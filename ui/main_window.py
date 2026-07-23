import time

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QLabel, QMessageBox, QInputDialog, QListWidget,
    QListWidgetItem, QToolButton, QSizePolicy
)
from PyQt6.QtCore import Qt

from core import storage
from core.transport import BluetoothWorker, winrt_bluetooth_available
from core.discovery import DiscoveryWorker, PairWorker
from core.protocol import Envelope, MessageType, make_text_message
from . import theme
from .widgets import ContactItemWidget, Avatar
from .chat_widget import ChatWidget

DEVICE_ID_ROLE = Qt.ItemDataRole.UserRole
DEVICE_NAME_ROLE = Qt.ItemDataRole.UserRole + 1
DEVICE_PAIRED_ROLE = Qt.ItemDataRole.UserRole + 2


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BTChat")
        self.resize(980, 700)
        self.setStyleSheet(theme.STYLESHEET)

        storage.init_db()
        self.local_id = storage.get_or_create_local_id()
        self.display_name = storage.get_display_name()
        if self.display_name == "Me":
            name, ok = QInputDialog.getText(self, "Your name", "What should we call you in chats?")
            if ok and name.strip():
                self.display_name = name.strip()
                storage.set_display_name(self.display_name)

        self.worker: BluetoothWorker | None = None
        self.discovery_worker: DiscoveryWorker | None = None
        self.pair_worker: PairWorker | None = None
        self.peer_key: str | None = None    # device_id (preferred) or MAC, used as storage key
        self.peer_name: str = "Peer"
        self.is_advertising = False

        self._build_ui()

        if not winrt_bluetooth_available():
            QMessageBox.warning(
                self, "Bluetooth unavailable",
                "The `winsdk` package (WinRT Bluetooth bindings) isn't available.\n\n"
                "Install it with:\n    pip install winsdk\n\n"
                "This requires Windows 10 version 1607 or later."
            )
        else:
            self._start_scan()

    # ---------------------------------------------------------------
    # UI construction
    # ---------------------------------------------------------------

    def _build_ui(self):
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_sidebar())
        root.addWidget(self._build_chat_panel(), stretch=1)

        self.setCentralWidget(central)

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(320)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # -- header --
        header = QWidget()
        header.setObjectName("SidebarHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(16, 14, 16, 14)
        header_layout.setSpacing(10)

        title_row = QHBoxLayout()
        my_avatar = Avatar(self.display_name, size=36)
        title_row.addWidget(my_avatar)
        title_col = QVBoxLayout()
        title_col.setSpacing(0)
        app_title = QLabel("BTChat")
        app_title.setObjectName("AppTitle")
        app_subtitle = QLabel(f"You: {self.display_name}")
        app_subtitle.setObjectName("AppSubtitle")
        title_col.addWidget(app_title)
        title_col.addWidget(app_subtitle)
        title_row.addLayout(title_col, stretch=1)
        header_layout.addLayout(title_row)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.scan_btn = QPushButton("Scan")
        self.scan_btn.setObjectName("GhostButton")
        self.scan_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.scan_btn.clicked.connect(self._start_scan)
        btn_row.addWidget(self.scan_btn)

        self.listen_btn = QPushButton("Make discoverable")
        self.listen_btn.setObjectName("PrimaryButton")
        self.listen_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.listen_btn.clicked.connect(self._on_listen_clicked)
        btn_row.addWidget(self.listen_btn, stretch=1)
        header_layout.addLayout(btn_row)

        layout.addWidget(header)

        # -- section label --
        section_label = QLabel("  NEARBY DEVICES")
        section_label.setStyleSheet(
            f"color: {theme.TEXT_SECONDARY}; font-size: 10px; font-weight: 600; "
            f"padding: 10px 8px 4px 8px; letter-spacing: 1px;"
        )
        layout.addWidget(section_label)

        # -- device list --
        self.device_list = QListWidget()
        self.device_list.setObjectName("DeviceList")
        self.device_list.itemClicked.connect(self._on_device_row_clicked)
        self.device_list.itemDoubleClicked.connect(self._on_connect_selected)
        layout.addWidget(self.device_list, stretch=1)

        # -- per-selection actions --
        action_row = QWidget()
        action_layout = QHBoxLayout(action_row)
        action_layout.setContentsMargins(12, 8, 12, 8)
        action_layout.setSpacing(8)
        self.pair_btn = QPushButton("Pair")
        self.pair_btn.setObjectName("GhostButton")
        self.pair_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pair_btn.clicked.connect(self._on_pair_selected)
        self.connect_selected_btn = QPushButton("Connect")
        self.connect_selected_btn.setObjectName("PrimaryButton")
        self.connect_selected_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.connect_selected_btn.clicked.connect(self._on_connect_selected)
        action_layout.addWidget(self.pair_btn)
        action_layout.addWidget(self.connect_selected_btn, stretch=1)
        layout.addWidget(action_row)

        # -- advanced/manual fallback, collapsed by default --
        self.advanced_toggle = QToolButton()
        self.advanced_toggle.setText("  Advanced: connect by MAC")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.advanced_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.advanced_toggle.setStyleSheet(
            f"QToolButton {{ border: none; color: {theme.TEXT_SECONDARY}; font-size: 11px; "
            f"padding: 8px 12px; text-align: left; }}"
        )
        self.advanced_toggle.clicked.connect(self._toggle_advanced)
        layout.addWidget(self.advanced_toggle)

        self.advanced_row = QWidget()
        advanced_layout = QVBoxLayout(self.advanced_row)
        advanced_layout.setContentsMargins(12, 0, 12, 10)
        advanced_layout.setSpacing(6)
        self.mac_input = QLineEdit()
        self.mac_input.setObjectName("SearchBox")
        self.mac_input.setPlaceholderText("AA:BB:CC:DD:EE:FF")
        advanced_layout.addWidget(self.mac_input)
        self.mac_connect_btn = QPushButton("Connect by MAC")
        self.mac_connect_btn.setObjectName("GhostButton")
        self.mac_connect_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mac_connect_btn.clicked.connect(self._on_connect_by_mac)
        advanced_layout.addWidget(self.mac_connect_btn)
        self.advanced_row.setVisible(False)
        layout.addWidget(self.advanced_row)

        return sidebar

    def _build_chat_panel(self) -> QWidget:
        self.chat = ChatWidget()
        self.chat.message_submitted.connect(self._on_send)
        self.chat.disconnect_clicked.connect(self._on_disconnect_clicked)
        return self.chat

    def _toggle_advanced(self):
        self.advanced_row.setVisible(self.advanced_toggle.isChecked())
        self.advanced_toggle.setArrowType(
            Qt.ArrowType.DownArrow if self.advanced_toggle.isChecked() else Qt.ArrowType.RightArrow
        )

    # ---------------------------------------------------------------
    # Discovery
    # ---------------------------------------------------------------

    def _start_scan(self):
        if self.discovery_worker and self.discovery_worker.isRunning():
            return
        self.scan_btn.setEnabled(False)
        self.scan_btn.setText("Scanning...")
        self.device_list.clear()
        self.discovery_worker = DiscoveryWorker(timeout=8.0)
        self.discovery_worker.found.connect(self._on_devices_found)
        self.discovery_worker.error.connect(self._on_scan_error)
        self.discovery_worker.start()

    def _on_devices_found(self, devices: list):
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("Scan")
        self.device_list.clear()
        if not devices:
            placeholder = QListWidgetItem()
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            note = QLabel("No BTChat devices found nearby.\nMake sure it's open on the other PC.")
            note.setWordWrap(True)
            note.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; font-size: 12px; padding: 16px;")
            self.device_list.addItem(placeholder)
            placeholder.setSizeHint(note.sizeHint())
            self.device_list.setItemWidget(placeholder, note)
            return
        for d in devices:
            subtitle = "Paired" if d["is_paired"] else "Nearby - tap Pair if connect fails"
            item = QListWidgetItem()
            item.setData(DEVICE_ID_ROLE, d["id"])
            item.setData(DEVICE_NAME_ROLE, d["name"])
            item.setData(DEVICE_PAIRED_ROLE, d["is_paired"])
            row_widget = ContactItemWidget(d["name"], subtitle)
            self.device_list.addItem(item)
            item.setSizeHint(row_widget.sizeHint())
            self.device_list.setItemWidget(item, row_widget)

    def _on_scan_error(self, message: str):
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("Scan")
        self.chat.append_system(f"Scan error: {message}")

    def _on_device_row_clicked(self, item):
        pass  # selection highlight is handled by the list widget itself

    def _selected_device(self):
        item = self.device_list.currentItem()
        if not item or item.data(DEVICE_ID_ROLE) is None:
            return None
        return {
            "id": item.data(DEVICE_ID_ROLE),
            "name": item.data(DEVICE_NAME_ROLE),
            "is_paired": item.data(DEVICE_PAIRED_ROLE),
        }

    def _on_pair_selected(self):
        device = self._selected_device()
        if not device:
            QMessageBox.information(self, "No device selected", "Select a device from the list first.")
            return
        self.pair_btn.setEnabled(False)
        self.chat.append_system(f"Pairing with {device['name']}... check for a Windows confirmation prompt.")
        self.pair_worker = PairWorker(device["id"])
        self.pair_worker.paired.connect(self._on_pair_result)
        self.pair_worker.error.connect(self._on_pair_error)
        self.pair_worker.start()

    def _on_pair_result(self, success: bool):
        self.pair_btn.setEnabled(True)
        self.chat.append_system("Paired successfully." if success else "Pairing was declined or failed.")
        if success:
            self._start_scan()

    def _on_pair_error(self, message: str):
        self.pair_btn.setEnabled(True)
        self.chat.append_system(f"Pairing error: {message}")

    # ---------------------------------------------------------------
    # Connection
    # ---------------------------------------------------------------

    def _set_connecting_state(self):
        self.connect_selected_btn.setEnabled(False)
        self.mac_connect_btn.setEnabled(False)
        self.listen_btn.setEnabled(False)
        self.chat.set_status("Connecting...", connected=False)
        self.chat.append_system("Connecting...")

    def _on_connect_selected(self):
        device = self._selected_device()
        if not device:
            QMessageBox.information(self, "No device selected", "Select a device from the list first.")
            return
        self._set_connecting_state()
        self.chat.set_peer_name(device["name"])
        self.worker = BluetoothWorker(
            local_id=self.local_id, display_name=self.display_name,
            mode="connect", target_device_id=device["id"], target_name=device["name"],
        )
        self._wire_worker()
        self.worker.start()

    def _on_connect_by_mac(self):
        mac = self.mac_input.text().strip()
        if not mac:
            QMessageBox.information(self, "MAC address needed", "Enter the peer's Bluetooth MAC address first.")
            return
        self._set_connecting_state()
        self.chat.set_peer_name(mac)
        self.worker = BluetoothWorker(
            local_id=self.local_id, display_name=self.display_name,
            mode="connect", target_mac=mac,
        )
        self._wire_worker()
        self.worker.start()

    def _on_listen_clicked(self):
        self._set_connecting_state()
        self.chat.set_peer_name("Waiting for a peer...")
        self.chat.append_system("Advertising BTChat - waiting for someone to connect...")
        self.worker = BluetoothWorker(
            local_id=self.local_id, display_name=self.display_name, mode="listen",
        )
        self._wire_worker()
        self.worker.start()

    def _wire_worker(self):
        self.worker.connected.connect(self._on_connected)
        self.worker.disconnected.connect(self._on_disconnected)
        self.worker.message_received.connect(self._on_message_received)
        self.worker.error.connect(self._on_error)
        self.worker.listening.connect(self._on_listening)

    def _on_listening(self):
        self.chat.set_status("Discoverable - waiting for a connection...", connected=False)

    def _on_connected(self, peer_label: str):
        self.peer_name = peer_label
        self.peer_key = (
            self.worker.target_device_id or self.worker.target_mac or peer_label
        )
        storage.upsert_contact(self.peer_key, display_name=peer_label, last_seen=time.time())
        self.chat.set_peer_name(peer_label)
        self.chat.set_status(f"Connected", connected=True)
        self.chat.append_system(f"Connected to {peer_label}")
        self.chat.set_enabled(True)
        self._reset_connect_buttons()

        self.chat.clear_messages()
        for m in storage.get_history(self.peer_key):
            label = self.display_name if m["direction"] == "out" else self.peer_name
            self.chat.append_message(label, m["text"], m["timestamp"], outgoing=(m["direction"] == "out"))

    def _on_disconnected(self, reason: str):
        self.chat.set_status("Disconnected", connected=False)
        self.chat.append_system(f"Disconnected ({reason})")
        self.chat.set_enabled(False)
        self._reset_connect_buttons()

    def _on_error(self, message: str):
        self.chat.append_system(f"Error: {message}")
        self._reset_connect_buttons()

    def _reset_connect_buttons(self):
        self.connect_selected_btn.setEnabled(True)
        self.mac_connect_btn.setEnabled(True)
        self.listen_btn.setEnabled(True)

    def _on_disconnect_clicked(self):
        if self.worker:
            self.chat.append_system("Disconnecting...")
            self.worker.stop()

    # ---------------------------------------------------------------
    # Messaging
    # ---------------------------------------------------------------

    def _on_message_received(self, envelope: Envelope):
        if envelope.type == MessageType.HELLO:
            self.peer_name = envelope.payload.get("display_name", self.peer_name)
            self.chat.set_peer_name(self.peer_name)
            self.chat.append_system(f"{self.peer_name} joined the chat")
            return
        if envelope.type == MessageType.ACK:
            storage.mark_delivered(envelope.payload.get("for_msg_id", ""))
            return
        if envelope.type == MessageType.TEXT:
            text = envelope.payload.get("text", "")
            self.chat.append_message(self.peer_name, text, envelope.timestamp, outgoing=False)
            if self.peer_key:
                storage.save_message(
                    envelope.msg_id, self.peer_key, envelope.sender_id,
                    "in", text, envelope.timestamp, delivered=True,
                )

    def _on_send(self, text: str):
        if not self.worker or not self.peer_key:
            return
        envelope = make_text_message(self.local_id, text)
        sent = self.worker.send(envelope)
        if sent:
            self.chat.append_message(self.display_name, text, envelope.timestamp, outgoing=True)
            storage.save_message(
                envelope.msg_id, self.peer_key, self.local_id,
                "out", text, envelope.timestamp, delivered=False,
            )

    def closeEvent(self, event):
        for w in (self.worker, self.discovery_worker, self.pair_worker):
            if w:
                if hasattr(w, "stop"):
                    w.stop()
                w.wait(2000)
        event.accept()