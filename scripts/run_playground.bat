@echo off
REM Starts the Streamlit playground (Windows). Run the service in another terminal.
cd /d "%~dp0\.."
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
pip install -q --disable-pip-version-check -r requirements-playground.txt
set PYTHONPATH=%CD%
streamlit run playground\streamlit_app.py
