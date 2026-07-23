"""
Pre-flight check for BTChat - verifies the project will actually start
without launching the GUI. Run this whenever something's not working
and you're not sure if it's a code problem, a missing dependency, or
an environment problem.

Usage:  python check.py   (or double-click check.bat)
"""
import importlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
PASS = "  [OK]  "
FAIL = "  [FAIL]"

errors = []


def check(label, fn):
    try:
        fn()
        print(PASS + label)
    except Exception as e:
        print(FAIL + label)
        print(f"         -> {type(e).__name__}: {e}")
        errors.append(label)


def check_python_version():
    v = sys.version_info
    print(f"    Python {v.major}.{v.minor}.{v.micro} at {sys.executable}")
    if v < (3, 9):
        raise RuntimeError("Python 3.9+ required")


def check_files_present():
    required = [
        "main.py", "requirements.txt",
        "core/__init__.py", "core/protocol.py", "core/storage.py",
        "core/transport.py", "core/discovery.py",
        "ui/__init__.py", "ui/theme.py", "ui/widgets.py",
        "ui/chat_widget.py", "ui/main_window.py",
    ]
    missing = [f for f in required if not (ROOT / f).exists()]
    if missing:
        raise RuntimeError(f"Missing files: {', '.join(missing)}")


def check_syntax():
    py_files = list(ROOT.glob("core/*.py")) + list(ROOT.glob("ui/*.py")) + [ROOT / "main.py"]
    for f in py_files:
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(f)],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"{f.name}: {result.stderr.strip()}")


def check_pyqt6():
    importlib.import_module("PyQt6.QtWidgets")


def check_winsdk():
    importlib.import_module("winsdk.windows.devices.bluetooth.rfcomm")


def check_core_imports():
    for mod in ["core.protocol", "core.storage", "core.transport", "core.discovery"]:
        sys.modules.pop(mod, None)
        importlib.import_module(mod)


def check_ui_imports():
    for mod in ["ui.theme", "ui.widgets", "ui.chat_widget", "ui.main_window"]:
        sys.modules.pop(mod, None)
        importlib.import_module(mod)


def check_storage():
    from core import storage
    storage.init_db()
    storage.get_or_create_local_id()


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    print("=== BTChat pre-flight check ===\n")

    check("Python version", check_python_version)
    check("Required files present", check_files_present)
    check("Syntax (py_compile) on all .py files", check_syntax)
    check("PyQt6 installed", check_pyqt6)
    check("winsdk installed (Windows Bluetooth bindings)", check_winsdk)
    check("core/ package imports cleanly", check_core_imports)
    check("ui/ package imports cleanly", check_ui_imports)
    check("Local SQLite storage works", check_storage)

    print()
    if errors:
        print(f"{len(errors)} check(s) failed: {', '.join(errors)}")
        print("Fix the issue(s) above, then run this again before trying main.py.")
        sys.exit(1)
    else:
        print("All checks passed - main.py should launch cleanly.")
        sys.exit(0)