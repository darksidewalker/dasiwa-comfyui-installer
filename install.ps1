# --- install.ps1 (Improved Bootstrapper) ---
# Anchor the execution to the folder where this script actually sits
Set-Location $PSScriptRoot

Write-Host "==========================================" -ForegroundColor Green
Write-Host "=== DaSiWa ComfyUI Installer (Windows) ===" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green

# 1. Define Paths and Constants
$zipFile = Join-Path $PSScriptRoot "repo.zip"
$tempFolder = Join-Path $PSScriptRoot "temp_extract"
$configPath = Join-Path $PSScriptRoot "config.json"

# Revert logic: If config exists, use it. Otherwise, use hardcoded fallback.
if (Test-Path $configPath) {
    try {
        $config = Get-Content $configPath -Raw | ConvertFrom-Json
        $repoZip = $config.repository.zip_url
    } catch {
        $repoZip = "https://github.com/darksidewalker/dasiwa-comfyui-installer/archive/refs/heads/main.zip"
    }
} else {
    $repoZip = "https://github.com/darksidewalker/dasiwa-comfyui-installer/archive/refs/heads/main.zip"
}

# 2. Download and Extract
Write-Host "[*] Downloading installer components..." -ForegroundColor Cyan
try {
    Invoke-WebRequest -Uri $repoZip -OutFile $zipFile -ErrorAction Stop
} catch {
    Write-Host "[-] FATAL: Could not download installer. Check your internet." -ForegroundColor Red
    Pause; exit
}

# Clean temp extract folder if it exists from a failed previous run
if (Test-Path $tempFolder) { Remove-Item $tempFolder -Recurse -Force }

Write-Host "[*] Extracting..." -ForegroundColor Gray
Expand-Archive -Path $zipFile -DestinationPath $tempFolder -Force

# GitHub Zips contain an inner folder (repo-name-branch). Find it.
$innerFolder = Get-ChildItem -Path $tempFolder | Where-Object { $_.PSIsContainer } | Select-Object -First 1

if ($null -ne $innerFolder) {
    Write-Host "[*] Syncing files to root..." -ForegroundColor Gray
    Get-ChildItem -Path $innerFolder.FullName | ForEach-Object {
        $target = Join-Path $PSScriptRoot $_.Name
        
        # Avoid deleting the currently running script to prevent lock errors
        if ($_.Name -ne "install.ps1" -and $_.Name -ne "install.bat") {
            if (Test-Path $target) { Remove-Item $target -Recurse -Force }
            Move-Item -Path $_.FullName -Destination $PSScriptRoot -Force
        }
    }
}

# Cleanup zip and temp folder
Remove-Item $zipFile, $tempFolder -Recurse -Force

# 3. UV & Portable Python Acquisition
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "[*] Installing UV (Standalone)..." -ForegroundColor Cyan
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    # Force update the path for the current session
    $env:Path += ";$env:USERPROFILE\.cargo\bin;$env:AppData\Roaming\uv\bin"
}

# Now that we have synced files, config.json definitely exists
$config = Get-Content $configPath -Raw | ConvertFrom-Json
$targetVer = $config.python.display_name

if (-not $targetVer) { $targetVer = "3.12" } # Safety fallback

Write-Host "[*] Ensuring Portable Python $targetVer via UV..." -ForegroundColor Cyan
& uv python install $targetVer
$finalPyPath = (& uv python find $targetVer).Trim()

# 4. Final Execution
if (Test-Path $finalPyPath) {
    Write-Host "[+] Launching Setup Logic..." -ForegroundColor Green
    # Running setup_logic.py inside the absolute BASE_DIR
    & $finalPyPath "setup_logic.py" --branch "main"
} else {
    Write-Host "[-] ERROR: UV could not locate Python $targetVer." -ForegroundColor Red
    Pause
}