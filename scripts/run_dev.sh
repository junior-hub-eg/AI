#!/usr/bin/env bash
# One-command local start (Linux / macOS / Git-Bash).
set -euo pipefail
cd "$(dirname "$0")/.."
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -q --disable-pip-version-check -r requirements.txt
exec uvicorn app.main:create_app --factory --reload --reload-dir app --reload-dir prompts --port 8000
