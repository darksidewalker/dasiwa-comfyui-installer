@echo off
SETLOCAL EnableDelayedExpansion
title DaSiWa ComfyUI - Absolute Bootstrapper

:: --- ADMIN ELEVATION CHECK ---
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [i] Requesting Administrator rights to handle Python installation...
    powershell -Command "Start-Process -FilePath '%0' -Verb RunAs"
    exit /b
)

:: 1. Define the real Python paths
set "PY_OFFICIAL=C:\Program Files\Python312\python.exe"
set "PY_USER=%LocalAppData%\Programs\Python\Python312\python.exe"

:: 2. Check if a REAL Python exists
if exist "!PY_OFFICIAL!" (
    set "PYTHON_EXE=!PY_OFFICIAL!"
) else if exist "!PY_USER!" (
    set "PYTHON_EXE=!PY_USER!"
) else (
    echo [!] Real Python 3.12 not detected.
    echo [i] Starting official bypass installation...
    
    :: Use -ExecutionPolicy Bypass and -Wait to ensure it finishes
    powershell -ExecutionPolicy Bypass -Command "Write-Host 'Downloading Python...'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe' -OutFile 'py_fix.exe'"
    
    echo [i] Running installer... Please wait.
    start /wait py_fix.exe /quiet InstallAllUsers=1 PrependPath=1 Include_test=0
    del py_fix.exe
    
    :: Re-check after install
    if exist "C:\Program Files\Python312\python.exe" (
        set "PYTHON_EXE=C:\Program Files\Python312\python.exe"
    ) else if exist "C:\Program Files\Python\Python312\python.exe" (
        set "PYTHON_EXE=C:\Program Files\Python\Python312\python.exe"
    ) else (
        echo [!] Installation failed. Please install Python 3.12 manually from python.org.
        pause & exit
    )
)

:: 3. Download the logic script
echo [INFO] Updating setup_logic.py...
powershell -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/darksidewalker/dasiwa-comfyui-installer/main/setup_logic.py' -OutFile 'setup_logic.py'"

:: 4. Run using the verified physical path
echo [!] Launching Setup Logic...
"!PYTHON_EXE!" setup_logic.py
pause
