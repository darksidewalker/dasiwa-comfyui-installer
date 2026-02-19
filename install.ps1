# --- install.ps1 ---
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "[i] Requesting Admin rights..." -ForegroundColor Cyan
    Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}
Set-Location $PSScriptRoot

Write-Host "=== DaSiWa ComfyUI Bootstrapper ===" -ForegroundColor Green

# 1. Ensure Git is available
if (!(Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "[!] Git not found. Please install Git first." -ForegroundColor Red
    Pause; exit
}

# 2. Sync Repository (This gets setup_logic.py AND the utils folder)
$repoUrl = "https://github.com/darksidewalker/dasiwa-comfyui-installer.git"
if (!(Test-Path ".git")) {
    Write-Host "[*] Initializing Installer Repository..." -ForegroundColor Cyan
    git clone -b main $repoUrl .
} else {
    Write-Host "[*] Checking for Installer Updates..." -ForegroundColor Cyan
    git pull origin main
}

# 3. Python Check & Run
$pyPath = "C:\Program Files\Python312\python.exe"
if (!(Test-Path $pyPath)) {
    Write-Host "[!] Python 3.12 missing. Downloading..." -ForegroundColor Yellow
    Invoke-WebRequest "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe" -OutFile "py_fix.exe"
    Start-Process "py_fix.exe" -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1" -Wait
    Remove-Item "py_fix.exe"
}

& $pyPath "setup_logic.py"
Pause
