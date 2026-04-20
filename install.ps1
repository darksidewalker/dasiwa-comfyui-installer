# --- install.ps1 ---

# 1. Handle Execution Environment
$BaseDir = if ($null -ne $PSScriptRoot -and $PSScriptRoot -ne "") { $PSScriptRoot } else { Get-Location }
Set-Location $BaseDir

$Interactive = ($Host.Name -eq 'ConsoleHost')

Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "=== DaSiWa ComfyUI Installer (Windows) ===" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""

function Exit-Installer($code) {
    if ($Interactive) { Pause }
    exit $code
}

# 2. Define Paths and Constants
$zipFile = Join-Path $BaseDir 'repo.zip'
$tempFolder = Join-Path $BaseDir 'temp_extract'
$configPath = Join-Path $BaseDir 'config.json'
$localConfigPath = Join-Path $BaseDir 'config.local.json'

# Ensure config exists to get the zip_url
if (-not (Test-Path $configPath)) {
    Write-Host '[*] config.json missing, fetching defaults...' -ForegroundColor Yellow
    try {
        Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/darksidewalker/dasiwa-comfyui-installer/main/config.json' -OutFile $configPath -ErrorAction Stop
    } catch {
        Write-Host '[-] FATAL: Could not fetch default config.json' -ForegroundColor Red
        Write-Host $_.Exception.Message -ForegroundColor Red
        Exit-Installer 1
    }
}

try {
    $config = Get-Content $configPath -Raw | ConvertFrom-Json
    $repoZip = $config.repository.zip_url
} catch {
    $repoZip = 'https://github.com/darksidewalker/dasiwa-comfyui-installer/archive/refs/heads/main.zip'
}

# 3. Download and Extract
Write-Host '[*] Downloading installer components...' -ForegroundColor Cyan
try {
    Invoke-WebRequest -Uri $repoZip -OutFile $zipFile -ErrorAction Stop
} catch {
    Write-Host '[-] FATAL: Could not download installer.' -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Exit-Installer 1
}

if (Test-Path $tempFolder) { Remove-Item $tempFolder -Recurse -Force }
Write-Host '[*] Extracting...' -ForegroundColor Gray
Expand-Archive -Path $zipFile -DestinationPath $tempFolder -Force

# Sync files to root
$innerFolder = Get-ChildItem -Path $tempFolder | Where-Object { $_.PSIsContainer } | Select-Object -First 1
if ($null -ne $innerFolder) {
    Write-Host '[*] Syncing files to root...' -ForegroundColor Gray
    Get-ChildItem -Path $innerFolder.FullName | ForEach-Object {
        $target = Join-Path $BaseDir $_.Name
        if ($_.Name -ne 'install.ps1' -and $_.Name -ne 'install.bat') {
            if (Test-Path $target) { Remove-Item $target -Recurse -Force }
            Move-Item -Path $_.FullName -Destination $BaseDir -Force
        }
    }
}

# Cleanup download artefacts
Remove-Item $zipFile -Force -ErrorAction SilentlyContinue
Remove-Item $tempFolder -Recurse -Force -ErrorAction SilentlyContinue

# 4. UV & Portable Python Acquisition
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host '[*] Installing UV...' -ForegroundColor Cyan
    try {
        powershell -ExecutionPolicy ByPass -c 'irm https://astral.sh/uv/install.ps1 | iex'
    } catch {
        Write-Host '[-] UV installer script failed.' -ForegroundColor Red
        Write-Host $_.Exception.Message -ForegroundColor Red
    }

    # UV can land in several locations depending on version and install method.
    # Build every candidate path with Join-Path to avoid string-interpolation issues.
    $uvCandidates = @(
        (Join-Path $env:USERPROFILE '.cargo\bin'),
        (Join-Path $env:USERPROFILE '.local\bin'),
        (Join-Path $env:LOCALAPPDATA 'uv\bin'),
        (Join-Path $env:LOCALAPPDATA 'Programs\uv')
    )
    foreach ($candidate in $uvCandidates) {
        if (Test-Path $candidate) {
            $env:Path = $candidate + ';' + $env:Path
        }
    }

    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Host '[-] FATAL: UV was installed but is not reachable on PATH.' -ForegroundColor Red
        Write-Host '    Close this terminal, open a new one, and re-run the installer.' -ForegroundColor Yellow
        Exit-Installer 1
    }
}

# --- LOCAL CONFIG MERGE ---
$config = Get-Content $configPath -Raw | ConvertFrom-Json
if (Test-Path $localConfigPath) {
    Write-Host '[*] Applying local configuration overrides...' -ForegroundColor Magenta
    try {
        $localConfig = Get-Content $localConfigPath -Raw | ConvertFrom-Json
        if ($null -ne $localConfig.python) {
            if ($null -ne $localConfig.python.display_name) {
                $config.python.display_name = $localConfig.python.display_name
            }
        }
    } catch {
        Write-Host '[!] Warning: Could not parse config.local.json - using defaults.' -ForegroundColor Yellow
    }
}

$targetVer = $config.python.display_name
Write-Host ('[*] Ensuring Portable Python ' + $targetVer + ' via UV...') -ForegroundColor Cyan
& uv python install $targetVer

$uvOutput = & uv python find $targetVer
$finalPyPath = ($uvOutput | Select-Object -Last 1).Trim().Trim('"')

# 5. Final Execution
if ($null -ne $finalPyPath -and (Test-Path $finalPyPath)) {
    Write-Host ('[+] Launching Setup Logic with: ' + $finalPyPath) -ForegroundColor Green
    & $finalPyPath 'setup_logic.py' --branch 'master'
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        Write-Host ('[-] Setup exited with code ' + $exitCode) -ForegroundColor Red
        Exit-Installer $exitCode
    }
} else {
    Write-Host ('[-] ERROR: UV could not locate Python ' + $targetVer) -ForegroundColor Red
    Exit-Installer 1
}
