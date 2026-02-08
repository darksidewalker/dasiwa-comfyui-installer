@echo off
SETLOCAL EnableDelayedExpansion
title DaSiWa ComfyUI - Bootstrapper

:: 1. Download the PowerShell Script
echo [INFO] Fetching installer components...
powershell -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/darksidewalker/dasiwa-comfyui-installer/main/install.ps1' -OutFile 'install.ps1'"

:: 2. Run the PowerShell Script
:: This handles elevation, Python installation, and the Python logic launch
if exist "install.ps1" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
) else (
    echo [!] Failed to download installer components. Check your internet connection.
    pause
)

:: 3. Cleanup (Optional: deletes the ps1 after running)
:: del install.ps1
exit
