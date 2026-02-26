# --- install.ps1 ---
Set-Location $PSScriptRoot

Write-Host "==========================================" -ForegroundColor Green
Write-Host "=== DaSiWa ComfyUI Installer (Windows) ===" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green

# 1. Download Testing Branch Components
$repoZip = "https://github.com/darksidewalker/dasiwa-comfyui-installer/archive/refs/heads/main.zip"
$zipFile = "repo.zip"
$tempFolder = "temp_extract"

Write-Host "[*] Downloading components (Testing Branch)..." -ForegroundColor Cyan
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest -Uri $repoZip -OutFile $zipFile

# 2. Extract and Sync
if (Test-Path $tempFolder) { Remove-Item $tempFolder -Recurse -Force }
Expand-Archive -Path $zipFile -DestinationPath $tempFolder
$innerFolder = Get-ChildItem -Path $tempFolder | Where-Object { $_.PSIsContainer } | Select-Object -First 1

Write-Host "[*] Syncing files..." -ForegroundColor Gray
Get-ChildItem -Path $innerFolder.FullName | ForEach-Object {
    $target = Join-Path $PSScriptRoot $_.Name
    if (Test-Path $target) { Remove-Item $target -Recurse -Force }
    Move-Item -Path $_.FullName -Destination $PSScriptRoot -Force
}
Remove-Item $zipFile, $tempFolder -Recurse -Force

# 3. UV & Portable Python Acquisition (STRICT VERSION)
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "[*] UV not found. Installing UV..." -ForegroundColor Cyan
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path += ";$env:USERPROFILE\.cargo\bin;$env:AppData\Roaming\uv\bin"
}

# Load version from config.json
$targetVer = $null
if (Test-Path "config.json") {
    $config = Get-Content "config.json" -Raw | ConvertFrom-Json
    $targetVer = $config.python.display_name
}

if (-not $targetVer) {
    Write-Host "[-] ERROR: No Python version (display_name) found in config.json!" -ForegroundColor Red
    Pause; exit
}

Write-Host "[*] Fetching Portable Python $targetVer via UV..." -ForegroundColor Cyan
& uv python install $targetVer
$finalPyPath = (& uv python find $targetVer).Trim()

# 4. Final Execution
if (Test-Path $finalPyPath) {
    Write-Host "[+] Launching Setup Logic..." -ForegroundColor Green
    & $finalPyPath "setup_logic.py" --branch "testing"
} else {
    Write-Host "[-] ERROR: UV failed to provide Python $targetVer." -ForegroundColor Red
    Pause
}