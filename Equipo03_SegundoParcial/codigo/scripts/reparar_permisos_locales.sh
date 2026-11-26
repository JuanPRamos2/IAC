#!/bin/bash
# El arranque de Postgres solo otorga permisos cuando el volumen está vacío.
# Si la base ya existía, el rol puede entrar y aun así no poder leer
# usuarios.usuario. Este guion aplica db/esquema/09_permisos.sh sobre esa base.
#
# En la laptop:
#   bash scripts/reparar_permisos_locales.sh
# En la máquina virtual, desde esta misma carpeta, el guion detecta la llave
# y usa también docker-compose.gcp.yml.
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
cd "$RAIZ"

if docker info >/dev/null 2>&1; then
  DC=(docker)
else
  DC=(sudo docker)
fi

archivos=(-f docker-compose.yml)
if [[ -f /opt/nexum/signer.json ]]; then
  archivos+=(-f docker-compose.gcp.yml)
fi

"${DC[@]}" compose "${archivos[@]}" exec -T datos bash /docker-entrypoint-initdb.d/90_permisos.sh
"${DC[@]}" compose "${archivos[@]}" restart auth-service web
echo "Permisos de bienestar_app aplicados."
