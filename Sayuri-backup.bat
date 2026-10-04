@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Сначала запустите Sayuri.bat
  pause
  exit /b 1
)
".venv\Scripts\python.exe" backup.py
pause
