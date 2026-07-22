@echo off
setlocal

REM BTChat - one-click setup + run.
REM Creates a venv on first run, installs dependencies, then launches the app.
REM Just double-click this file (or run it from a terminal) every time.

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [BTChat] Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo [BTChat] ERROR: Could not create a virtual environment.
        echo Make sure Python 3.11+ is installed and on your PATH.
        pause
        exit /b 1
    )
)

echo [BTChat] Installing/updating dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
".venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [BTChat] ERROR: Dependency installation failed. See output above.
    pause
    exit /b 1
)

echo [BTChat] Launching...
".venv\Scripts\python.exe" main.py

if errorlevel 1 (
    echo [BTChat] The app exited with an error. See output above.
    pause
)