@echo off
cd /d "%~dp0"
echo =================================
echo  Images to ePub / PDF - Web App
echo =================================
echo  Opening browser at http://127.0.0.1:5000
echo  Press Ctrl+C to stop the server.
echo.
python web\server.py
pause
