# --- install.ps1 ---
Set-Location $PSScriptRoot

Write-Host "=== DaSiWa ComfyUI Bootstrapper ===" -ForegroundColor Green

$repoUrl = "https://github.com/darksidewalker/dasiwa-comfyui-installer/archive/refs/heads/main.zip"
$zipFile = "repo.zip"
$tempFolder = "temp_extract"

# 1. Download
Write-Host "[*] Downloading latest components..." -ForegroundColor Cyan
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest -Uri $repoUrl -OutFile $zipFile

# 2. Extract
if (Test-Path $tempFolder) { Remove-Item $tempFolder -Recurse -Force }
Expand-Archive -Path $zipFile -DestinationPath $tempFolder

# 3. Move files out of the nested zip folder
$innerFolder = Get-ChildItem -Path $tempFolder | Select-Object -First 1
Get-ChildItem -Path $innerFolder.FullName | ForEach-Object {
    $target = Join-Path $PSScriptRoot $_.Name
    
    # If the target is a directory and already exists, we must remove it first
    if (Test-Path $target) {
        Remove-Item $target -Recurse -Force
    }
    
    Move-Item -Path $_.FullName -Destination $PSScriptRoot -Force
}

# 4. Cleanup
Remove-Item $zipFile -Force
Remove-Item $tempFolder -Recurse -Force

# 5. Execute Logic
$pyPath = "C:\Program Files\Python312\python.exe"
if (Test-Path $pyPath) {
    # We run setup_logic.py which will then ask the user for the install path
    & $pyPath "setup_logic.py"
} else {
    Write-Host "[!] Python 3.12 not found at $pyPath" -ForegroundColor Red
    Pause
}
