#!/usr/bin/env bash

# setup.sh - Script de instalación/despliegue para BIND9 WebGUI
# Este script automatiza la instalación del servidor DNS WebGUI en cualquier servidor Debian/Ubuntu.

# 1. Comprobar privilegios de root
if [ "$EUID" -ne 0 ]; then
  echo "❌ Error: Por favor, ejecuta este script como root o usando sudo:"
  echo "sudo $0"
  exit 1
fi

echo "============================================="
echo "   Instalador de BIND9 WebGUI"
echo "============================================="

# 2. Comprobar e instalar dependencias del sistema
echo "🔍 Comprobando dependencias del sistema..."

# Actualizar repositorios si es necesario
echo "🔄 Actualizando lista de paquetes (apt-get update)..."
apt-get update -y > /dev/null

# Comprobar/Instalar python3, python3-venv y bind9
PACKAGES_TO_INSTALL=()

if ! command -v python3 &> /dev/null; then
    PACKAGES_TO_INSTALL+=("python3")
fi

# Debian/Ubuntu separa venv en un paquete aparte
if ! dpkg -s python3-venv &> /dev/null; then
    PACKAGES_TO_INSTALL+=("python3-venv")
fi

if ! command -v named &> /dev/null; then
    PACKAGES_TO_INSTALL+=("bind9")
fi

if [ ${#PACKAGES_TO_INSTALL[@]} -ne 0 ]; then
    echo "📦 Instalando paquetes requeridos: ${PACKAGES_TO_INSTALL[*]}..."
    apt-get install -y "${PACKAGES_TO_INSTALL[@]}"
else
    echo "✅ Todas las dependencias del sistema (Python3, venv, BIND9) ya están instaladas."
fi

# 3. Preguntar por la ruta de instalación
DEFAULT_INSTALL_DIR="/opt/bind9-webgui"
read -p "📂 Introduce la ruta de instalación [$DEFAULT_INSTALL_DIR]: " INSTALL_DIR
INSTALL_DIR=${INSTALL_DIR:-$DEFAULT_INSTALL_DIR}

echo "🚀 Iniciando despliegue en: $INSTALL_DIR"

# Crear directorio de destino si no existe
mkdir -p "$INSTALL_DIR"

# 4. Copiar archivos del proyecto
echo "📂 Copiando archivos de la aplicación..."
cp -r app.py bind_manager.py static "$INSTALL_DIR/"

# 5. Crear el entorno virtual de Python
echo "🐍 Creando entorno virtual de Python (venv) en $INSTALL_DIR/venv..."
python3 -m venv "$INSTALL_DIR/venv"

# Cambiar propietario de la carpeta de instalación al usuario actual (o dejarlo en root)
# Dado que se ejecuta como servicio root, dejarlo como root es correcto y seguro.
chown -R root:root "$INSTALL_DIR"

# 6. Generar y registrar el servicio systemd
echo "⚙️ Configurando servicio systemd (bind9-webgui.service)..."

SERVICE_FILE="/etc/systemd/system/bind9-webgui.service"

cat <<EOF > "$SERVICE_FILE"
[Unit]
Description=BIND9 WebGUI - DNS Administration Interface
After=network.target named.service

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python3 app.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

chmod 644 "$SERVICE_FILE"

# 7. Recargar systemd y arrancar el servicio
echo "🔄 Recargando systemd y habilitando el servicio..."
systemctl daemon-reload
systemctl enable bind9-webgui.service
echo "🔄 Iniciando BIND9 WebGUI..."
systemctl restart bind9-webgui.service

# 8. Mostrar resultado y estado final
echo "============================================="
echo "🎉 ¡Instalación completada con éxito!"
echo "============================================="
echo "🌐 URL de acceso: http://<IP_DEL_SERVIDOR>:8080"
echo "🔐 Credenciales de administración:"
echo "   Usuario: admindns"
echo "   Contraseña: ipkQoRm5X1U4mT"
echo ""
echo "📊 Estado del servicio bind9-webgui:"
systemctl status bind9-webgui.service --no-pager -n 5
