#!/bin/bash
# Monta el bucket de evidencias. Se puede dejar como servicio de systemd
# para que sobreviva un reinicio de la VM. Ver nexum-bucket.service.
set -euo pipefail
MOUNT=/mnt/evidencias
BUCKET=nexum-610248-evidencias
mkdir -p "$MOUNT"
if mountpoint -q "$MOUNT"; then
  exit 0
fi
gcsfuse --implicit-dirs -o allow_other "$BUCKET" "$MOUNT"
