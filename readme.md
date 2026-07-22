# BTChat

Bluetooth chat for Windows, using WinRT RFCOMM for discovery, pairing, and messaging.

## Requirements

- Windows 10 version 1607 or later
- Python 3.11+ on your PATH (only needed for `run.bat` / `build_exe.bat`, not for the final .exe)

## Option 1 - Just run it (`run.bat`)

Double-click **`run.bat`**. First run creates a local virtual environment (`.venv`) and installs
dependencies; every run after that starts instantly. Nothing is installed system-wide.

## Option 2 - Build a standalone .exe to hand to someone else (`build_exe.bat`)

Double-click **`build_exe.bat`**. This produces `dist\BTChat.exe` - a single file with everything
bundled in. Copy that one file to another PC and double-click it; no Python, no pip, no setup
required on the receiving end.

Rebuild it any time you change the code - it always reflects whatever is in this folder at build time.

## Using the app

1. On one PC, click **"Make this PC discoverable"**.
2. On the other, click **Scan** - the first PC should show up in the "Nearby BTChat devices" list.
3. Select it, click **Pair** if Windows prompts you to, then **Connect**.
4. Chat.

If a device you expect isn't found by discovery, the **Advanced: connect by MAC address** section
is a manual fallback - expand it and enter the peer's MAC address directly.

## Project layout

```
btchat/
  core/
    protocol.py     # message framing (length-prefixed JSON)
    storage.py       # local SQLite message history
    transport.py     # WinRT RFCOMM: advertise, connect, send/receive
    discovery.py     # WinRT scan for nearby BTChat instances + pairing
  ui/
    chat_widget.py   # message list + input box
    main_window.py    # discovery list, connect controls, wiring
  main.py
  requirements.txt
  run.bat            # one-click dev setup + run
  build_exe.bat       # one-click standalone .exe build
```

## Known limitation

The WinRT Bluetooth code (`transport.py`, `discovery.py`) has been written to match Microsoft's
documented API exactly, but it's only fully testable on real Windows hardware with a Bluetooth
radio - it can't be exercised in a Linux sandbox. If you hit a traceback, the WinRT error text is
usually specific enough to pinpoint the exact call that needs adjusting.