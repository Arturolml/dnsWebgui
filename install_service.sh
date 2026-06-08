#!/usr/bin/env bash

# Check if script is run as root
if [ "$EUID" -ne 0 ]; then
  echo "Por favor, ejecuta este script con sudo o como root:"
  echo "sudo $0"
  exit 1
fi

echo "Instalando servicio BIND9 WebGUI..."

# Verify service file exists in current dir
if [ ! -f bind9-webgui.service ]; then
  echo "Error: No se encontró bind9-webgui.service en el directorio actual."
  exit 1
fi

# Copy service file
cp bind9-webgui.service /etc/systemd/system/bind9-webgui.service
chmod 644 /etc/systemd/system/bind9-webgui.service

# Reload systemd
echo "Recargando demonio de systemd..."
systemctl daemon-reload

# Enable service
echo "Habilitando servicio bind9-webgui para iniciar en el arranque..."
systemctl enable bind9-webgui.service

# Start service
echo "Iniciando servicio bind9-webgui..."
systemctl restart bind9-webgui.service

# Print status
echo "Estado del servicio:"
systemctl status bind9-webgui.service
