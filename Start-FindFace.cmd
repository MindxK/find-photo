@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Please run Install-FindFace.ps1 first. See README.md.
  pause
  exit /b 1
)
echo Starting FindFace at http://127.0.0.1:8765
echo Keep this window open. Press Ctrl+C to stop.
".venv\Scripts\python.exe" run.py
pause
