"""
Bluetooth RFCOMM transport - WinRT edition.

Plain AF_BLUETOOTH sockets can only dial a device you already know the
MAC address of - Windows won't let you enumerate/discover *services*
that way. To get real "find nearby BTChat instances and connect"
behavior, we need the WinRT Bluetooth APIs
(Windows.Devices.Bluetooth.Rfcomm / Windows.Devices.Enumeration), which
is exactly what Microsoft's own "Bluetooth Rfcomm Chat Sample" uses. We
drive them from Python via the `winsdk` package.

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

Connection lifecycle: a connection now stays open until either the
user disconnects (or the app closes) or the peer goes out of range /
closes the socket - there is no artificial timeout. Two things make
that possible:
  - The read loop waits on the actual pending read plus a "stop"
    future, rather than repeatedly cancelling and re-issuing a timed
    read every second. Constantly cancelling a live WinRT stream read
    was the previous (buggy) design and is the likely cause of
    connections dropping "after a while" even while idle.
  - A lightweight PING/PONG keepalive runs every 20s so the OS/radio
    doesn't treat a quiet-but-open chat as an idle link worth closing.

All WinRT calls are async (awaitable). Since Bluetooth I/O can't run on
the GUI thread, each BluetoothWorker runs its own asyncio event loop
inside a QThread and reports back to the GUI via Qt signals (the only
thread-safe way to touch widgets from a worker thread).

IMPORTANT: `winsdk` is Windows-only and requires Windows 10 1607+.
This module cannot be executed/tested outside Windows - it has been
written to match Microsoft's documented API shapes as closely as
possible but has NOT been run against real Bluetooth hardware.
"""
import asyncio
import json
import uuid
from PyQt6.QtCore import QThread, pyqtSignal

from .protocol import Envelope, make_hello, make_ack, MessageType

# Fixed UUID identifying "this is a BTChat instance". Both sides must
# use the same value - do not change unless you rebuild both ends.
BTCHAT_SERVICE_UUID = uuid.UUID("23e1f6c4-2eb5-4a0a-9614-6f0b1a6db2cd")
BTCHAT_SERVICE_NAME = "BTChatService"

KEEPALIVE_INTERVAL = 20.0  # seconds between PINGs while idle


