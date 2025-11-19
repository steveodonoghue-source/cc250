@echo off
REM AutoGen Multi-Agent System - One-Time Setup Script
REM This script installs dependencies and initializes all databases

echo ================================================
echo AutoGen Multi-Agent System - Setup
echo ================================================
echo.

REM Check if Python is installed
echo Checking Python installation...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo X Python is not installed. Please install Python 3.8 or higher.
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo [OK] Found Python %PYTHON_VERSION%
echo.

REM Check if pip is installed
echo Checking pip installation...
pip --version >nul 2>&1
if %errorlevel% neq 0 (
    echo X pip is not installed. Please install pip.
    pause
    exit /b 1
)

echo [OK] pip is installed
echo.

REM Install dependencies
echo Installing Python packages...
echo This may take a few minutes...
pip install -r requirements.txt

if %errorlevel% neq 0 (
    echo X Failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo [OK] All packages installed successfully
echo.

REM Initialize databases
echo Initializing databases...
python -c "import database; import database_marketplace; import database_cost; import database_orchestration; import database_testing; import database_integrations; print('[OK] All databases initialized successfully!')"

if %errorlevel% neq 0 (
    echo X Failed to initialize databases.
    pause
    exit /b 1
)

echo.
echo ================================================
echo [OK] Setup Complete!
echo ================================================
echo.
echo You can now run the application with:
echo   start.bat
echo.
echo Or on Mac/Linux:
echo   ./start.sh
echo.
pause
