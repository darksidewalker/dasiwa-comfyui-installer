# --- install.ps1 (Web-Ready Bootstrapper) ---

# 1. Handle Execution Environment
$BaseDir = if ($null -ne $PSScriptRoot -and $PSScriptRoot -ne "") { $PSScriptRoot } else { Get-Location }
Set-Location $BaseDir

Write-Host "==========================================" -ForegroundColor Green
Write-Host "=== DaSiWa ComfyUI Installer (Windows) ===" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green

# 2. Define Paths and Constants
$zipFile = Join-Path $BaseDir "repo.zip"
$tempFolder = Join-Path $BaseDir "temp_extract"
$configPath = Join-Path $BaseDir "config.json"

# Logic: Ensure config exists to get the zip_url
if (-not (Test-Path $configPath)) {
    Write-Host "[*] config.json missing, fetching defaults..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri "https://raw.githubusercontent.com/darksidewalker/dasiwa-comfyui-installer/main/config.json" -OutFile $configPath
}

try {
    $config = Get-Content $configPath -Raw | ConvertFrom-Json
    $repoZip = $config.repository.zip_url
} catch {
    $repoZip = "https://github.com/darksidewalker/dasiwa-comfyui-installer/archive/refs/heads/main.zip"
}

# 3. Download and Extract
Write-Host "[*] Downloading installer components..." -ForegroundColor Cyan
try {
    Invoke-WebRequest -Uri $repoZip -OutFile $zipFile -ErrorAction Stop
} catch {
    Write-Host "[-] FATAL: Could not download installer. Check your internet." -ForegroundColor Red
    Pause; exit
}

if (Test-Path $tempFolder) { Remove-Item $tempFolder -Recurse -Force }

Write-Host "[*] Extracting..." -ForegroundColor Gray
Expand-Archive -Path $zipFile -DestinationPath $tempFolder -Force

$innerFolder = Get-ChildItem -Path $tempFolder | Where-Object { $_.PSIsContainer } | Select-Object -First 1

if ($null -ne $innerFolder) {
    Write-Host "[*] Syncing files to root..." -ForegroundColor Gray
    Get-ChildItem -Path $innerFolder.FullName | ForEach-Object {
        $target = Join-Path $BaseDir $_.Name
        # Don't overwrite the running script or the batch file to avoid lock errors
        if ($_.Name -ne "install.ps1" -and $_.Name -ne "install.bat") {
            if (Test-Path $target) { Remove-Item $target -Recurse -Force }
            Move-Item -Path $_.FullName -Destination $BaseDir -Force
        }
    }
}

# Cleanup temp files
if (Test-Path $zipFile) { Remove-Item $zipFile -Force }
if (Test-Path $tempFolder) { Remove-Item $tempFolder -Recurse -Force }

# 4. UV & Portable Python Acquisition
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "[*] Installing UV (Standalone)..." -ForegroundColor Cyan
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path += ";$env:USERPROFILE\.cargo\bin;$env:AppData\Roaming\uv\bin"
}

# Refresh config object after extraction to ensure we have the latest
$config = Get-Content $configPath -Raw | ConvertFrom-Json
$targetVer = $config.python.display_name
if (-not $targetVer) { $targetVer = "3.12" } 

Write-Host "[*] Ensuring Portable Python $targetVer via UV..." -ForegroundColor Cyan
& uv python install $targetVer
$finalPyPath = (& uv python find $targetVer).Trim()

# 5. Final Execution
if (Test-Path $finalPyPath) {
    Write-Host "[+] Launching Setup Logic..." -ForegroundColor Green
    # branch "master" for the official ComfyUI repo
    & $finalPyPath "setup_logic.py" --branch "master"
} else {
    Write-Host "[-] ERROR: UV could not locate Python $targetVer." -ForegroundColor Red
    Pause
}