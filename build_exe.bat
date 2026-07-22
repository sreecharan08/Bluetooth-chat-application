@echo off
setlocal

REM BTChat - build a standalone Windows .exe (no Python required to run it).
REM Result lands in dist\BTChat.exe - that single file is what you hand to
REM someone else; they don't need Python, pip, or this folder at all.
REM
REM Dependency install only happens ONCE (first run, or after you edit
REM requirements.txt). Every run after that skips straight to the build,
REM which is the only step you actually need to repeat when the code changes.

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [BTChat] No virtual environment found - creating one...
    python -m venv .venv
)

if not exist ".venv\.deps_installed" (
    echo [BTChat] First-time setup: installing dependencies...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet
    ".venv\Scripts\python.exe" -m pip install pyinstaller --quiet
    if errorlevel 1 (
        echo [BTChat] ERROR: Dependency installation failed. See output above.
        pause
        exit /b 1
    )
    echo done > ".venv\.deps_installed"
) else (
    echo [BTChat] Dependencies already installed - skipping straight to build.
    echo   ^(Delete the .venv folder, or the .venv\.deps_installed file, to force a reinstall
    echo    e.g. after changing requirements.txt^)
)

echo [BTChat] Building BTChat.exe (this can take a couple of minutes)...
REM --onefile        : single .exe, nothing else to ship
REM --windowed       : no console window behind the GUI
REM --collect-all    : winsdk and PyQt6 both load native/plugin files that
REM                    PyInstaller's static import scan won't find on its
REM                    own (winsdk's Windows.* submodules are imported
REM                    lazily inside functions; PyQt6 needs its Qt plugin
REM                    DLLs). --collect-all bundles binaries + data + every
REM                    submodule so nothing is missing at runtime.
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --onefile --windowed ^
    --name BTChat ^
    --collect-all winsdk ^
    --collect-all PyQt6 ^
    main.py

if errorlevel 1 (
    echo [BTChat] Build failed. See output above.
    pause
    exit /b 1
)

echo.
echo [BTChat] Done. Your standalone app is at: dist\BTChat.exe
echo Copy that one file anywhere - no Python install needed to run it.
pause