def winrt_bluetooth_available() -> bool:
    """Best-effort check that the winsdk package is importable here."""
    try:
        import winsdk.windows.devices.bluetooth.rfcomm  # noqa: F401
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
        self._stopped = False
        self._stop_future = None  # created once the loop is running
        self._peer_label = target_name or target_mac or "peer"

    # ---- lifecycle -----------------------------------------------

    def run(self):
        try:
            asyncio.run(self._async_main())
        except Exception as e:  # noqa: BLE001 - surface any WinRT failure to the UI
            self.error.emit(f"Bluetooth error: {e}")

    def stop(self):
        """
        Called from the GUI thread (e.g. the Disconnect button, or on
        app close). Signals the worker's asyncio loop to unwind
        cleanly - it does NOT force-close the socket from this thread,
        since that isn't safe to do across threads with WinRT objects.
        """
        self._stopped = True
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._resolve_stop_future)

    def _resolve_stop_future(self):
        if self._stop_future is not None and not self._stop_future.done():
            self._stop_future.set_result(True)

    async def _async_main(self):
        self._loop = asyncio.get_running_loop()
        self._stop_future = self._loop.create_future()
        if self.mode == "listen":
            await self._run_server()
        else:
            await self._run_client()

    # ---- server (advertise + accept) ------------------------------

    async def _run_server(self):
        from winsdk.windows.devices.bluetooth.rfcomm import RfcommServiceProvider, RfcommServiceId
        from winsdk.windows.networking.sockets import StreamSocketListener, SocketProtectionLevel

        provider = await RfcommServiceProvider.create_async(RfcommServiceId.from_uuid(BTCHAT_SERVICE_UUID))
        listener = StreamSocketListener()

        got_connection = self._loop.create_future()

        def on_connection_received(sender, args):
            if not got_connection.done():
                self._loop.call_soon_threadsafe(got_connection.set_result, args.socket)

        token = listener.add_connection_received(on_connection_received)
        sock = None
        try:
            await listener.bind_service_name_async(
                provider.service_id.as_string(),
                SocketProtectionLevel.BLUETOOTH_ENCRYPTION_ALLOW_NULL_AUTHENTICATION,
            )
            # radioDiscoverable=True: discoverable by nearby devices
            # without requiring a pre-existing OS pairing bond.
            provider.start_advertising(listener, True)
            self.listening.emit()

            done, _pending = await asyncio.wait(
                {got_connection, self._stop_future}, return_when=asyncio.FIRST_COMPLETED
            )
            if got_connection in done and not self._stop_future.done():
                sock = got_connection.result()
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
        from winsdk.windows.devices.bluetooth.rfcomm import RfcommDeviceService, RfcommServiceId
        from winsdk.windows.devices.bluetooth import BluetoothDevice
        from winsdk.windows.networking.sockets import StreamSocket, SocketProtectionLevel

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
        await sock.connect_async(
            service.connection_host_name,
            service.connection_service_name,
            SocketProtectionLevel.BLUETOOTH_ENCRYPTION_ALLOW_NULL_AUTHENTICATION,
        )
        await self._handle_socket(sock)

    # ---- shared read/write loop -------------------------------------

    async def _handle_socket(self, sock):
        from winsdk.windows.storage.streams import DataReader, DataWriter, ByteOrder

        self._writer = DataWriter(sock.output_stream)
        reader = DataReader(sock.input_stream)
        reader.byte_order = ByteOrder.BIG_ENDIAN

        self.connected.emit(self._peer_label)
        await self._send_envelope(make_hello(self.local_id, self.display_name))

        keepalive_task = asyncio.ensure_future(self._keepalive_loop())

        try:
            while not self._stopped:
                # A single pending read, waited on alongside the stop
                # signal - NOT repeatedly cancelled/recreated. Cancelling
                # a live WinRT stream read on a timer (the old design)
                # is what was likely causing connections to drop on
                # their own after a while.
                read_task = asyncio.ensure_future(reader.load_async(4))
                done, _pending = await asyncio.wait(
                    {read_task, self._stop_future}, return_when=asyncio.FIRST_COMPLETED
                )
                if self._stop_future.done():
                    if not read_task.done():
                        read_task.cancel()
                    break

                loaded = read_task.result()
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
            self.error.emit(f"Connection error: {e}")
        finally:
            keepalive_task.cancel()
            try:
                sock.close()
            except Exception:
                pass
            self.disconnected.emit(
                "you disconnected" if self._stopped else "connection lost - peer closed or went out of range"
            )

    async def _keepalive_loop(self):
        """Sends a PING every KEEPALIVE_INTERVAL seconds so idle connections
        aren't mistaken for dead ones by Windows' Bluetooth power management."""
        try:
            while not self._stopped:
                await asyncio.sleep(KEEPALIVE_INTERVAL)
                if self._stopped:
                    break
                await self._send_envelope(Envelope(type=MessageType.PING, sender_id=self.local_id))
        except asyncio.CancelledError:
            pass

    def _handle_incoming_bytes(self, raw: bytes):
        try:
            envelope = Envelope.from_dict(json.loads(raw.decode("utf-8")))
        except (ValueError, KeyError):
            return

        if envelope.type == MessageType.PING:
            asyncio.run_coroutine_threadsafe(
                self._send_envelope(Envelope(type=MessageType.PONG, sender_id=self.local_id)), self._loop
            )
            return
        if envelope.type == MessageType.PONG:
            return  # just keepalive traffic, nothing for the UI to do

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