@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  call INSTALL.cmd
  if errorlevel 1 exit /b 1
)
echo.
echo AI Office: http://127.0.0.1:4197
echo Keep this server window open. Press Ctrl+C to stop.
echo.
".venv\Scripts\python.exe" -m uvicorn backend.main:app --host 127.0.0.1 --port 4197
if errorlevel 1 pause
