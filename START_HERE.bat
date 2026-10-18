@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
set LOG=%~dp0start_log.txt
echo ==== %date% %time% ==== > "%LOG%"

REM ---------- 2) Python 3.11+ environment ----------
if exist .venv\Scripts\python.exe goto :venv_ok
set UVEXE=
where uv >nul 2>&1 && set UVEXE=uv
if not defined UVEXE if exist "%USERPROFILE%\.local\bin\uv.exe" set UVEXE="%USERPROFILE%\.local\bin\uv.exe"
if not defined UVEXE if exist "%USERPROFILE%\.cargo\bin\uv.exe" set UVEXE="%USERPROFILE%\.cargo\bin\uv.exe"
if defined UVEXE (
  echo Creating Python 3.12 environment with uv...
  !UVEXE! venv --python 3.12 .venv >> "%LOG%" 2>&1
  if exist .venv\Scripts\python.exe goto :venv_ok
)
for %%V in (3.13 3.12 3.11) do (
  if not exist .venv\Scripts\python.exe (
    py -%%V -m venv .venv >> "%LOG%" 2>&1
  )
)
if exist .venv\Scripts\python.exe goto :venv_ok
python -c "import sys; sys.exit(0 if sys.version_info>=(3,11) else 1)" >nul 2>&1 && python -m venv .venv >> "%LOG%" 2>&1
if exist .venv\Scripts\python.exe goto :venv_ok
echo [X] No Python 3.11+ found and uv not available. >> "%LOG%"
echo [X] No Python 3.11+ found. Install Python 3.12 from https://www.python.org/downloads/ ^(tick "Add to PATH"^) and run again.
pause
exit /b 1

:venv_ok
.venv\Scripts\python.exe --version >> "%LOG%" 2>&1
echo Installing packages (first time ~1-2 min)...
.venv\Scripts\python.exe -m ensurepip >> "%LOG%" 2>&1
.venv\Scripts\python.exe -m pip install -q --disable-pip-version-check -r requirements-playground.txt >> "%LOG%" 2>&1
if errorlevel 1 (
  if defined UVEXE (!UVEXE! pip install --python .venv\Scripts\python.exe -r requirements-playground.txt >> "%LOG%" 2>&1)
)
.venv\Scripts\python.exe -c "import fastapi, uvicorn, streamlit" >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [X] Package install failed. Details in start_log.txt
  type "%LOG%"
  pause
  exit /b 1
)
echo Packages OK >> "%LOG%"

REM ---------- 3) Start ----------
taskkill /F /T /FI "WINDOWTITLE eq Junior Hub*" >nul 2>&1
set API_PORT=8010
start "Junior Hub API" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --reload --reload-dir app --reload-dir prompts --timeout-graceful-shutdown 2 --port %API_PORT% > api_log.txt 2>&1"
timeout /t 6 >nul
set PYTHONPATH=%~dp0
set DISCOVERY_URL=http://127.0.0.1:%API_PORT%
start "Junior Hub Playground" cmd /k ".venv\Scripts\python.exe -m streamlit run playground\streamlit_app.py --server.headless true --server.port 8501 > ui_log.txt 2>&1"
echo Started >> "%LOG%"
echo.
echo API:        http://127.0.0.1:%API_PORT%/docs
echo Playground: http://localhost:8501
echo CALL PAGE:  http://127.0.0.1:%API_PORT%/call/
start "" http://127.0.0.1:%API_PORT%/call/
timeout /t 8
