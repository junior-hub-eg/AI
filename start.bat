@echo off
rem Starts the assistant with the test chat at http://localhost:8010 and restarts it whenever a .py file changes.
rem After editing .env, close this window and run it again.
cd /d "%~dp0"
start "" http://localhost:8010
".venv\Scripts\python.exe" -m uvicorn app.main:app --port 8010 --reload
