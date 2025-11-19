@echo off
REM AutoGen Multi-Agent System - Startup Script
REM Run this script to start the application

echo ================================================
echo AutoGen Multi-Agent System
echo ================================================
echo.
echo Starting Streamlit application...
echo.
echo The app will open in your browser at:
echo   http://localhost:8501
echo.
echo Press Ctrl+C to stop the application
echo.
echo ================================================
echo.

REM Start Streamlit
python -m streamlit run streamlit_app.py

REM If that fails, try direct streamlit command
if %errorlevel% neq 0 (
    echo Trying alternative startup method...
    streamlit run streamlit_app.py
)

if %errorlevel% neq 0 (
    echo.
    echo X Failed to start the application.
    echo.
    echo Make sure you've run setup.bat first!
    pause
)
