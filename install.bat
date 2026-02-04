@echo off
SETLOCAL EnableDelayedExpansion
title DaSiWa ComfyUI - Bootstrapper

:: 1. Ensure we are in the correct directory
cd /d "%~dp0"

echo.
echo ===========================================
echo    DaSiWa ComfyUI Installer Bootstrapper
echo ===========================================
echo.

:: 2. Download the latest installer engine from GitHub
:: This ensures the user always runs the most up-to-date logic
echo [INFO] Downloading latest installer engine...
powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/darksidewalker/dasiwa-comfyui-installer/main/setup_logic.py' -OutFile 'setup_logic.py'"

:: 3. Launch the Python Script
:: If Python is missing, the user will see a command error, 
:: or Windows will prompt them. 
python setup_logic.py

if %errorlevel% neq 0 (
    echo.
    echo [!] An error occurred during the installation process.
    pause
)
