@echo off
SETLOCAL EnableDelayedExpansion
title DaSiWa ComfyUI - Absolute Bootstrapper

:: 1. Define the real Python path we want
set "PY_OFFICIAL=C:\Program Files\Python312\python.exe"
set "PY_USER=%LocalAppData%\Programs\Python\Python312\python.exe"

:: 2. Check if a REAL Python exists (Bypassing MS Store aliases)
if exist "!PY_OFFICIAL!" (
    set "PYTHON_EXE=!PY_OFFICIAL!"
) else if exist "!PY_USER!" (
    set "PYTHON_EXE=!PY_USER!"
) else (
    echo [!] Real Python 3.12 not detected.
    echo [i] Starting official bypass installation...
    powershell -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe' -OutFile 'py_fix.exe'; Start-Process 'py_fix.exe' -ArgumentList '/quiet InstallAllUsers=1 PrependPath=1' -Wait; Remove-Item 'py_fix.exe'"
    
    :: Re-check after install
    if exist "C:\Program Files\Python312\python.exe" (
        set "PYTHON_EXE=C:\Program Files\Python312\python.exe"
    ) else (
        echo [!] Installation failed. Please install Python 3.12 from python.org manually.
        pause & exit
    )
)

:: 3. Download the logic script
echo [INFO] Updating setup_logic.py...
powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/darksidewalker/dasiwa-comfyui-installer/main/setup_logic.py' -OutFile 'setup_logic.py'"

:: 4. Run using the verified physical path
"!PYTHON_EXE!" setup_logic.py
pause
