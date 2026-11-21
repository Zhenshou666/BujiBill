@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo   Starting app + public tunnel...
echo.
".venv\Scripts\python.exe" "tools\share_online.py"
echo.
echo   Stopped.
pause
