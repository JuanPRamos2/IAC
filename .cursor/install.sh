#!/usr/bin/env bash
# Idempotent: compile the Java app if a JDK is available.
set -euo pipefail
cd "$(dirname "$0")/.."

chmod +x app/compile.sh app/run-cli.sh app/run-gui.sh app/run-tests.sh

if command -v javac >/dev/null 2>&1; then
  bash app/compile.sh
else
  echo "javac no está en PATH; el sitio estático en web/ no lo necesita."
fi
