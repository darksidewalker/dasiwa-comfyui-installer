# --- install.ps1 ---
Set-Location $PSScriptRoot

Write-Host "==========================================" -ForegroundColor Green
Write-Host "=== DaSiWa ComfyUI Installer (Windows) ===" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green

# 1. Configuration & Download
$repoZip = "https://github.com/darksidewalker/dasiwa-comfyui-installer/archive/refs/heads/main.zip"
$zipFile = "repo.zip"
$tempFolder = "temp_extract"

Write-Host "[*] Downloading latest components..." -ForegroundColor Cyan
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest -Uri $repoZip -OutFile $zipFile

# 2. Extract
if (Test-Path $tempFolder) { Remove-Item $tempFolder -Recurse -Force }
Expand-Archive -Path $zipFile -DestinationPath $tempFolder

# 3. Smart Move & Overwrite (Ensures 'utils' and 'setup_logic' are moved correctly)
$innerFolder = Get-ChildItem -Path $tempFolder | Select-Object -First 1
Get-ChildItem -Path $innerFolder.FullName | ForEach-Object {
    $target = Join-Path $PSScriptRoot $_.Name
    if (Test-Path $target) {
        # Folders like 'utils' need to be deleted before Move-Item can "overwrite" them
        Remove-Item $target -Recurse -Force
    }
    Move-Item -Path $_.FullName -Destination $PSScriptRoot -Force
}

# 4. Cleanup Zip files
Remove-Item $zipFile -Force
Remove-Item $tempFolder -Recurse -Force

# 5. Load Config (Now that config.json has been moved to the root)
if (Test-Path "config.json") {
    $config = Get-Content "config.json" | ConvertFrom-Json
    $pyShort = $config.python.short_version
    $pyDisplay = $config.python.display_name
} else {
    # Hardcoded fallbacks if config.json is missing for some reason
    $pyShort = "312"
    $pyDisplay = "3.12"
}

# 6. Smart Python Search
$searchPaths = @(
    "$(Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)",
    "$env:ProgramFiles\Python$pyShort\python.exe",
    "$env:LocalAppData\Programs\Python\Python$pyShort\python.exe",
    "C:\Python$pyShort\python.exe"
)

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
    & $finalPyPath "setup_logic.py"
} else {
    Write-Host "[!] Python $pyDisplay not found." -ForegroundColor Red
    Write-Host "[*] Please install Python $pyDisplay and try again." -ForegroundColor Yellow
    Pause
}