# Voice Claude Installer for Windows PowerShell
# Requires: Windows 10/11, PowerShell 5.1+

$ErrorActionPreference = "Stop"

$RepoUrl = "https://github.com/iwebercodes/voice-claude"
$InstallDir = "$env:USERPROFILE\.voice-claude"
$MinPythonVersion = [version]"3.10"

function Write-Info { param($Message) Write-Host "[INFO] " -ForegroundColor Green -NoNewline; Write-Host $Message }
function Write-Warn { param($Message) Write-Host "[WARN] " -ForegroundColor Yellow -NoNewline; Write-Host $Message }
function Write-Err { param($Message) Write-Host "[ERROR] " -ForegroundColor Red -NoNewline; Write-Host $Message; exit 1 }

function Test-PythonVersion {
    Write-Info "Checking Python installation..."

    # Try py launcher first (recommended on Windows), then python
    $pythonCmd = $null

    if (Get-Command "py" -ErrorAction SilentlyContinue) {
        $pythonCmd = "py"
        $versionOutput = & py --version 2>&1
    }
    elseif (Get-Command "python" -ErrorAction SilentlyContinue) {
        $pythonCmd = "python"
        $versionOutput = & python --version 2>&1
    }
    else {
        Write-Err "Python not found. Please install Python $MinPythonVersion or later from https://python.org"
    }

    # Parse version
    if ($versionOutput -match "Python (\d+\.\d+)") {
        $version = [version]$Matches[1]
        if ($version -lt $MinPythonVersion) {
            Write-Err "Python $version found, but $MinPythonVersion or later is required."
        }
        Write-Info "Found Python $version"
    }
    else {
        Write-Err "Could not determine Python version"
    }

    return $pythonCmd
}

function Test-ClaudeCode {
    Write-Info "Checking for Claude Code..."

    if (-not (Get-Command "claude" -ErrorAction SilentlyContinue)) {
        Write-Warn "Claude Code not found."
        Write-Host ""
        Write-Host "Voice Claude requires Claude Code to be installed."
        Write-Host "Install it with:"
        Write-Host ""
        Write-Host "  irm https://claude.ai/install.ps1 | iex" -ForegroundColor Cyan
        Write-Host ""

        $response = Read-Host "Would you like to install Claude Code now? [y/N]"
        if ($response -eq "y" -or $response -eq "Y") {
            Invoke-RestMethod https://claude.ai/install.ps1 | Invoke-Expression
            # Refresh PATH
            $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
        }
        else {
            Write-Warn "Continuing without Claude Code. You'll need to install it before using Voice Claude."
        }
    }
    else {
        Write-Info "Claude Code found"
    }
}

function Install-VoiceClaude {
    Write-Info "Installing Voice Claude..."

    if (Test-Path $InstallDir) {
        Write-Info "Updating existing installation..."
        Push-Location $InstallDir
        git fetch origin
        git reset --hard origin/master
        Pop-Location
    }
    else {
        Write-Info "Cloning repository..."
        git clone $RepoUrl $InstallDir
    }
}

function Initialize-Venv {
    param($PythonCmd)

    Write-Info "Setting up Python virtual environment..."

    Push-Location $InstallDir

    if (-not (Test-Path "venv")) {
        if ($PythonCmd -eq "py") {
            & py -m venv venv
        }
        else {
            & python -m venv venv
        }
    }

    # Activate and install dependencies
    & "$InstallDir\venv\Scripts\Activate.ps1"

    Write-Info "Installing Python dependencies..."
    pip install --upgrade pip
    pip install -r requirements.txt

    deactivate
    Pop-Location
}

function New-Launcher {
    Write-Info "Creating launcher script..."

    # Create batch launcher
    $launcherBat = @"
@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat
python -u src\main.py %*
"@
    Set-Content -Path "$InstallDir\voice-claude.bat" -Value $launcherBat

    # Create PowerShell launcher
    $launcherPs1 = @"
`$scriptDir = Split-Path -Parent `$MyInvocation.MyCommand.Path
Push-Location `$scriptDir
& ".\venv\Scripts\Activate.ps1"
python -u src\main.py @args
Pop-Location
"@
    Set-Content -Path "$InstallDir\voice-claude.ps1" -Value $launcherPs1

    # Add to PATH
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($userPath -notlike "*$InstallDir*") {
        Write-Info "Adding Voice Claude to PATH..."
        [Environment]::SetEnvironmentVariable("Path", "$userPath;$InstallDir", "User")
        $env:Path = "$env:Path;$InstallDir"
    }
}

function Main {
    Write-Host ""
    Write-Host "================================" -ForegroundColor Cyan
    Write-Host "  Voice Claude Installer" -ForegroundColor Cyan
    Write-Host "================================" -ForegroundColor Cyan
    Write-Host ""

    # Check for git
    if (-not (Get-Command "git" -ErrorAction SilentlyContinue)) {
        Write-Err "Git not found. Please install Git from https://git-scm.com"
    }

    $pythonCmd = Test-PythonVersion
    Test-ClaudeCode
    Install-VoiceClaude
    Initialize-Venv -PythonCmd $pythonCmd
    New-Launcher

    Write-Host ""
    Write-Host "================================" -ForegroundColor Cyan
    Write-Host "  Installation complete!" -ForegroundColor Green
    Write-Host "================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Run Voice Claude with:"
    Write-Host ""
    Write-Host "  voice-claude" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Or directly:"
    Write-Host ""
    Write-Host "  $InstallDir\voice-claude.bat" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Note: The first run will download the Whisper speech model (~500MB)."
    Write-Host ""
    Write-Host "You may need to restart your terminal for PATH changes to take effect."
    Write-Host ""
}

Main
