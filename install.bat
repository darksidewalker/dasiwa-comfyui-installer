@echo off
SETLOCAL EnableDelayedExpansion
title DaSiWa ComfyUI - Absolute Bootstrapper

:: --- 1. SELF-ELEVATION BLOCK ---
:: Check for Admin rights using 'net session'
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [i] Requesting Administrator rights...
    :: This line creates a temporary VBScript to relaunch this BAT as Admin
    powershell -Command "Start-Process -FilePath '%0' -Verb RunAs"
    exit /b
)

:: --- 2. REST OF YOUR SCRIPT ---
:: Once we reach here, we are definitely Admin.
:: We must fix the directory context because 'RunAs' often starts in C:\Windows\System32
cd /d "%~dp0"

set "PY_OFFICIAL=C:\Program Files\Python312\python.exe"
set "PY_USER=%LocalAppData%\Programs\Python\Python312\python.exe"

echo [*] Verified Administrator Rights.
echo [*] Working Directory: %cd%

:: Check if a REAL Python exists
if exist "!PY_OFFICIAL!" (
    set "PYTHON_EXE=!PY_OFFICIAL!"
) else if exist "!PY_USER!" (
    set "PYTHON_EXE=!PY_USER!"
) else (
    echo [!] Real Python 3.12 not detected.
    echo [i] Starting official bypass installation...
    powershell -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe' -OutFile 'py_fix.exe'"
    
    echo [i] Running installer... Please wait.
    start /wait py_fix.exe /quiet InstallAllUsers=1 PrependPath=1 Include_test=0
    del py_fix.exe
    
    :: Re-check after install
    if exist "C:\Program Files\Python312\python.exe" (
        set "PYTHON_EXE=C:\Program Files\Python312\python.exe"
    ) else (
        echo [!] Installation failed. Please install Python 3.12 manually.
        pause & exit
    )
)

:: Download logic and run
echo [INFO] Updating setup_logic.py...
powershell -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/darksidewalker/dasiwa-comfyui-installer/main/setup_logic.py' -OutFile 'setup_logic.py'"

"!PYTHON_EXE!" setup_logic.py
pause
