"""
WhatsApp-inspired visual theme: color palette, global stylesheet, and a
couple of small helpers (avatar colors, initials) shared by widgets.py.

Keeping all of this in one place means the whole app's look can be
tweaked from a single file.
"""
import hashlib

# --- Palette (modeled on WhatsApp's light desktop theme) -----------------
GREEN_DARK = "#075E54"      # top header bar
GREEN_MED = "#00A884"       # primary accent / buttons
GREEN_LIGHT_BUBBLE = "#d9fdd3"  # outgoing message bubble
WHITE = "#ffffff"
CHAT_BG = "#efeae2"          # chat canvas background
SIDEBAR_BG = "#ffffff"
SIDEBAR_HEADER_BG = "#f0f2f5"
BORDER = "#e9edef"
TEXT_PRIMARY = "#111b21"
TEXT_SECONDARY = "#667781"
HOVER = "#f5f6f6"
SELECTED = "#e9edef"

# A handful of distinct, muted colors for avatar backgrounds - picked to
# look reasonable with white initials on top, WhatsApp/Slack-style.
AVATAR_PALETTE = [
    "#f56060", "#f2994a", "#e0a92f", "#27ae60", "#00A884",
    "#2f80ed", "#9b51e0", "#eb5757", "#219653", "#56ccf2",
]


def avatar_color(seed: str) -> str:
    """Deterministic color pick so the same name/id always gets the same avatar color."""
    if not seed:
        return AVATAR_PALETTE[0]
    h = int(hashlib.md5(seed.encode("utf-8")).hexdigest(), 16)
    return AVATAR_PALETTE[h % len(AVATAR_PALETTE)]


def initials(name: str) -> str:
    name = (name or "?").strip()
    if not name:
        return "?"
    parts = name.split()
    if len(parts) == 1:
        return parts[0][:1].upper()
    return (parts[0][:1] + parts[-1][:1]).upper()


STYLESHEET = f"""
* {{
    font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
}}

QMainWindow {{
    background-color: {CHAT_BG};
}}

/* ---- Sidebar ---- */
#Sidebar {{
    background-color: {SIDEBAR_BG};
    border-right: 1px solid {BORDER};
}}
#SidebarHeader {{
    background-color: {SIDEBAR_HEADER_BG};
    border-bottom: 1px solid {BORDER};
}}
#AppTitle {{
    color: {TEXT_PRIMARY};
    font-size: 16px;
    font-weight: 600;
}}
#AppSubtitle {{
    color: {TEXT_SECONDARY};
    font-size: 11px;
}}

QListWidget#DeviceList {{
    background-color: {SIDEBAR_BG};
    border: none;
    outline: none;
}}
QListWidget#DeviceList::item {{
    border-bottom: 1px solid {BORDER};
}}
QListWidget#DeviceList::item:hover {{
    background-color: {HOVER};
}}
QListWidget#DeviceList::item:selected {{
    background-color: {SELECTED};
}}

/* ---- Buttons ---- */
QPushButton#PrimaryButton {{
    background-color: {GREEN_MED};
    color: white;
    border: none;
    border-radius: 18px;
    padding: 8px 18px;
    font-size: 13px;
    font-weight: 600;
}}
QPushButton#PrimaryButton:hover {{ background-color: #049275; }}
QPushButton#PrimaryButton:disabled {{ background-color: #a9d9cd; }}

QPushButton#GhostButton {{
    background-color: transparent;
    color: {GREEN_DARK};
    border: 1px solid {BORDER};
    border-radius: 16px;
    padding: 6px 14px;
    font-size: 12px;
}}
QPushButton#GhostButton:hover {{ background-color: {HOVER}; }}

QToolButton#IconButton {{
    background-color: transparent;
    border: none;
    border-radius: 16px;
    padding: 6px;
    color: {TEXT_SECONDARY};
    font-size: 14px;
}}
QToolButton#IconButton:hover {{ background-color: {HOVER}; }}

/* ---- Chat header ---- */
#ChatHeader {{
    background-color: {SIDEBAR_HEADER_BG};
    border-bottom: 1px solid {BORDER};
}}
#PeerName {{
    color: {TEXT_PRIMARY};
    font-size: 15px;
    font-weight: 600;
}}
#PeerStatus {{
    color: {TEXT_SECONDARY};
    font-size: 11px;
}}
#PeerStatus[connected="true"] {{
    color: {GREEN_MED};
}}

QPushButton#DisconnectButton {{
    background-color: transparent;
    color: #d64545;
    border: 1px solid #f0c4c4;
    border-radius: 14px;
    padding: 5px 14px;
    font-size: 12px;
    font-weight: 600;
}}
QPushButton#DisconnectButton:hover {{
    background-color: #fdeeee;
}}

/* ---- Message list / canvas ---- */
QListWidget#MessageList {{
    background-color: {CHAT_BG};
    border: none;
    outline: none;
}}
QListWidget#MessageList::item {{
    border: none;
}}

/* ---- Input bar ---- */
#InputBar {{
    background-color: {SIDEBAR_HEADER_BG};
    border-top: 1px solid {BORDER};
}}
QLineEdit#MessageInput {{
    background-color: {WHITE};
    border: none;
    border-radius: 20px;
    padding: 10px 16px;
    font-size: 13px;
    color: {TEXT_PRIMARY};
}}
QPushButton#SendButton {{
    background-color: {GREEN_MED};
    color: white;
    border: none;
    border-radius: 22px;
    font-size: 16px;
    font-weight: 600;
    min-width: 44px;
    min-height: 44px;
}}
QPushButton#SendButton:hover {{ background-color: #049275; }}
QPushButton#SendButton:disabled {{ background-color: #cfe9e2; color: #eef7f4; }}

QLineEdit#SearchBox {{
    background-color: {SIDEBAR_HEADER_BG};
    border: 1px solid {BORDER};
    border-radius: 14px;
    padding: 6px 12px;
    font-size: 12px;
    color: {TEXT_PRIMARY};
}}

QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: #d0d4d6;
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
"""