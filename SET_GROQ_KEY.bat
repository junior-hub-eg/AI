@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
REM ---------- 1) Groq key ----------
(
  echo.
  echo Get a key from https://console.groq.com/keys  ^(starts with gsk_^)
  set /p GKEY=Paste your Groq API key here then press Enter ^(or just Enter for fake mode^): 
  if not "!GKEY!"=="" (
    powershell -NoProfile -Command "$k=$env:GKEY.Trim(); (Get-Content .env) -replace '^GROQ_API_KEY=.*', ('GROQ_API_KEY='+$k) -replace '^FAKE_MODELS=\S+', 'FAKE_MODELS=false' | Set-Content .env -Encoding ascii"
    echo Key saved, real Groq mode ON. 
  ) else (
    echo No key, fake mode. 
  )
)

echo Done. Close the API window and run START_HERE.bat again.
pause
