#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python -m pip install --no-cache-dir -r requirements-render.txt
python scripts/check_render.py
