@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [BTChat] No virtual environment found - run run.bat first to set one up.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" check.py
pause