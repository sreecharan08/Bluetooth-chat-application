"""
Right-hand chat panel: peer header, scrollable message bubble list, and
the message input bar - the WhatsApp-style "conversation view".
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QLabel, QListWidget, QListWidgetItem
)
from PyQt6.QtCore import pyqtSignal, Qt

from . import theme
from .widgets import Avatar, MessageBubble, SystemNotice


class ChatWidget(QWidget):
    message_submitted = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ---- Header: avatar + name + status ----
        header = QWidget()
        header.setObjectName("ChatHeader")
        header.setFixedHeight(60)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 8, 16, 8)
        header_layout.setSpacing(12)

        self.peer_avatar = Avatar("?", size=40)
        header_layout.addWidget(self.peer_avatar)

        name_col = QVBoxLayout()
        name_col.setSpacing(0)
        self.peer_name_label = QLabel("Not connected")
        self.peer_name_label.setObjectName("PeerName")
        self.peer_status_label = QLabel("Select a device from the sidebar to start chatting")
        self.peer_status_label.setObjectName("PeerStatus")
        name_col.addWidget(self.peer_name_label)
        name_col.addWidget(self.peer_status_label)
        header_layout.addLayout(name_col, stretch=1)

        layout.addWidget(header)

        # ---- Message list (bubbles) ----
        self.message_list = QListWidget()
        self.message_list.setObjectName("MessageList")
        self.message_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.message_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.message_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.message_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(self.message_list, stretch=1)

        # ---- Input bar ----
        input_bar = QWidget()
        input_bar.setObjectName("InputBar")
        input_row = QHBoxLayout(input_bar)
        input_row.setContentsMargins(16, 10, 16, 10)
        input_row.setSpacing(10)

        self.input_box = QLineEdit()
        self.input_box.setObjectName("MessageInput")
        self.input_box.setPlaceholderText("Type a message...")
        self.input_box.returnPressed.connect(self._submit)
        input_row.addWidget(self.input_box, stretch=1)

        self.send_button = QPushButton("\u27A4")  # ➤
        self.send_button.setObjectName("SendButton")
        self.send_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_button.clicked.connect(self._submit)
        input_row.addWidget(self.send_button)

        layout.addWidget(input_bar)

        self.set_enabled(False)

    # ---- behavior -------------------------------------------------

    def _submit(self):
        text = self.input_box.text().strip()
        if not text:
            return
        self.message_submitted.emit(text)
        self.input_box.clear()

    def set_enabled(self, enabled: bool):
        self.input_box.setEnabled(enabled)
        self.send_button.setEnabled(enabled)

    def set_status(self, text: str, connected: bool = False):
        self.peer_status_label.setText(text)
        self.peer_status_label.setProperty("connected", "true" if connected else "false")
        self.peer_status_label.style().unpolish(self.peer_status_label)
        self.peer_status_label.style().polish(self.peer_status_label)

    def set_peer_name(self, name: str):
        self.peer_name_label.setText(name)
        self.peer_avatar.set_name(name)

    def _add_row(self, widget: QWidget):
        item = QListWidgetItem()
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        self.message_list.addItem(item)
        item.setSizeHint(widget.sizeHint())
        self.message_list.setItemWidget(item, widget)
        self.message_list.scrollToBottom()

    def append_message(self, sender_label: str, text: str, timestamp: float = None, outgoing: bool = False):
        self._add_row(MessageBubble(text, timestamp, outgoing))

    def append_system(self, text: str):
        self._add_row(SystemNotice(text))

    def clear_messages(self):
        self.message_list.clear()