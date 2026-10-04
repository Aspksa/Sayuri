@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  where py >nul 2>&1
  if %errorlevel%==0 (py -3 -m venv .venv) else (python -m venv .venv)
  if errorlevel 1 (echo Python 3.10+ required&pause&exit /b 1)
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (echo Dependency install failed&pause&exit /b 1)
if not exist ".env" copy ".env.example" ".env" >nul
echo Opening Sayuri at http://127.0.0.1:8765
start "" "http://127.0.0.1:8765"
".venv\Scripts\python.exe" run.py
pause
