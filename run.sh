#!/usr/bin/env bash
# Start AP Autopilot on http://localhost:8000
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi
[ -d samples ] && [ "$(ls samples | wc -l)" -gt 0 ] || .venv/bin/python scripts/generate_samples.py
exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
