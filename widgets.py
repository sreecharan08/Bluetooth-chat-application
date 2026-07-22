"""
Small reusable widgets for the WhatsApp-style UI: circular avatars,
sidebar contact rows, and chat message bubbles.
"""
import time
from PyQt6.QtWidgets import QWidget, QLabel, QHBoxLayout, QVBoxLayout, QFrame, QSizePolicy
from PyQt6.QtCore import Qt

from . import theme


class Avatar(QLabel):
    """Circular colored badge showing a name's initials."""

    def __init__(self, name: str, size: int = 44, parent=None):
        super().__init__(parent)
        self._size = size
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_name(name)

    def set_name(self, name: str):
        color = theme.avatar_color(name)
        font_size = max(11, self._size // 3)
        self.setStyleSheet(f"""
            background-color: {color};
            color: white;
            border-radius: {self._size // 2}px;
            font-weight: 600;
            font-size: {font_size}px;
        """)
        self.setText(theme.initials(name))


class ContactItemWidget(QWidget):
    """One row in the sidebar's 'Nearby BTChat devices' list."""

    def __init__(self, name: str, subtitle: str, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)

        layout.addWidget(Avatar(name, size=44))

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        name_label = QLabel(name)
        name_label.setStyleSheet(f"color: {theme.TEXT_PRIMARY}; font-size: 13px; font-weight: 600;")
        sub_label = QLabel(subtitle)
        sub_label.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; font-size: 11px;")
        text_col.addWidget(name_label)
        text_col.addWidget(sub_label)
        layout.addLayout(text_col, stretch=1)


class MessageBubble(QWidget):
    """
    One chat message, rendered as a rounded bubble aligned left
    (incoming) or right (outgoing), WhatsApp-style.
    """

    def __init__(self, text: str, timestamp: float = None, outgoing: bool = False, parent=None):
        super().__init__(parent)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(12, 3, 12, 3)

        bubble = QFrame()
        bubble.setMaximumWidth(420)
        bg = theme.GREEN_LIGHT_BUBBLE if outgoing else theme.WHITE
        bubble.setStyleSheet(f"""
            QFrame {{
                background-color: {bg};
                border-radius: 10px;
            }}
        """)
        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(10, 7, 10, 6)
        bubble_layout.setSpacing(2)

        text_label = QLabel(text)
        text_label.setWordWrap(True)
        text_label.setStyleSheet(f"color: {theme.TEXT_PRIMARY}; font-size: 13px; background: transparent;")
        text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        bubble_layout.addWidget(text_label)

        ts = time.strftime("%H:%M", time.localtime(timestamp or time.time()))
        time_label = QLabel(ts)
        time_label.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; font-size: 10px; background: transparent;")
        time_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        bubble_layout.addWidget(time_label)

        if outgoing:
            outer.addStretch(1)
            outer.addWidget(bubble)
        else:
            outer.addWidget(bubble)
            outer.addStretch(1)


class SystemNotice(QWidget):
    """Centered pill-shaped system message, e.g. 'Connected to X'."""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(12, 6, 12, 6)
        outer.addStretch(1)

        pill = QLabel(text)
        pill.setWordWrap(True)
        pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pill.setStyleSheet(f"""
            background-color: #fef7d8;
            color: #5c5a4d;
            border-radius: 8px;
            padding: 5px 12px;
            font-size: 11px;
        """)
        outer.addWidget(pill)
        outer.addStretch(1)