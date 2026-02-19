@echo off
SETLOCAL EnableDelayedExpansion
title DaSiWa ComfyUI - Bootstrapper

:: 1. Download the PowerShell Script
echo [INFO] Fetching latest bootstrapper...
powershell -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/darksidewalker/dasiwa-comfyui-installer/main/install.ps1' -OutFile 'install.ps1'"

:: 2. Run the PowerShell Script
if exist "install.ps1" (
    :: We use %~dp0 to ensure the path is absolute and correct even if run as Admin
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
) else (
    echo [!] Failed to download installer components.
    pause
    exit /b
)

:: 3. Cleanup
:: It is better to delete it so the next time you run the .bat, 
:: it's forced to grab the newest version from GitHub.
if exist "install.ps1" del "install.ps1"
exit
