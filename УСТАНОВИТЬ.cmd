@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
  if errorlevel 1 goto failure
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failure
if exist "frontend\dist\index.html" goto ready
pushd frontend
call npm ci --no-audit --no-fund
if errorlevel 1 (
  popd
  goto failure
)
call npm run build
if errorlevel 1 (
  popd
  goto failure
)
popd
:ready
echo.
echo Установка завершена. Откройте ЗАПУСТИТЬ.cmd.
exit /b 0
:failure
echo.
echo Установка не завершена. Проверьте Python 3.11+, Node.js 22+ и доступ к интернету.
pause
exit /b 1
