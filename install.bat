@echo off
SETLOCAL EnableDelayedExpansion
title ComfyUI Installer Wrapper

echo ===========================================
echo    ComfyUI Prerequisites Check (Windows)
echo ===========================================

:check_git
where git >nul 2>nul
if %errorlevel% neq 0 (
    echo [!] Git was not found.
    set /p install_git="Would you like to install Git via winget? (y/n): "
    if /i "!install_git!"=="y" (
        winget install --id Git.Git -e --source winget
        echo [!] Please restart this script after the installation is finished.
        pause & exit
    ) else (
        echo [!] Please install Git manually: https://git-scm.com/
        pause & exit
    )
)

:check_python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [!] Python was not found.
    set /p install_py="Would you like to install Python 3.12 via winget? (y/n): "
    if /i "!install_py!"=="y" (
        winget install --id Python.Python.3.12 -e --source winget
        echo [!] Please restart this script after the installation is finished.
        pause & exit
    ) else (
        echo [!] Please install Python 3.12 manually.
        pause & exit
    )
)

echo [+] Prerequisites met.
echo [*] Checking for installer script...

:: Check if the wrapper already exists, if not, download it
if not exist install_comfyui.py (
    echo [!] Installer wrapper not found locally. Downloading...
    powershell -Command "Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/darksidewalker/dasiwa-comfyui-installer/main/install_comfyui.py' -OutFile 'install_comfyui.py'"
)

python install_comfyui.py
pause
