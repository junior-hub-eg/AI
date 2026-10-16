#!/usr/bin/env bash
# Starts the Streamlit playground (Linux / macOS / Git-Bash). Run the service in another terminal.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -q --disable-pip-version-check -r requirements-playground.txt
export PYTHONPATH="$PWD"
exec streamlit run playground/streamlit_app.py
