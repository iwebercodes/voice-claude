@echo off
setlocal enabledelayedexpansion

:: Voice Claude Installer for Windows CMD
:: Requires: Windows 10/11, Git, Python 3.10+

set "REPO_URL=https://github.com/iwebercodes/voice-claude"
set "INSTALL_DIR=%USERPROFILE%\.voice-claude"
set "MIN_PYTHON=3.10"

echo.
echo ================================
echo   Voice Claude Installer
echo ================================
echo.

:: Check for git
where git >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Git not found. Please install Git from https://git-scm.com
    goto :error
)
echo [INFO] Git found

:: Check for Python
set "PYTHON_CMD="
where py >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=py"
    goto :check_version
)
where python >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=python"
    goto :check_version
)
echo [ERROR] Python not found. Please install Python %MIN_PYTHON% or later from https://python.org
goto :error

:check_version
echo [INFO] Checking Python version...
for /f "tokens=2" %%v in ('%PYTHON_CMD% --version 2^>^&1') do set "PYVER=%%v"
echo [INFO] Found Python %PYVER%

:: Check for Claude Code
echo [INFO] Checking for Claude Code...
where claude >nul 2>&1
if errorlevel 1 (
    echo [WARN] Claude Code not found.
    echo.
    echo Voice Claude requires Claude Code to be installed.
    echo Install it with:
    echo.
    echo   curl -fsSL https://claude.ai/install.cmd -o claude-install.cmd ^&^& claude-install.cmd
    echo.
    set /p "INSTALL_CLAUDE=Would you like to install Claude Code now? [y/N] "
    if /i "!INSTALL_CLAUDE!"=="y" (
        curl -fsSL https://claude.ai/install.cmd -o "%TEMP%\claude-install.cmd"
        call "%TEMP%\claude-install.cmd"
        del "%TEMP%\claude-install.cmd"
    ) else (
        echo [WARN] Continuing without Claude Code. You'll need to install it before using Voice Claude.
    )
) else (
    echo [INFO] Claude Code found
)

:: Clone or update repository
if exist "%INSTALL_DIR%" (
    echo [INFO] Updating existing installation...
    pushd "%INSTALL_DIR%"
    git fetch origin
    git reset --hard origin/master
    popd
) else (
    echo [INFO] Cloning repository...
    git clone %REPO_URL% "%INSTALL_DIR%"
)

:: Set up virtual environment
echo [INFO] Setting up Python virtual environment...
pushd "%INSTALL_DIR%"

if not exist "venv" (
    %PYTHON_CMD% -m venv venv
)

echo [INFO] Installing Python dependencies...
call venv\Scripts\activate.bat
pip install --upgrade pip
pip install -r requirements.txt
call venv\Scripts\deactivate.bat

popd

:: Create launcher
echo [INFO] Creating launcher script...
(
    echo @echo off
    echo cd /d "%%~dp0"
    echo call venv\Scripts\activate.bat
    echo python -u src\main.py %%*
) > "%INSTALL_DIR%\voice-claude.bat"

:: Add to PATH
echo [INFO] Adding to PATH...
for /f "tokens=2*" %%a in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USER_PATH=%%b"
echo %USER_PATH% | findstr /i /c:"%INSTALL_DIR%" >nul
if errorlevel 1 (
    setx Path "%USER_PATH%;%INSTALL_DIR%" >nul
    set "PATH=%PATH%;%INSTALL_DIR%"
)

echo.
echo ================================
echo   Installation complete!
echo ================================
echo.
echo Run Voice Claude with:
echo.
echo   voice-claude
echo.
echo Or directly:
echo.
echo   %INSTALL_DIR%\voice-claude.bat
echo.
echo Note: The first run will download the Whisper speech model (~500MB).
echo.
echo You may need to restart your terminal for PATH changes to take effect.
echo.
goto :end

:error
echo.
echo Installation failed.
exit /b 1

:end
endlocal
