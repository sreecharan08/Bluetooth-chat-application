"""
Bluetooth RFCOMM transport - WinRT edition.

Plain AF_BLUETOOTH sockets (the old approach in this file) can only
dial a device you already know the MAC address of - Windows won't let
you enumerate/discover *services* that way. To get real "find nearby
BTChat instances and connect" behavior, we need the WinRT Bluetooth
APIs (Windows.Devices.Bluetooth.Rfcomm / Windows.Devices.Enumeration),
which is exactly what Microsoft's own "Bluetooth Rfcomm Chat Sample"
uses. We drive them from Python via the `winrt-*` packages.

Key facts this design relies on (from Microsoft's docs):
  - RfcommServiceProvider advertises a custom service (identified by
    BTCHAT_SERVICE_UUID below) that other BTChat instances can find.
  - Since Windows 10 1607+, RFCOMM devices advertising a custom service
    can be discovered and connected to WITHOUT a prior OS-level pairing
    bond, via StartAdvertising(listener, radioDiscoverable=True) on the
    server and DeviceInformation.find_all_async(selector) on the client.
  - We still expose an explicit Pair action (via
    DeviceInformationPairing) for cases where Windows' security policy
    requires a bonded pair before it'll allow the connection.

All WinRT calls are async (awaitable). Since Bluetooth I/O can't run on
the GUI thread, each BluetoothWorker runs its own asyncio event loop
inside a QThread and reports back to the GUI via Qt signals (the only
thread-safe way to touch widgets from a worker thread).

IMPORTANT: The `winrt-*` packages are Windows-only and require Windows 10 1607+.
This module cannot be executed/tested outside Windows - it has been
written to match Microsoft's documented API shapes as closely as
possible but has NOT been run against real Bluetooth hardware. If you
hit a traceback running this, send it back and it can be fixed fast.
"""
import asyncio
import uuid
from PyQt6.QtCore import QThread, pyqtSignal

from protocol import Envelope, make_hello, make_ack, MessageType

# Fixed UUID identifying "this is a BTChat instance". Both sides must
# use the same value - do not change unless you rebuild both ends.
BTCHAT_SERVICE_UUID = uuid.UUID("23e1f6c4-2eb5-4a0a-9614-6f0b1a6db2cd")
BTCHAT_SERVICE_NAME = "BTChatService"

POLL_INTERVAL = 1.0  # seconds; how often the server-accept loop checks for stop


def winrt_bluetooth_available() -> bool:
    """Best-effort check that the winrt Bluetooth packages are importable."""
    try:
        import winrt.windows.devices.bluetooth.rfcomm  # noqa: F401
        return True
    except ImportError:
        return False


def _mac_str_to_int(mac: str) -> int:
    return int(mac.replace(":", "").replace("-", ""), 16)


