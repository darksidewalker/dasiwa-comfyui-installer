# --- install.ps1 ---
Set-Location $PSScriptRoot

Write-Host "==========================================" -ForegroundColor Green
Write-Host "=== DaSiWa ComfyUI Installer (Windows) ===" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green

# 1. Configuration & Download
# Updated to testing branch for your current testing phase
$repoZip = "https://github.com/darksidewalker/dasiwa-comfyui-installer/archive/refs/heads/testing.zip"
$zipFile = "repo.zip"
$tempFolder = "temp_extract"

Write-Host "[*] Downloading latest components from testing branch..." -ForegroundColor Cyan
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest -Uri $repoZip -OutFile $zipFile

# 2. Extract
if (Test-Path $tempFolder) { Remove-Item $tempFolder -Recurse -Force }
Expand-Archive -Path $zipFile -DestinationPath $tempFolder

# 3. Smart Move & Overwrite (Safety Enhanced)
$innerFolder = Get-ChildItem -Path $tempFolder | Where-Object { $_.PSIsContainer } | Select-Object -First 1

# SAFETY GUARD: Ensure we actually found a folder inside the zip
if ($null -eq $innerFolder -or $innerFolder.Name -eq "") {
    Write-Host "[!] Error: Failed to locate extracted source folder." -ForegroundColor Red
    Pause
    exit
}

Write-Host "[*] Updating files from $($innerFolder.Name)..." -ForegroundColor Gray
Get-ChildItem -Path $innerFolder.FullName | ForEach-Object {
    $target = Join-Path $PSScriptRoot $_.Name
    if (Test-Path $target) {
        Remove-Item $target -Recurse -Force
    }
    Move-Item -Path $_.FullName -Destination $PSScriptRoot -Force
}

# 4. Cleanup Zip files
Remove-Item $zipFile -Force
Remove-Item $tempFolder -Recurse -Force

# 5. Load Config
if (Test-Path "config.json") {
    $config = Get-Content "config.json" | ConvertFrom-Json
    $pyShort = $config.python.short_version
    $pyDisplay = $config.python.display_name
} else {
    $pyShort = "312"
    $pyDisplay = "3.12"
}

# 6. Smart Python Search
$searchPaths = @(
    "$env:ProgramFiles\Python$pyShort\python.exe",
    "$env:LocalAppData\Programs\Python\Python$pyShort\python.exe",
    "C:\Python$pyShort\python.exe",
    "$(Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)",
    "$(Get-Command python3 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)"
)

$finalPyPath = $null
foreach ($path in $searchPaths) {
    if ($path -and (Test-Path $path)) {
        # Check if the path is the "Fake" Windows Store alias
        if ($path -like "*\Microsoft\WindowsApps\*") {
            Write-Host "[!] Skipping Windows Store alias: $path" -ForegroundColor Gray
            continue
        }
        
        # Verify it actually works by checking the version
        try {
            $ver = & $path --version 2>$null
            if ($lastExitCode -eq 0) {
                $finalPyPath = $path
                break
            }
        } catch {
            continue
        }
    }
}

$finalPyPath = $null
foreach ($path in $searchPaths) {
    if ($path -and (Test-Path $path)) {
        $finalPyPath = $path
        break
    }
}

# 7. Execute Logic
if ($finalPyPath) {
    Write-Host "[+] Using Python: $finalPyPath" -ForegroundColor Green
    # Passing branch argument to keep setup_logic informed
    & $finalPyPath "setup_logic.py" --branch "testing"
} else {
    Write-Host "[!] Python $pyDisplay not found." -ForegroundColor Red
    Write-Host "[*] Please install Python $pyDisplay and try again." -ForegroundColor Yellow
    Pause
}