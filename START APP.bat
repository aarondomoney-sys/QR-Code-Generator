@echo off
title Hugo Cars QR App
cd /d "%~dp0"

echo ================================================
echo   Hugo Cars QR Code App
echo ================================================
echo.

:: Check Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo Python not found. Please install it from https://www.python.org/downloads/
    echo Make sure to tick "Add Python to PATH" during install.
    pause
    exit
)

:: Install dependencies if needed
echo Checking dependencies...
pip install flask playwright qrcode[pil] Pillow apscheduler --quiet
python -m playwright install chromium --with-deps >nul 2>&1

:: Start the app
echo Starting Hugo Cars QR App...
start http://localhost:8080
python app.py
