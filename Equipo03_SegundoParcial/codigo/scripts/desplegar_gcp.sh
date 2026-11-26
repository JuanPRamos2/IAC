#!/bin/bash
# Deja la VM nexum-equipo03 corriendo la rama integrada.
#
# No sube signer.json. Ese archivo ya debe estar en /opt/nexum/signer.json.
# Si el bucket no está montado y gcsfuse existe, lo monta.
#
# Uso, como DELL, dentro de Equipo03_SegundoParcial/codigo, después del git pull:
#   bash scripts/desplegar_gcp.sh
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
cd "$RAIZ"

if [[ ! -f /opt/nexum/signer.json ]]; then
  echo "Falta /opt/nexum/signer.json. No está en Git y este guion no lo crea."
  exit 1
fi

if ! mountpoint -q /mnt/evidencias; then
  sudo mkdir -p /mnt/evidencias
  if command -v gcsfuse >/dev/null 2>&1; then
    sudo gcsfuse --implicit-dirs -o allow_other nexum-610248-evidencias /mnt/evidencias
  else
    echo "gcsfuse no está instalado y /mnt/evidencias no es un punto de montaje."
    exit 1
  fi
fi

if docker info >/dev/null 2>&1; then
  DC=(docker)
else
  DC=(sudo docker)
fi

"${DC[@]}" compose -f docker-compose.yml -f docker-compose.gcp.yml up -d --build
bash "$RAIZ/scripts/aplicar_migraciones_en_caliente.sh"
echo "Portal local de la VM: http://127.0.0.1:8000/salud"
echo "Portal del equipo: https://34.41.26.94.sslip.io/salud"
