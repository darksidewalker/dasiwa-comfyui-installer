@echo off
SETLOCAL EnableDelayedExpansion
title DaSiWa ComfyUI Installer

cls
echo.
echo ===========================================
echo    Welcome to the DaSiWa ComfyUI Installer
echo ===========================================
echo.

:: Section 1: Set Installation Path
set "DefaultPath=%cd%"
echo Where would you like to install ComfyUI?
echo.
echo Current path: %DefaultPath%
echo.
echo Press ENTER to use the current path.
echo Or, enter a full path (e.g., D:\ComfyUI) and press ENTER.
echo.
set /p "InstallPath=Enter installation path: "
if "%InstallPath%"=="" set "InstallPath=%DefaultPath%"
if "%InstallPath:~-1%"=="\" set "InstallPath=%InstallPath:~0,-1%"

echo.
echo [INFO] Target directory: %InstallPath%
echo.

:: Section 2: Prerequisites
:check_git
where git >nul 2>nul
if %errorlevel% neq 0 (
    echo [!] Git not found.
    set /p install_git="Install Git via winget? (y/n): "
    if /i "!install_git!"=="y" (
        winget install --id Git.Git -e --source winget
        echo Please restart this script after installation. & pause & exit
    ) else ( exit )
)

:check_python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [!] Python not found.
    set /p install_py="Install Python 3.12 via winget? (y/n): "
    if /i "!install_py!"=="y" (
        winget install --id Python.Python.3.12 -e --source winget
        echo Please restart this script after installation. & pause & exit
    ) else ( exit )
)

:: Section 3: Launch Python Wrapper
cd /d "%InstallPath%"
if not exist install_comfyui.py (
    echo [INFO] Downloading installer engine...
    powershell -Command "Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/darksidewalker/dasiwa-comfyui-installer/main/install_comfyui.py' -OutFile 'install_comfyui.py'"
)

python install_comfyui.py
pause
