# --- install.ps1 (Web-Ready Bootstrapper) ---

# 1. Handle Execution Environment
# When running via 'iex', $PSScriptRoot is null. Fallback to current directory ($PWD).
$BaseDir = if ($null -ne $PSScriptRoot -and $PSScriptRoot -ne "") { $PSScriptRoot } else { Get-Location }
[cite_start]Set-Location $BaseDir [cite: 2]

Write-Host "==========================================" -ForegroundColor Green
Write-Host "=== DaSiWa ComfyUI Installer (Windows) ===" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green

# 2. Define Paths and Constants using $BaseDir
[cite_start]$zipFile = Join-Path $BaseDir "repo.zip" [cite: 2]
[cite_start]$tempFolder = Join-Path $BaseDir "temp_extract" [cite: 2]
[cite_start]$configPath = Join-Path $BaseDir "config.json" [cite: 2]

# Logic: If config exists, use its zip_url. Otherwise, use hardcoded fallback.
if (Test-Path $configPath) {
    try {
        $config = Get-Content $configPath -Raw | [cite_start]ConvertFrom-Json [cite: 2]
        [cite_start]$repoZip = $config.repository.zip_url [cite: 2]
    } catch {
        [cite_start]$repoZip = "https://github.com/darksidewalker/dasiwa-comfyui-installer/archive/refs/heads/main.zip" [cite: 2]
    }
} else {
    [cite_start]$repoZip = "https://github.com/darksidewalker/dasiwa-comfyui-installer/archive/refs/heads/main.zip" [cite: 2]
}

# 3. Download and Extract
Write-Host "[*] Downloading installer components..." -ForegroundColor Cyan
try {
    [cite_start]Invoke-WebRequest -Uri $repoZip -OutFile $zipFile -ErrorAction Stop [cite: 2]
} catch {
    Write-Host "[-] FATAL: Could not download installer. Check your internet." -ForegroundColor Red
    Pause; exit
}

[cite_start]if (Test-Path $tempFolder) { Remove-Item $tempFolder -Recurse -Force } [cite: 2]

Write-Host "[*] Extracting..." -ForegroundColor Gray
[cite_start]Expand-Archive -Path $zipFile -DestinationPath $tempFolder -Force [cite: 2]

$innerFolder = Get-ChildItem -Path $tempFolder | Where-Object { $_.PSIsContainer } | [cite_start]Select-Object -First 1 [cite: 2]

if ($null -ne $innerFolder) {
    Write-Host "[*] Syncing files to root..." -ForegroundColor Gray
    Get-ChildItem -Path $innerFolder.FullName | ForEach-Object {
        [cite_start]$target = Join-Path $BaseDir $_.Name [cite: 2]
        if ($_.Name -ne "install.ps1" -and $_.Name -ne "install.bat") {
            [cite_start]if (Test-Path $target) { Remove-Item $target -Recurse -Force } [cite: 2]
            [cite_start]Move-Item -Path $_.FullName -Destination $BaseDir -Force [cite: 2]
        }
    }
}

[cite_start]Remove-Item $zipFile, $tempFolder -Recurse -Force [cite: 2]

# 4. UV & Portable Python Acquisition
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "[*] Installing UV (Standalone)..." -ForegroundColor Cyan
    [cite_start]powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex" [cite: 2]
    [cite_start]$env:Path += ";$env:USERPROFILE\.cargo\bin;$env:AppData\Roaming\uv\bin" [cite: 2]
}

$config = Get-Content $configPath -Raw | [cite_start]ConvertFrom-Json [cite: 2]
[cite_start]$targetVer = $config.python.display_name [cite: 2]
if (-not $targetVer) { $targetVer = "3.12" } 

Write-Host "[*] Ensuring Portable Python $targetVer via UV..." -ForegroundColor Cyan
[cite_start]& uv python install $targetVer [cite: 2]
[cite_start]$finalPyPath = (& uv python find $targetVer).Trim() [cite: 2]

# 5. Final Execution
if (Test-Path $finalPyPath) {
    Write-Host "[+] Launching Setup Logic..." -ForegroundColor Green
    # FIXED: Changed branch from "main" to "master" to match the official ComfyUI repo
    & $finalPyPath "setup_logic.py" --branch "master"
} else {
    Write-Host "[-] ERROR: UV could not locate Python $targetVer." -ForegroundColor Red
    [cite_start]Pause [cite: 2]
}