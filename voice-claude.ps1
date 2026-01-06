# Voice Claude Windows Launcher (PowerShell)
# Captures original working directory before changing to installation dir

# Save original working directory
$env:VOICE_CLAUDE_ORIGINAL_CWD = (Get-Location).Path

# Change to script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# Activate virtual environment and run
& ".\venv\Scripts\Activate.ps1"
python -u src\main.py @args
