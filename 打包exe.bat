@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem 版本名：改这一行就行，exe / 文件夹 / zip 会一起用这个名字
set NAME=不记账本beta1
echo.
echo   building Windows desktop app (2-3 min) ...
echo.
if exist "dist\%NAME%" rmdir /s /q "dist\%NAME%"
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --onedir --windowed --name "%NAME%" ^
  --add-data "app.py;." ^
  --add-data "billkit;billkit" ^
  --add-data "ui;ui" ^
  --add-data "static;static" ^
  --add-data "data/rules.json;data" ^
  --add-data ".streamlit;.streamlit" ^
  --add-data "tools/campus_grab.js;tools" ^
  --collect-all streamlit ^
  --collect-all plotly ^
  --collect-all streamlit_sortables ^
  launcher.py
echo.
echo   making zip ...
".venv\Scripts\python.exe" tools\make_zip.py "%NAME%"
echo.
echo   Done. Output in the dist folder:
echo     %NAME%.exe
echo     %NAME%.zip
echo.
pause
