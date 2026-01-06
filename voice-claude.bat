@echo off
REM Voice Claude Windows Launcher
REM Captures original working directory before changing to installation dir

REM Save original working directory
set VOICE_CLAUDE_ORIGINAL_CWD=%CD%

REM Change to script directory
cd /d "%~dp0"

REM Activate virtual environment and run
call venv\Scripts\activate.bat
python -u src\main.py %*
