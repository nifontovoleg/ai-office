@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -m venv .venv
if errorlevel 1 (
  echo Python 3.11 or newer is required and must be available in PATH.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo Installation failed. Check internet access and the output above.
  pause
  exit /b 1
)
echo Installation complete. Run START.cmd.
