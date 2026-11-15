#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python -m pip install --no-cache-dir -r backend/requirements-production.txt
python -m pip install --no-deps -e ./backend
npm --prefix frontend ci --include=dev --no-audit --no-fund --cache "$PWD/.lifeline/caches/npm"
npm --prefix frontend run build
