#!/bin/bash
# Aplica las migraciones del tercer parcial sobre una base que YA tiene datos.
#
# PostgreSQL solo ejecuta docker-entrypoint-initdb.d cuando el volumen está
# vacío. En nexum-equipo03 el volumen ya existe, así que 019, 020, 021 y 022
# no corren solas al volver a levantar los contenedores.
#
# Uso, desde Equipo03_SegundoParcial/codigo:
#   bash scripts/aplicar_migraciones_en_caliente.sh
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
cd "$RAIZ"

if docker info >/dev/null 2>&1; then
  DC=(docker)
else
  DC=(sudo docker)
fi

archivos=(
  db/migraciones/019_cuatro_ojos_en_la_aprobacion.sql
  db/migraciones/020_la_jerarquia_se_impide_romper.sql
  db/migraciones/021_analisis_complejo_y_rendimiento.sql
  db/migraciones/022_historial_disponibilidad.sql
)

"${DC[@]}" compose -f docker-compose.yml -f docker-compose.gcp.yml exec -T datos \
  psql -U postgres -d bienestar -v ON_ERROR_STOP=1 <<'SQL'
CREATE TABLE IF NOT EXISTS auditoria.migracion_aplicada (
    nombre TEXT PRIMARY KEY,
    aplicada_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
SQL

for archivo in "${archivos[@]}"; do
  nombre="$(basename "$archivo")"
  ya="$("${DC[@]}" compose -f docker-compose.yml -f docker-compose.gcp.yml exec -T datos \
    psql -U postgres -d bienestar -tAc \
    "SELECT 1 FROM auditoria.migracion_aplicada WHERE nombre = '${nombre}'")"
  if [[ "$ya" == "1" ]]; then
    echo "Ya aplicada: $nombre"
    continue
  fi
  echo "Aplicando $nombre"
  "${DC[@]}" compose -f docker-compose.yml -f docker-compose.gcp.yml exec -T datos \
    psql -U postgres -d bienestar -v ON_ERROR_STOP=1 < "$archivo"
  "${DC[@]}" compose -f docker-compose.yml -f docker-compose.gcp.yml exec -T datos \
    psql -U postgres -d bienestar -v ON_ERROR_STOP=1 \
    -c "INSERT INTO auditoria.migracion_aplicada (nombre) VALUES ('${nombre}') ON CONFLICT DO NOTHING"
done

echo "Migraciones del tercer parcial al día."
