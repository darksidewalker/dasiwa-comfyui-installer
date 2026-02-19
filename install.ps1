# --- install.ps1 (No-Git Version) ---
Set-Location $PSScriptRoot

Write-Host "=== DaSiWa ComfyUI Bootstrapper (Standalone) ===" -ForegroundColor Green

# 1. Configuration
$repoUrl = "https://github.com/darksidewalker/dasiwa-comfyui-installer/archive/refs/heads/main.zip"
$zipFile = "repo.zip"
$tempFolder = "temp_extract"

# 2. Download and Extract
Write-Host "[*] Downloading installer components..." -ForegroundColor Cyan
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest -Uri $repoUrl -OutFile $zipFile

Write-Host "[*] Extracting files..." -ForegroundColor Cyan
if (Test-Path $tempFolder) { Remove-Item $tempFolder -Recurse -Force }
Expand-Archive -Path $zipFile -DestinationPath $tempFolder

# 3. Move files to current directory
# GitHub zips put everything inside a folder named 'repo-name-branch'
$extractedInner = Get-ChildItem -Path $tempFolder | Select-Object -First 1
Get-ChildItem -Path $extractedInner.FullName | ForEach-Object {
    Move-Item -Path $_.FullName -Destination $PSScriptRoot -Force
}

# 4. Cleanup
Remove-Item $zipFile -Force
Remove-Item $tempFolder -Recurse -Force

# 5. Launch
$pyPath = "C:\Program Files\Python312\python.exe"
if (Test-Path $pyPath) {
    & $pyPath "setup_logic.py"
} else {
    Write-Host "[!] Python 3.12 not found. Please run this script again after Python installs." -ForegroundColor Yellow
    # (Insert your Python installation logic here if not already handled)
}
