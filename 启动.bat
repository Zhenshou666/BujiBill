@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo   正在启动「不记账本」...
echo.
".venv\Scripts\python.exe" -m streamlit run app.py
echo.
echo   已经退出了。如果上面有红色报错，截图发我。
pause
