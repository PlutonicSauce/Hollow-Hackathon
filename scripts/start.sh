#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
test -f frontend/dist/index.html || { echo 'Missing frontend build; run bash scripts/build.sh.' >&2; exit 1; }
exec python -m gunicorn --config backend/gunicorn.conf.py engine.public_app:application
