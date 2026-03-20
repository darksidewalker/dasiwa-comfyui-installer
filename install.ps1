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
$localConfigPath = Join-Path $BaseDir "config.local.json"

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

# --- MERGE LOCAL CONFIG LOGIC ---
# Reload config objects to ensure we have the files synced from the ZIP
$config = Get-Content $configPath -Raw | ConvertFrom-Json

if (Test-Path $localConfigPath) {
    Write-Host "[*] Applying local configuration overrides for Python acquisition..." -ForegroundColor Magenta
    $localConfig = Get-Content $localConfigPath -Raw | ConvertFrom-Json
    
    if ($null -ne $localConfig.python) {
        if ($null -ne $localConfig.python.display_name) { $config.python.display_name = $localConfig.python.display_name }
        if ($null -ne $localConfig.python.full_version) { $config.python.full_version = $localConfig.python.full_version }
    }
}

$targetVer = $config.python.display_name
if (-not $targetVer) { $targetVer = "3.12" } 

Write-Host "[*] Ensuring Portable Python $targetVer via UV..." -ForegroundColor Cyan
& uv python install $targetVer

# Capture only the last line of output to avoid "Already installed" messages polluting the path
$uvPathOutput = & uv python find $targetVer
$finalPyPath = ($uvPathOutput | Select-Object -Last 1).Trim().Trim('"')

# 5. Final Execution
if ($null -ne $finalPyPath -and (Test-Path $finalPyPath)) {
    Write-Host "[+] Launching Setup Logic with Python $targetVer..." -ForegroundColor Green
    # Execute setup_logic.py using the specific python executable found by UV
    & $finalPyPath "setup_logic.py"
} else {
    Write-Host "[-] ERROR: Could not find or install Python $targetVer. Path: $finalPyPath" -ForegroundColor Red
    Pause
}