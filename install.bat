@echo off
SETLOCAL EnableDelayedExpansion
title DaSiWa ComfyUI - Bootstrapper
cd /d "%~dp0"

echo [INFO] Fetching latest installer logic...

:: Always download the newest PS1 to ensure portable logic is up to date
powershell -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/darksidewalker/dasiwa-comfyui-installer/main/install.ps1' -OutFile 'install.ps1'"

if exist "install.ps1" (
    echo [INFO] Starting Installation...
    :: We run the newly downloaded PS1
    powershell -NoProfile -ExecutionPolicy Bypass -File "install.ps1"
) else (
    echo [!] Failed to download installer components. Check your internet connection.
    pause
    exit /b
)

:: Clean up the temporary PS1 after execution so the next run is fresh [cite: 2]
if exist "install.ps1" del "install.ps1"
exit