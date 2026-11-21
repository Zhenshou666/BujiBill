@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo   Starting demo mode for classmates...
echo.
".venv\Scripts\python.exe" "tools\share_lan.py"
if errorlevel 1 (
  echo.
  echo   Failed to start. Check that .venv exists.
  pause
)
