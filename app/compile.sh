#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$ROOT/bin"
mapfile -t SRC < <(find "$ROOT/src" -name '*.java' | sort)
javac --release 17 -encoding UTF-8 -d "$ROOT/bin" "${SRC[@]}"
mapfile -t TST < <(find "$ROOT/test" -name '*.java' | sort)
javac --release 17 -encoding UTF-8 -cp "$ROOT/bin" -d "$ROOT/bin" "${TST[@]}"
echo "Compilado en $ROOT/bin"
