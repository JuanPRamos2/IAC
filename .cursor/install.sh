#!/usr/bin/env bash
# Idempotent setup for the IAC web monolith (Flask).
set -euo pipefail

# Run from the repository root regardless of where the script is invoked from.
cd "$(dirname "$0")/.."

# The default image ships Python 3 but not the venv module; add it if missing.
if ! python3 -c 'import ensurepip' >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq python3-venv
fi

# Create (or reuse) the virtual environment and refresh dependencies.
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/pip install -r requirements-dev.txt

# Provide a local .env for development if one does not already exist.
# Never commit real secrets; OPENROUTER_API_KEY stays empty until provided.
if [ ! -f .env ]; then
  cp .env.example .env
fi
