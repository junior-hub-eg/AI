@echo off
REM One-command local start (Windows).
cd /d "%~dp0\.."
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
pip install -q --disable-pip-version-check -r requirements.txt
uvicorn app.main:create_app --factory --reload --reload-dir app --reload-dir prompts --port 8000
