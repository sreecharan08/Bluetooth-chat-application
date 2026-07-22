from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit, QPushButton, QLabel
)
from PyQt6.QtCore import pyqtSignal, Qt
import time


class ChatWidget(QWidget):
    message_submitted = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        self.status_label = QLabel("Not connected")
        self.status_label.setStyleSheet("color: #888; padding: 4px;")
        layout.addWidget(self.status_label)

        self.history = QTextEdit()
        self.history.setReadOnly(True)
        layout.addWidget(self.history, stretch=1)

        input_row = QHBoxLayout()
        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("Type a message...")
        self.input_box.returnPressed.connect(self._submit)
        input_row.addWidget(self.input_box, stretch=1)

        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self._submit)
        input_row.addWidget(self.send_button)

        layout.addLayout(input_row)

        self.set_enabled(False)

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
        self.status_label.setText(text)
        color = "#2e7d32" if connected else "#888"
        self.status_label.setStyleSheet(f"color: {color}; padding: 4px;")

    def append_message(self, sender_label: str, text: str, timestamp: float = None, outgoing: bool = False):
        ts = time.strftime("%H:%M", time.localtime(timestamp or time.time()))
        align_color = "#1565c0" if outgoing else "#333"
        self.history.append(
            f'<div style="margin:4px 0;">'
            f'<span style="color:#999; font-size:11px;">[{ts}]</span> '
            f'<b style="color:{align_color};">{sender_label}:</b> {text}'
            f'</div>'
        )

    def append_system(self, text: str):
        self.history.append(f'<div style="color:#999; font-style:italic; margin:2px 0;">{text}</div>')