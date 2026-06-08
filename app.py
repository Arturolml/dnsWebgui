import os
import json
import urllib.parse
import base64
from http.server import BaseHTTPRequestHandler, HTTPServer
from bind_manager import BindManager

# Determine configuration directory
config_dir = os.environ.get('BIND_CONFIG_DIR')
if not config_dir:
    config_dir = '/etc/bind'
    mode = 'production'
else:
    mode = 'custom'

print(f"Iniciando BIND9 WebGUI en modo: {mode.upper()}")
print(f"Carpeta de configuración: {config_dir}")

bind_mgr = BindManager(config_dir)

def get_ram_usage():
    try:
        with open('/proc/meminfo', 'r') as f:
            lines = f.readlines()
        mem_info = {}
        for line in lines:
            parts = line.split(':')
            if len(parts) == 2:
                mem_info[parts[0].strip()] = int(parts[1].replace('kB', '').strip())
        
        total = mem_info.get('MemTotal', 0)
        free = mem_info.get('MemFree', 0)
        buffers = mem_info.get('Buffers', 0)
        cached = mem_info.get('Cached', 0)
        
        used = total - free - buffers - cached
        if total > 0:
            pct = (used / total) * 100
            return {
                'total_mb': round(total / 1024, 1),
                'used_mb': round(used / 1024, 1),
                'percent': round(pct, 1)
            }
    except Exception:
        pass
    return {'total_mb': 0, 'used_mb': 0, 'percent': 0}

def get_cpu_load():
    try:
        with open('/proc/loadavg', 'r') as f:
            load = f.read().split()
        return {
            'load_1m': float(load[0]),
            'load_5m': float(load[1]),
            'load_15m': float(load[2]),
            'cores': os.cpu_count() or 1
        }
    except Exception:
        return {'load_1m': 0.0, 'load_5m': 0.0, 'load_15m': 0.0, 'cores': 1}

