@echo off
SETLOCAL EnableDelayedExpansion
title ComfyUI Installer Wrapper

echo ===========================================
echo    ComfyUI Prerequisites Check (Windows)
echo ===========================================

:check_git
where git >nul 2>nul
if %errorlevel% neq 0 (
    echo [!] Git wurde nicht gefunden.
    set /p install_git="Moechtest du Git via winget installieren? (j/n): "
    if /i "!install_git!"=="j" (
        winget install --id Git.Git -e --source winget
        echo Bitte starte dieses Script nach der Installation neu.
        pause & exit
    ) else (
        echo Bitte installiere Git manuell: https://git-scm.com/
        pause & exit
    )
)

:check_python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [!] Python wurde nicht gefunden.
    set /p install_py="Moechtest du Python 3.12 via winget installieren? (j/n): "
    if /i "!install_py!"=="j" (
        winget install --id Python.Python.3.12 -e --source winget
        echo Bitte starte dieses Script nach der Installation neu.
        pause & exit
    ) else (
        echo Bitte installiere Python 3.12 manuell.
        pause & exit
    )
)

echo [+] Voraussetzungen erfuellt.
python install_comfyui.py
pause
