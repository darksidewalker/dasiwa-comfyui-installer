# --- install.ps1 ---
Set-Location $PSScriptRoot

Write-Host "==========================================" -ForegroundColor Green
Write-Host "=== DaSiWa ComfyUI Installer (Windows) ===" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green

# 1. Configuration & Download
$repoZip = "https://github.com/darksidewalker/dasiwa-comfyui-installer/archive/refs/heads/testing.zip"
$zipFile = "repo.zip"
$tempFolder = "temp_extract"

Write-Host "[*] Downloading latest components from testing branch..." -ForegroundColor Cyan
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest -Uri $repoZip -OutFile $zipFile

# 2. Extract
if (Test-Path $tempFolder) { Remove-Item $tempFolder -Recurse -Force }
Expand-Archive -Path $zipFile -DestinationPath $tempFolder

# 3. Smart Move & Overwrite
$innerFolder = Get-ChildItem -Path $tempFolder | Where-Object { $_.PSIsContainer } | Select-Object -First 1

if ($null -eq $innerFolder -or $innerFolder.Name -eq "") {
    Write-Host "[!] Error: Failed to locate extracted source folder." -ForegroundColor Red
    Pause
    exit
}

Write-Host "[*] Updating files from $($innerFolder.Name)..." -ForegroundColor Gray
Get-ChildItem -Path $innerFolder.FullName | ForEach-Object {
    $target = Join-Path $PSScriptRoot $_.Name
    if (Test-Path $target) { Remove-Item $target -Recurse -Force }
    Move-Item -Path $_.FullName -Destination $PSScriptRoot -Force
}

# 4. Cleanup
Remove-Item $zipFile -Force
Remove-Item $tempFolder -Recurse -Force

# 5. Load Config & Determine Version
$targetVersion = $null

if (Test-Path "config.json") {
    try {
        $config = Get-Content "config.json" -Raw | ConvertFrom-Json
        # Directly use the display_name (e.g., "3.12")
        if ($config.python.display_name) {
            $targetVersion = $config.python.display_name
            Write-Host "[*] Target Python version from config: $targetVersion" -ForegroundColor Cyan
        }
    } catch {
        Write-Host "[-] ERROR: Failed to parse config.json." -ForegroundColor Red
        Pause
        exit
    }
}

# Strict Check: No version in config = No install
if (-not $targetVersion) {
    Write-Host "[-] ERROR: No compatible Python version (display_name) specified in config.json!" -ForegroundColor Red
    Pause
    exit
}

# 6. UV Bootstrapping
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "[*] UV not found. Installing UV (Standalone)..." -ForegroundColor Cyan
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    # Update current session path to ensure we can run 'uv' immediately
    $env:Path += ";$env:USERPROFILE\.cargo\bin;$env:AppData\Roaming\uv\bin"
}

# 7. Strict Python Acquisition via UV
Write-Host "[*] UV is ensuring Python $targetVersion is ready..." -ForegroundColor Cyan
try {
    # UV will look for "3.12" and install the best stable match
    & uv python install $targetVersion
} catch {
    Write-Host "[-] ERROR: UV could not install Python $targetVersion. This version may be invalid or unavailable." -ForegroundColor Red
    Pause
    exit
}

# Locate the UV-managed executable path
$finalPyPath = (& uv python find $targetVersion).Trim()

# 8. Final Execution
if ($finalPyPath -and (Test-Path $finalPyPath)) {
    Write-Host "[+] Using UV-Managed Python: $finalPyPath" -ForegroundColor Green
    & $finalPyPath "setup_logic.py" --branch "testing"
} else {
    Write-Host "[-] ERROR: No compatible Python $targetVersion found or installed." -ForegroundColor Red
    Pause
    exit
}