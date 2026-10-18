@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
echo.
echo Get a key from https://elevenlabs.io/app/settings/api-keys  (needs Speech to Text permission)
set /p XKEY=Paste your ElevenLabs API key here then press Enter: 
if "!XKEY!"=="" (echo No key entered. & pause & exit /b 1)
powershell -NoProfile -Command "$k=$env:XKEY.Trim(); $c=Get-Content .env; if (-not ($c -match '^ELEVENLABS_API_KEY=')) { $c += 'ELEVENLABS_API_KEY=' }; if (-not ($c -match '^STT_PROVIDER=')) { $c += 'STT_PROVIDER=groq' }; $c -replace '^ELEVENLABS_API_KEY=.*', ('ELEVENLABS_API_KEY='+$k) -replace '^STT_PROVIDER=.*', 'STT_PROVIDER=elevenlabs' | Set-Content .env -Encoding utf8"
echo Saved. Speech-to-text now uses ElevenLabs Scribe v2 (Groq Whisper as backup).
echo Close the API window and run START_HERE.bat again.
pause
