import os
import re
import subprocess
import shutil

class BindManager:
    def __init__(self, config_dir=None):
        # By default, use system BIND9 configuration directory
        if config_dir is None:
            self.config_dir = '/etc/bind'
        else:
            self.config_dir = os.path.abspath(config_dir)
            
        self.named_conf_path = os.path.join(self.config_dir, 'named.conf')
        self.named_conf_local_path = os.path.join(self.config_dir, 'named.conf.local')
        self.named_conf_options_path = os.path.join(self.config_dir, 'named.conf.options')

    def _strip_comments(self, text):
        # Remove /* ... */ comments
        text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
        # Remove // ... comments
        text = re.sub(r'//.*', '', text)
        # Remove # ... comments
        text = re.sub(r'#.*', '', text)
        return text

    def get_zones(self):
        if not os.path.exists(self.named_conf_local_path):
            return []
            
        try:
            with open(self.named_conf_local_path, 'r') as f:
                content = f.read()
        except Exception as e:
            print(f"Error reading named.conf.local: {e}")
            return []
            
        clean_content = self._strip_comments(content)
        # Regex to match zone "zone_name" { type_and_file_stuff };
        zone_pattern = r'zone\s+"([^"]+)"\s*\{\s*(.*?)\s*\};'
        zones = []
        
        for match in re.finditer(zone_pattern, clean_content, re.DOTALL):
            name = match.group(1)
            body = match.group(2)
            
            type_match = re.search(r'type\s+([^;]+);', body)
            file_match = re.search(r'file\s+"([^"]+)";', body)
            
            zone_type = type_match.group(1).strip() if type_match else 'master'
            zone_file = file_match.group(1).strip() if file_match else ''
            
            # If the path in the file directive is relative, make it relative to self.config_dir
            if zone_file and not os.path.isabs(zone_file):
                # We show the absolute path in the manager, but write it back as is
                abs_file = os.path.abspath(os.path.join(self.config_dir, zone_file))
            else:
                abs_file = zone_file
                
            is_reverse = 'in-addr.arpa' in name or 'ip6.arpa' in name
            
            zones.append({
                'name': name,
                'type': zone_type,
                'file_path': abs_file,
                'raw_file_path': zone_file, # Keep raw string for named.conf.local formatting
                'is_reverse': is_reverse
            })
            
        return zones

    def save_zones(self, zones):
        """Save list of zones to named.conf.local"""
        lines = []
        for z in zones:
            # Maintain path styling (if it is inside config_dir, write relative or absolute appropriately)
            file_path = z['file_path']
            # If the config directory is the system /etc/bind, we write absolute. 
            # For local test development, let's keep absolute paths so BIND check utilities don't get confused.
            lines.append(f'zone "{z["name"]}" {{')
            lines.append(f'    type {z["type"]};')
            lines.append(f'    file "{file_path}";')
            lines.append('};')
            lines.append('')
            
        try:
            with open(self.named_conf_local_path, 'w') as f:
                f.write('\n'.join(lines))
            return True, "Zonas guardadas correctamente"
        except Exception as e:
            return False, f"Error escribiendo named.conf.local: {str(e)}"

    def add_zone(self, name, zone_type='master', is_reverse=False):
        # Validate zone name
        name = name.strip().lower()
        if not name:
            return False, "El nombre de la zona no puede estar vacío"
            
        zones = self.get_zones()
        for z in zones:
            if z['name'] == name:
                return False, f"La zona '{name}' ya existe"
                
        # Generate default file name
        sanitized_name = re.sub(r'[^a-z0-9.-]', '_', name)
        db_filename = f"db.{sanitized_name}"
        file_path = os.path.join(self.config_dir, db_filename)
        
        # Create zone file with a default template
        soa = {
            'name': '@',
            'mname': 'ns1.' + (name if not is_reverse else 'example.com.'),
            'rname': 'admin.' + (name if not is_reverse else 'example.com.'),
            'serial': 1,
            'refresh': 604800,
            'retry': 86400,
            'expire': 2419200,
            'minimum': 604800
        }
        
        # Ensure email ending in dot
        if not soa['mname'].endswith('.'): soa['mname'] += '.'
        if not soa['rname'].endswith('.'): soa['rname'] += '.'
        
        records = [
            {
                'name': '@',
                'ttl': '',
                'class': 'IN',
                'type': 'NS',
                'value': soa['mname']
            }
        ]
        
        if not is_reverse:
            # Default A record for the nameserver and apex
            records.append({
                'name': '@',
                'ttl': '',
                'class': 'IN',
                'type': 'A',
                'value': '127.0.0.1'
            })
            records.append({
                'name': 'ns1',
                'ttl': '',
                'class': 'IN',
                'type': 'A',
                'value': '127.0.0.1'
            })
        else:
            # Default PTR record for the NS
            records.append({
                'name': '1',
                'ttl': '',
                'class': 'IN',
                'type': 'PTR',
                'value': 'ns1.example.com.'
            })
            
        # Write the zone file
        formatted_zone = self._format_zone_file('604800', soa, records)
        try:
            with open(file_path, 'w') as f:
                f.write(formatted_zone)
        except Exception as e:
            return False, f"No se pudo crear el archivo de zona: {str(e)}"
            
        # Update named.conf.local
        zones.append({
            'name': name,
            'type': zone_type,
            'file_path': file_path,
            'is_reverse': is_reverse
        })
        
        success, msg = self.save_zones(zones)
        if not success:
            # Cleanup created db file on failure
            if os.path.exists(file_path):
                os.remove(file_path)
            return False, msg
            
        return True, f"Zona '{name}' agregada con éxito"

    def delete_zone(self, name):
        name = name.strip().lower()
        zones = self.get_zones()
        target_zone = None
        
        for z in zones:
            if z['name'] == name:
                target_zone = z
                break
                
        if not target_zone:
            return False, f"La zona '{name}' no existe"
            
        # Remove from list
        zones = [z for z in zones if z['name'] != name]
        success, msg = self.save_zones(zones)
        
        if success:
            # Optionally delete the file if it's in our config directory
            db_path = target_zone['file_path']
            if os.path.exists(db_path) and os.path.dirname(db_path) == self.config_dir:
                try:
                    os.remove(db_path)
                except Exception as e:
                    print(f"Warning: could not delete zone file {db_path}: {e}")
            return True, f"Zona '{name}' eliminada con éxito"
        return False, msg

    def get_zone_records(self, zone_name):
        zones = self.get_zones()
        zone = next((z for z in zones if z['name'] == zone_name), None)
        if not zone:
            return None, "La zona no existe"
            
        file_path = zone['file_path']
        if not os.path.exists(file_path):
            return None, f"El archivo de base de datos de la zona no existe en: {file_path}"
            
        try:
            with open(file_path, 'r') as f:
                content = f.read()
        except Exception as e:
            return None, f"Error al leer el archivo de zona: {str(e)}"
            
        default_ttl, soa, records = self._parse_zone_file(content)
        return {
            'default_ttl': default_ttl,
            'soa': soa,
            'records': records,
            'file_path': file_path
        }, None

    def save_zone_records(self, zone_name, default_ttl, soa, records):
        zones = self.get_zones()
        zone = next((z for z in zones if z['name'] == zone_name), None)
        if not zone:
            return False, "La zona no existe"
            
        file_path = zone['file_path']
        
        # Increment serial automatically (Standard BIND9 behavior when changes happen)
        try:
            soa['serial'] = int(soa['serial']) + 1
        except Exception:
            soa['serial'] = 1
            
        formatted_content = self._format_zone_file(default_ttl, soa, records)
        
        # Write to temporary file first to run checkzone
        temp_file_path = file_path + ".tmp"
        try:
            with open(temp_file_path, 'w') as f:
                f.write(formatted_content)
        except Exception as e:
            return False, f"Error escribiendo archivo temporal de zona: {str(e)}"
            
        # Validate zone
        validation_success, validation_output = self.validate_zone_file(zone_name, temp_file_path)
        if not validation_success:
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
            return False, f"La validación del archivo de zona falló:\n{validation_output}"
            
        # Replace original file with temporary file
        try:
            shutil.move(temp_file_path, file_path)
            return True, "Registros de la zona guardados y validados correctamente"
        except Exception as e:
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
            return False, f"Error al guardar el archivo final de zona: {str(e)}"

    def _parse_zone_file(self, content):
        # Find default TTL
        ttl_match = re.search(r'^\$TTL\s+(\S+)', content, re.IGNORECASE | re.MULTILINE)
        default_ttl = ttl_match.group(1) if ttl_match else '86400'
        
        # Find SOA record
        soa_pattern = r'(\S+)\s+(?:IN\s+)?SOA\s+(\S+)\s+(\S+)\s*\(\s*(.*?)\s*\)'
        soa_block_match = re.search(soa_pattern, content, re.DOTALL | re.IGNORECASE)
        
        soa = {
            'name': '@',
            'mname': '',
            'rname': '',
            'serial': 1,
            'refresh': 604800,
            'retry': 86400,
            'expire': 2419200,
            'minimum': 604800
        }
        
        records_start_pos = 0
        if soa_block_match:
            soa['name'] = soa_block_match.group(1)
            soa['mname'] = soa_block_match.group(2)
            soa['rname'] = soa_block_match.group(3)
            soa_body = soa_block_match.group(4)
            
            # Clean comments inside SOA body
            soa_body_clean = re.sub(r';.*', '', soa_body)
            soa_numbers = soa_body_clean.split()
            if len(soa_numbers) >= 5:
                soa['serial'] = int(soa_numbers[0])
                soa['refresh'] = int(soa_numbers[1])
                soa['retry'] = int(soa_numbers[2])
                soa['expire'] = int(soa_numbers[3])
                soa['minimum'] = int(soa_numbers[4])
                
            records_start_pos = soa_block_match.end()
            
        # Parse the records
        records = []
        lines = content[records_start_pos:].split('\n')
        current_name = '@'
        
        record_types = {'A', 'AAAA', 'CNAME', 'MX', 'TXT', 'NS', 'PTR', 'SRV'}
        
        for line in lines:
            # Strip comments
            line_clean = re.sub(r';.*', '', line).strip()
            if not line_clean:
                continue
                
            # Skip directive statements
            if line_clean.upper().startswith('$TTL') or line_clean.upper().startswith('$ORIGIN'):
                continue
                
            starts_with_ws = len(line) > 0 and line[0] in (' ', '\t')
            tokens = line_clean.split()
            if not tokens:
                continue
                
            # Find the type token
            type_idx = -1
            for i, tok in enumerate(tokens):
                if tok.upper() in record_types:
                    type_idx = i
                    break
                    
            if type_idx == -1:
                # Unknown type, skip or store as raw
                continue
                
            rec_type = tokens[type_idx].upper()
            rec_value = ' '.join(tokens[type_idx+1:])
            
            rec_ttl = ''
            rec_class = 'IN'
            
            prefix_tokens = tokens[:type_idx]
            
            if starts_with_ws:
                rec_name = current_name
            else:
                if prefix_tokens:
                    rec_name = prefix_tokens[0]
                    current_name = rec_name
                    prefix_tokens = prefix_tokens[1:]
                else:
                    rec_name = current_name
                    
            for pt in prefix_tokens:
                if pt.upper() == 'IN':
                    rec_class = 'IN'
                elif pt.isdigit():
                    rec_ttl = pt
                else:
                    rec_ttl = pt # String ttl
                    
            records.append({
                'name': rec_name,
                'ttl': rec_ttl,
                'class': rec_class,
                'type': rec_type,
                'value': rec_value
            })
            
        return default_ttl, soa, records

    def _format_zone_file(self, default_ttl, soa, records):
        lines = []
        lines.append(f"$TTL    {default_ttl}")
        
        # Format SOA
        lines.append(f"{soa['name']}       IN      SOA     {soa['mname']} {soa['rname']} (")
        lines.append(f"                              {soa['serial']}       ; Serial")
        lines.append(f"                         {soa['refresh']}         ; Refresh")
        lines.append(f"                          {soa['retry']}         ; Retry")
        lines.append(f"                        {soa['expire']}         ; Expire")
        lines.append(f"                         {soa['minimum']} )       ; Negative Cache TTL")
        lines.append(";")
        
        # Format Records
        for r in records:
            name_part = r['name'].ljust(15)
            class_part = f"{r['class']}      " if r['class'] else "IN      "
            ttl_part = f"{r['ttl']}".ljust(8) + " " if r['ttl'] else ""
            type_part = r['type'].ljust(8)
            value_part = r['value']
            lines.append(f"{name_part} {ttl_part}{class_part}{type_part} {value_part}")
            
        return '\n'.join(lines) + '\n'

    def get_options(self):
        if not os.path.exists(self.named_conf_options_path):
            return {
                'recursion': 'yes',
                'forwarders': []
            }
            
        try:
            with open(self.named_conf_options_path, 'r') as f:
                content = f.read()
        except Exception as e:
            print(f"Error reading named.conf.options: {e}")
            return {'recursion': 'yes', 'forwarders': []}
            
        clean_content = self._strip_comments(content)
        
        recursion_match = re.search(r'recursion\s+(yes|no);', clean_content, re.IGNORECASE)
        recursion = recursion_match.group(1).lower() if recursion_match else 'yes'
        
        forwarders = []
        forwarders_match = re.search(r'forwarders\s*\{\s*(.*?)\s*\};', clean_content, re.DOTALL)
        if forwarders_match:
            body = forwarders_match.group(1)
            ips = [ip.strip() for ip in body.split(';') if ip.strip()]
            forwarders = ips
            
        return {
            'recursion': recursion,
            'forwarders': forwarders
        }

    def save_options(self, options_dict):
        forwarders_str = ""
        if options_dict.get('forwarders'):
            forwarders_str = "\n        " + ";\n        ".join(options_dict['forwarders']) + ";\n    "
            
        recursion = options_dict.get('recursion', 'yes')
        
        # Use default cache folder on Debian
        directory = "/var/cache/bind"
        
        content = f"""options {{
    directory "{directory}";

    forwarders {{{forwarders_str}}};

    dnssec-validation auto;

    listen-on port 53 {{ any; }};
    allow-query {{ any; }};
    recursion {recursion};
}};
"""
        # Save to temp and validate first
        temp_options_path = self.named_conf_options_path + ".tmp"
        try:
            with open(temp_options_path, 'w') as f:
                f.write(content)
        except Exception as e:
            return False, f"Error escribiendo archivo temporal de opciones: {str(e)}"
            
        # To validate options we must ensure named.conf refers to it or validate the whole config.
        # But we can validate the single file structure with named-checkconf
        success, output = self.validate_config_file(temp_options_path)
        if not success:
            if os.path.exists(temp_options_path):
                os.remove(temp_options_path)
            return False, f"La validación de opciones falló:\n{output}"
            
        try:
            shutil.move(temp_options_path, self.named_conf_options_path)
            return True, "Opciones configuradas y validadas con éxito"
        except Exception as e:
            if os.path.exists(temp_options_path):
                os.remove(temp_options_path)
            return False, f"Error al guardar el archivo final de opciones: {str(e)}"

    def get_raw_config(self, file_type):
        """Get raw file contents of BIND9 config files"""
        path_map = {
            'named.conf': self.named_conf_path,
            'named.conf.local': self.named_conf_local_path,
            'named.conf.options': self.named_conf_options_path
        }
        
        file_path = path_map.get(file_type)
        if not file_path or not os.path.exists(file_path):
            return ""
            
        try:
            with open(file_path, 'r') as f:
                return f.read()
        except Exception:
            return ""

    def save_raw_config(self, file_type, content):
        """Save raw file content and validate"""
        path_map = {
            'named.conf': self.named_conf_path,
            'named.conf.local': self.named_conf_local_path,
            'named.conf.options': self.named_conf_options_path
        }
        
        file_path = path_map.get(file_type)
        if not file_path:
            return False, "Tipo de archivo desconocido"
            
        temp_path = file_path + ".tmp"
        try:
            with open(temp_path, 'w') as f:
                f.write(content)
        except Exception as e:
            return False, f"Error escribiendo archivo temporal: {str(e)}"
            
        # Validate syntax
        success, output = self.validate_config_file(temp_path)
        if not success:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return False, f"Validación de sintaxis fallida:\n{output}"
            
        try:
            shutil.move(temp_path, file_path)
            return True, "Archivo guardado y validado con éxito"
        except Exception as e:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return False, f"Error guardando el archivo final: {str(e)}"

    def rename_zone(self, old_name, new_name):
        old_name = old_name.strip().lower()
        new_name = new_name.strip().lower()
        
        if not new_name:
            return False, "El nuevo nombre de la zona no puede estar vacío"
            
        if old_name == new_name:
            return True, "El nombre de la zona es el mismo"
            
        zones = self.get_zones()
        target_zone = None
        for z in zones:
            if z['name'] == old_name:
                target_zone = z
            if z['name'] == new_name:
                return False, f"La zona '{new_name}' ya existe"
                
        if not target_zone:
            return False, f"La zona '{old_name}' no existe"
            
        old_db_path = target_zone['file_path']
        
        sanitized_new_name = re.sub(r'[^a-z0-9.-]', '_', new_name)
        new_db_filename = f"db.{sanitized_new_name}"
        new_db_path = os.path.join(self.config_dir, new_db_filename)
        
        if os.path.exists(old_db_path):
            try:
                shutil.move(old_db_path, new_db_path)
            except Exception as e:
                return False, f"No se pudo renombrar el archivo de zona: {str(e)}"
                
        target_zone['name'] = new_name
        target_zone['file_path'] = new_db_path
        
        success, msg = self.save_zones(zones)
        if success:
            return True, f"Zona renombrada de '{old_name}' a '{new_name}' con éxito"
        else:
            if os.path.exists(new_db_path):
                shutil.move(new_db_path, old_db_path)
            return False, msg

    # Verification and Service Control methods
    def validate_config_file(self, filepath):
        try:
            res = subprocess.run(['named-checkconf', filepath], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0:
                return True, ""
            return False, res.stderr or res.stdout
        except FileNotFoundError:
            return True, "named-checkconf no está instalado (omitido)"
        except Exception as e:
            return False, str(e)

    def validate_zone_file(self, zone_name, filepath):
        try:
            res = subprocess.run(['named-checkzone', zone_name, filepath], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0:
                return True, res.stdout
            return False, res.stderr or res.stdout
        except FileNotFoundError:
            return True, "named-checkzone no está instalado (omitido)"
        except Exception as e:
            return False, str(e)

    def validate_all(self):
        """Validate the main config named.conf"""
        if not os.path.exists(self.named_conf_path):
            return False, "named.conf no existe"
        return self.validate_config_file(self.named_conf_path)

    def get_service_status(self):
        """Check status of BIND9 system service"""
        try:
            res = subprocess.run(['systemctl', 'is-active', 'named'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            status = res.stdout.strip()
            if status == 'active':
                return 'running', 'El servidor DNS está activo y funcionando'
            elif status == 'inactive':
                return 'stopped', 'El servidor DNS está inactivo (detenido)'
            elif status == 'failed':
                return 'failed', 'El servidor DNS falló al arrancar'
            else:
                return 'unknown', f'Estado del servicio desconocido: {status}'
        except FileNotFoundError:
            # Let's see if process named is running (non-systemd environment check)
            try:
                res = subprocess.run(['pgrep', 'named'], stdout=subprocess.PIPE, text=True)
                if res.stdout.strip():
                    return 'running', 'El proceso named está activo'
                return 'stopped', 'El proceso named no está activo'
            except Exception:
                return 'offline', 'No se puede verificar el estado de BIND9 (systemd/pgrep no disponibles)'
        except Exception as e:
            return 'error', f'Error consultando servicio: {str(e)}'

    def control_service(self, action):
        """Run systemctl action on bind9 service (requires permissions)"""
        # Mapping actions to named.service
        if action not in ['start', 'stop', 'restart', 'reload']:
            return False, "Acción de servicio no permitida"
            
        # Check if running as root
        is_root = os.getuid() == 0
        
        # We can construct the systemctl command
        cmd = ['systemctl', action, 'named']
        
        # If we are not root, we will try to run with sudo. 
        # Note: if sudo requires a password, it will fail, and we will catch that and report it.
        if not is_root:
            cmd = ['sudo', '-n', 'systemctl', action, 'named']
            
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0:
                return True, f"Servicio BIND9 '{action}' completado con éxito"
            
            # Check if it was a sudo credential issue
            stderr_out = res.stderr or ""
            if "password is required" in stderr_out or "a password is required" in stderr_out:
                return False, f"Permiso denegado. Para controlar el servicio, ejecuta la WebGUI con 'sudo python3 app.py' o configura sudoers. Comando fallido: {' '.join(cmd)}"
                
            return False, f"Fallo al ejecutar '{action}': {res.stderr or res.stdout}"
        except Exception as e:
            return False, f"Excepción al controlar servicio: {str(e)}"