class BIND9WebGUIRequestHandler(BaseHTTPRequestHandler):
    def check_auth(self):
        auth_header = self.headers.get('Authorization')
        if not auth_header:
            self.send_unauthorized()
            return False
            
        try:
            auth_type, encoded_credentials = auth_header.split(' ', 1)
            if auth_type.lower() != 'basic':
                self.send_unauthorized()
                return False
            decoded = base64.b64decode(encoded_credentials).decode('utf-8')
            username, password = decoded.split(':', 1)
            if username in ['admindns', 'adminbind'] and password == 'ipkQoRm5X1U4mT':
                return True
        except Exception:
            pass
            
        self.send_unauthorized()
        return False

    def send_unauthorized(self):
        self.send_response(401)
        self.send_header('WWW-Authenticate', 'Basic realm="BIND9 WebGUI Administration"')
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(b"No autorizado")

    def send_json(self, status_code, data):
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        if not self.check_auth():
            return
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path
        query = urllib.parse.parse_qs(parsed_path.query)

        # API Routes
        if path.startswith('/api/'):
            self.handle_api_get(path, query)
        else:
            # Serve Static Files
            self.handle_static_serve(path)

    def do_POST(self):
        if not self.check_auth():
            return
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path
        query = urllib.parse.parse_qs(parsed_path.query)

        content_length = int(self.headers.get('Content-Length', 0))
        body_str = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else ""
        
        body_data = {}
        if body_str:
            try:
                body_data = json.loads(body_str)
            except json.JSONDecodeError:
                self.send_json(400, {'success': False, 'message': 'JSON body inválido'})
                return

        if path.startswith('/api/'):
            self.handle_api_post(path, query, body_data)
        else:
            self.send_json(404, {'success': False, 'message': 'Ruta POST no encontrada'})

    def do_DELETE(self):
        if not self.check_auth():
            return
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path
        query = urllib.parse.parse_qs(parsed_path.query)

        if path == '/api/zones':
            zone_name = query.get('name', [None])[0]
            if not zone_name:
                self.send_json(400, {'success': False, 'message': 'Falta el parámetro "name"'})
                return
            success, msg = bind_mgr.delete_zone(zone_name)
            self.send_json(200 if success else 400, {'success': success, 'message': msg})
        else:
            self.send_json(404, {'success': False, 'message': 'Ruta DELETE no encontrada'})

    def handle_static_serve(self, path):
        # Normalize path
        if path == '/':
            path = '/index.html'
            
        static_dir = os.path.join(os.path.dirname(__file__), 'static')
        # Prevent Directory Traversal
        safe_path = os.path.abspath(os.path.join(static_dir, path.lstrip('/')))
        if not safe_path.startswith(os.path.abspath(static_dir)):
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b"Acceso Prohibido")
            return
            
        if not os.path.exists(safe_path) or os.path.isdir(safe_path):
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"No Encontrado")
            return
            
        # Determine content type
        content_type = 'text/plain'
        if safe_path.endswith('.html'):
            content_type = 'text/html; charset=utf-8'
        elif safe_path.endswith('.css'):
            content_type = 'text/css; charset=utf-8'
        elif safe_path.endswith('.js'):
            content_type = 'application/javascript; charset=utf-8'
        elif safe_path.endswith('.svg'):
            content_type = 'image/svg+xml'
            
        try:
            with open(safe_path, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(f"Error interno del servidor: {e}".encode('utf-8'))

    def handle_api_get(self, path, query):
        if path == '/api/status':
            svc_status, svc_msg = bind_mgr.get_service_status()
            
            # Count zones
            zones = bind_mgr.get_zones()
            fwd_count = sum(1 for z in zones if not z['is_reverse'])
            rev_count = sum(1 for z in zones if z['is_reverse'])
            
            data = {
                'service': {
                    'status': svc_status,
                    'message': svc_msg
                },
                'system': {
                    'ram': get_ram_usage(),
                    'cpu': get_cpu_load()
                },
                'zones': {
                    'total': len(zones),
                    'forward': fwd_count,
                    'reverse': rev_count
                },
                'mode': mode,
                'config_dir': config_dir
            }
            self.send_json(200, data)
            
        elif path == '/api/zones':
            zones = bind_mgr.get_zones()
            self.send_json(200, {'success': True, 'zones': zones})
            
        elif path == '/api/records':
            zone_name = query.get('zone', [None])[0]
            if not zone_name:
                self.send_json(400, {'success': False, 'message': 'Parámetro "zone" es requerido'})
                return
                
            res, err = bind_mgr.get_zone_records(zone_name)
            if err:
                self.send_json(400, {'success': False, 'message': err})
            else:
                self.send_json(200, {'success': True, 'data': res})
                
        elif path == '/api/options':
            opts = bind_mgr.get_options()
            self.send_json(200, {'success': True, 'options': opts})
            
        elif path == '/api/raw_config':
            file_type = query.get('file', [None])[0]
            if not file_type:
                self.send_json(400, {'success': False, 'message': 'Parámetro "file" es requerido'})
                return
            content = bind_mgr.get_raw_config(file_type)
            self.send_json(200, {'success': True, 'content': content})
            
        elif path == '/api/validate':
            success, output = bind_mgr.validate_all()
            self.send_json(200, {'success': success, 'output': output})
            
        else:
            self.send_json(404, {'success': False, 'message': 'Endpoint de API GET no encontrado'})

    def handle_api_post(self, path, query, body):
        if path == '/api/service':
            action = body.get('action')
            success, msg = bind_mgr.control_service(action)
            self.send_json(200 if success else 400, {'success': success, 'message': msg})
            
        elif path == '/api/zones':
            name = body.get('name')
            zone_type = body.get('type', 'master')
            is_reverse = body.get('is_reverse', False)
            
            success, msg = bind_mgr.add_zone(name, zone_type, is_reverse)
            self.send_json(200 if success else 400, {'success': success, 'message': msg})
            
        elif path == '/api/zones/rename':
            old_name = body.get('old_name')
            new_name = body.get('new_name')
            if not old_name or not new_name:
                self.send_json(400, {'success': False, 'message': 'Nombres antiguo y nuevo son requeridos'})
                return
            success, msg = bind_mgr.rename_zone(old_name, new_name)
            self.send_json(200 if success else 400, {'success': success, 'message': msg})
            
        elif path == '/api/records':
            zone_name = body.get('zone')
            default_ttl = body.get('default_ttl', '604800')
            soa = body.get('soa')
            records = body.get('records')
            
            if not zone_name or not soa or records is None:
                self.send_json(400, {'success': False, 'message': 'Datos de zona incompletos'})
                return
                
            success, msg = bind_mgr.save_zone_records(zone_name, default_ttl, soa, records)
            self.send_json(200 if success else 400, {'success': success, 'message': msg})
            
        elif path == '/api/options':
            options_dict = body.get('options')
            if not options_dict or 'recursion' not in options_dict or 'forwarders' not in options_dict:
                self.send_json(400, {'success': False, 'message': 'Datos de opciones inválidos'})
                return
            success, msg = bind_mgr.save_options(options_dict)
            self.send_json(200 if success else 400, {'success': success, 'message': msg})
            
        elif path == '/api/raw_config':
            file_type = body.get('file')
            content = body.get('content')
            if not file_type or content is None:
                self.send_json(400, {'success': False, 'message': 'Archivo o contenido vacío'})
                return
            success, msg = bind_mgr.save_raw_config(file_type, content)
            self.send_json(200 if success else 400, {'success': success, 'message': msg})
            
        else:
            self.send_json(404, {'success': False, 'message': 'Endpoint de API POST no encontrado'})

def run_server(port=8080):
    server_address = ('', port)
    httpd = HTTPServer(server_address, BIND9WebGUIRequestHandler)
    print(f"Servidor WebGUI ejecutándose en http://localhost:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
        httpd.server_close()

if __name__ == '__main__':
    run_server()
