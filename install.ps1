# --- install.ps1 ---

# 1. FORCE ADMIN (The part that prevents the 'instant close')
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "[i] Requesting Admin rights..." -ForegroundColor Cyan
    Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

# 2. FIX LOCATION (Crucial after elevation)
Set-Location $PSScriptRoot

Write-Host "=== DaSiWa ComfyUI Bootstrapper ===" -ForegroundColor Green

# 3. PYTHON LOGIC (Check and Install)
$pyOfficial = "C:\Program Files\Python312\python.exe"
if (!(Test-Path $pyOfficial)) {
    Write-Host "[!] Python 3.12 not found. Installing..." -ForegroundColor Yellow
    $url = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
    Invoke-WebRequest -Uri $url -OutFile "py_fix.exe"
    Start-Process "py_fix.exe" -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1" -Wait
    Remove-Item "py_fix.exe"
}

# 4. DOWNLOAD PYTHON LOGIC & UTILS
Write-Host "[*] Downloading core files..." -ForegroundColor Cyan

# Ensure the utils directory exists
if (!(Test-Path "utils")) { New-Item -ItemType Directory -Path "utils" }

# Target branch (change to 'testing' if needed)
$branch = "main"
$baseUrl = "https://raw.githubusercontent.com/darksidewalker/dasiwa-comfyui-installer/$branch"

# Download the main logic
Invoke-WebRequest -Uri "$baseUrl/setup_logic.py" -OutFile "setup_logic.py"

# Download the utilities
Invoke-WebRequest -Uri "$baseUrl/utils/logger.py" -OutFile "utils/logger.py"
Invoke-WebRequest -Uri "$baseUrl/utils/reporter.py" -OutFile "utils/reporter.py"

# Create empty __init__.py so Python treats the folder as a package
if (!(Test-Path "utils/__init__.py")) { New-Item -ItemType File -Path "utils/__init__.py" }

# 5. RUN IT
Write-Host "[+] Starting Installer..." -ForegroundColor Green
& "C:\Program Files\Python312\python.exe" "setup_logic.py"

Write-Host "Installation script finished."
Pause