class BluetoothWorker(QThread):
    """
    One worker handles one connection, either as the listener/advertiser
    (server) or the initiator (client). Emits signals for everything the
    GUI thread needs to know about.
    """

    connected = pyqtSignal(str)                # peer display label
    disconnected = pyqtSignal(str)              # reason
    message_received = pyqtSignal(object)       # Envelope
    error = pyqtSignal(str)
    listening = pyqtSignal()                    # advertising has started

    def __init__(self, local_id: str, display_name: str, mode: str,
                 target_device_id: str = None, target_mac: str = None,
                 target_name: str = None, parent=None):
        """
        mode: "listen" (advertise + wait for an incoming connection) or
              "connect" (dial a peer).
        target_device_id: WinRT DeviceInformation.Id, as returned by
              discovery.scan_for_btchat_devices() - preferred path.
        target_mac: fallback manual "AA:BB:CC:DD:EE:FF" address, used
              only if target_device_id isn't available.
        """
        super().__init__(parent)
        self.local_id = local_id
        self.display_name = display_name
        self.mode = mode
        self.target_device_id = target_device_id
        self.target_mac = target_mac
        self.target_name = target_name

        self._loop = None
        self._writer = None
        self._sock = None
        self._stopped = False
        self._peer_label = target_name or target_mac or "peer"

    # ---- lifecycle -----------------------------------------------

    def run(self):
        try:
            asyncio.run(self._async_main())
        except Exception as e:  # noqa: BLE001 - surface any WinRT failure to the UI
            self.error.emit(f"Bluetooth error: {e}")

    def stop(self):
        """
        Ask the worker to stop. Closing the socket (if we have one) is
        what actually unblocks a pending reader.load_async() call in
        _handle_socket - without this, stop() only takes effect the next
        time the read loop naturally wakes up, which for a blocking read
        may be "never" until the peer sends something.
        """
        self._stopped = True
        sock = self._sock
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass

    async def _async_main(self):
        self._loop = asyncio.get_running_loop()
        if self.mode == "listen":
            await self._run_server()
        else:
            await self._run_client()

    # ---- server (advertise + accept) ------------------------------

    async def _run_server(self):
        from winrt.windows.devices.bluetooth.rfcomm import RfcommServiceProvider, RfcommServiceId
        from winrt.windows.networking.sockets import StreamSocketListener, SocketProtectionLevel

        provider = await RfcommServiceProvider.create_async(RfcommServiceId.from_uuid(BTCHAT_SERVICE_UUID))
        listener = StreamSocketListener()

        got_connection = self._loop.create_future()

        def on_connection_received(sender, args):
            if not got_connection.done():
                self._loop.call_soon_threadsafe(got_connection.set_result, args.socket)

        token = listener.add_connection_received(on_connection_received)
        try:
            await listener.bind_service_name_with_protection_level_async(
                provider.service_id.as_string(),
                SocketProtectionLevel.BLUETOOTH_ENCRYPTION_ALLOW_NULL_AUTHENTICATION,
            )
            # radioDiscoverable=True: discoverable by nearby devices
            # without requiring a pre-existing OS pairing bond.
            provider.start_advertising_with_radio_discoverability(listener, True)
            self.listening.emit()

            sock = None
            while not self._stopped:
                try:
                    sock = await asyncio.wait_for(asyncio.shield(got_connection), timeout=POLL_INTERVAL)
                    break
                except asyncio.TimeoutError:
                    continue
        finally:
            listener.remove_connection_received(token)
            try:
                provider.stop_advertising()
            except Exception:
                pass

        if sock is None:
            return  # stopped before anyone connected

        await self._handle_socket(sock)

    # ---- client (discover-and-dial or manual MAC) ------------------

    async def _run_client(self):
        from winrt.windows.devices.bluetooth.rfcomm import RfcommDeviceService, RfcommServiceId
        from winrt.windows.devices.bluetooth import BluetoothDevice
        from winrt.windows.networking.sockets import StreamSocket, SocketProtectionLevel

        service = None
        if self.target_device_id:
            service = await RfcommDeviceService.from_id_async(self.target_device_id)
            if service is None:
                raise RuntimeError("Couldn't resolve BTChat service on that device - it may have closed the app.")
        elif self.target_mac:
            addr = _mac_str_to_int(self.target_mac)
            device = await BluetoothDevice.from_bluetooth_address_async(addr)
            if device is None:
                raise RuntimeError("Device not found. Make sure it's powered on, in range, and BTChat is open on it.")
            result = await device.get_rfcomm_services_for_id_async(RfcommServiceId.from_uuid(BTCHAT_SERVICE_UUID))
            services = list(result.services) if result and result.services else []
            if not services:
                raise RuntimeError("That device isn't advertising BTChat - make sure BTChat is open and listening there.")
            service = services[0]
        else:
            raise RuntimeError("No target device specified.")

        sock = StreamSocket()
        await sock.connect_with_protection_level_async(
            service.connection_host_name,
            service.connection_service_name,
            SocketProtectionLevel.BLUETOOTH_ENCRYPTION_ALLOW_NULL_AUTHENTICATION,
        )
        await self._handle_socket(sock)

    # ---- shared read/write loop -------------------------------------

    async def _handle_socket(self, sock):
        from winrt.windows.storage.streams import DataReader, DataWriter, ByteOrder, UnicodeEncoding

        # Keep a reference so stop() can close it to unblock a pending read.
        self._sock = sock
        self._writer = DataWriter(sock.output_stream)
        reader = DataReader(sock.input_stream)
        reader.byte_order = ByteOrder.BIG_ENDIAN
        reader.unicode_encoding = UnicodeEncoding.UTF8

        self.connected.emit(self._peer_label)
        await self._send_envelope(make_hello(self.local_id, self.display_name))

        closed_reason = "connection closed"
        try:
            while not self._stopped:
                # IMPORTANT: await this directly - do NOT wrap it in
                # asyncio.wait_for()/timeout. A DataReader only allows one
                # outstanding load_async() at a time; cancelling this await
                # via a timeout abandons the underlying WinRT operation
                # without truly stopping it, so the *next* load_async() call
                # collides with it and the runtime tears down the stream,
                # which shows up as WinError -2147483629 (RO_E_CLOSED).
                # To stop this loop on demand, stop() closes the socket
                # instead, which makes this await return/raise immediately.
                loaded = await reader.load_async(4)
                if not loaded:
                    break  # peer closed the connection
                length = reader.read_uint32()
                if length <= 0 or length > 10_000_000:
                    break  # corrupt frame, bail out rather than hang
                await reader.load_async(length)
                raw = bytearray(length)
                reader.read_bytes(raw)
                self._handle_incoming_bytes(bytes(raw))
        except Exception as e:  # noqa: BLE001
            # If we asked for the socket to be closed (via stop()), this
            # exception is expected - it's just the read unblocking. Only
            # report it as a real error if we didn't request the close.
            if not self._stopped:
                self.error.emit(f"Connection error: {e}")
                closed_reason = "connection error"
        finally:
            try:
                sock.close()
            except Exception:
                pass
            self._sock = None
            self.disconnected.emit(closed_reason)

    def _handle_incoming_bytes(self, raw: bytes):
        import json
        try:
            envelope = Envelope.from_dict(json.loads(raw.decode("utf-8")))
        except (ValueError, KeyError):
            return
        if envelope.type == MessageType.TEXT:
            asyncio.run_coroutine_threadsafe(
                self._send_envelope(make_ack(self.local_id, envelope.msg_id)), self._loop
            )
        self.message_received.emit(envelope)

    async def _send_envelope(self, envelope: Envelope) -> bool:
        if not self._writer:
            return False
        try:
            self._writer.write_bytes(envelope.to_bytes())
            await self._writer.store_async()
            return True
        except Exception as e:  # noqa: BLE001
            self.error.emit(f"Send failed: {e}")
            return False

    def send(self, envelope: Envelope) -> bool:
        """
        Called from the GUI thread. Queues the send onto this worker's
        asyncio loop; returns True optimistically (delivery failures
        surface via the `error` signal, matching async semantics).
        """
        if not self._loop or not self._writer:
            self.error.emit("Not connected")
            return False
        asyncio.run_coroutine_threadsafe(self._send_envelope(envelope), self._loop)
        return True