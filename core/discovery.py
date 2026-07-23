"""
Nearby-device discovery and pairing.

Finds other machines currently running BTChat (advertising
BTCHAT_SERVICE_UUID, see transport.py) using WinRT's Bluetooth
enumeration APIs - the same mechanism Microsoft's own RFCOMM chat
sample uses. This is real service discovery, not a generic "list every
Bluetooth device nearby" scan, so the results are (in principle) only
other BTChat instances.

Pairing is exposed as a fallback: modern Windows (10 1607+) usually
lets RFCOMM custom services connect without a pre-existing OS pairing
bond, but some security policies still require one. `pair_device()`
triggers Windows' native pairing flow when needed.

NOTE: same caveat as transport.py - `winrt-*`/WinRT only runs on
Windows and hasn't been exercised against real hardware from this
environment.
"""
import asyncio
from PyQt6.QtCore import QThread, pyqtSignal

from .transport import BTCHAT_SERVICE_UUID


async def scan_for_btchat_devices(timeout: float = 8.0):
    """
    Returns a list of {"name": str, "id": str, "is_paired": bool} for
    nearby devices currently advertising the BTChat RFCOMM service.
    `id` is a WinRT DeviceInformation.Id - pass it back into
    BluetoothWorker(target_device_id=...) to connect.
    """
    from winrt.windows.devices.bluetooth.rfcomm import RfcommDeviceService, RfcommServiceId
    from winrt.windows.devices.enumeration import DeviceInformation

    selector = RfcommDeviceService.get_device_selector(RfcommServiceId.from_uuid(BTCHAT_SERVICE_UUID))
    try:
        devices = await asyncio.wait_for(DeviceInformation.find_all_async_aqs_filter(selector), timeout=timeout)
    except asyncio.TimeoutError:
        return []

    results = []
    for d in devices:
        try:
            is_paired = bool(d.pairing and d.pairing.is_paired)
        except Exception:
            is_paired = False
        results.append({
            "name": d.name or "Unknown BTChat device",
            "id": d.id,
            "is_paired": is_paired,
        })
    return results


async def pair_device(device_id: str) -> bool:
    """
    Triggers Windows' native pairing UI/flow for the given device.
    Auto-accepts "confirm only" and PIN-display style requests since
    there's no second screen involved for a same-app chat pairing;
    Windows itself still shows its own confirmation dialog to the user.
    """
    from winrt.windows.devices.bluetooth.rfcomm import RfcommDeviceService
    from winrt.windows.devices.enumeration import (
        DevicePairingKinds, DevicePairingResultStatus,
    )

    # device_id here is the id of the RFCOMM *service* instance (as
    # returned by scan_for_btchat_devices), not of the underlying
    # Bluetooth device. DeviceInformation.create_from_id_async(device_id)
    # on that service id leaves `.pairing` unset (None), which is what
    # caused "'NoneType' object has no attribute 'is_paired'". Pairing
    # is a property of the *device*, so resolve the service first and
    # go through its .device.device_information instead.
    service = await RfcommDeviceService.from_id_async(device_id)
    if service is None:
        raise RuntimeError("Couldn't resolve that device - it may have gone offline.")

    info = service.device.device_information
    if info.pairing is None:
        raise RuntimeError("This device doesn't support pairing.")
    if info.pairing.is_paired:
        return True

    custom = info.pairing.custom

    def on_pairing_requested(sender, args):
        try:
            args.accept()
        except Exception:
            pass

    token = custom.add_pairing_requested(on_pairing_requested)
    try:
        result = await custom.pair_async(
            DevicePairingKinds.CONFIRM_ONLY | DevicePairingKinds.DISPLAY_PIN
        )
        return result.status == DevicePairingResultStatus.PAIRED
    finally:
        custom.remove_pairing_requested(token)


# ---- QThread wrappers so the GUI thread never blocks on asyncio.run ----

class DiscoveryWorker(QThread):
    found = pyqtSignal(list)   # list of device dicts, see scan_for_btchat_devices
    error = pyqtSignal(str)

    def __init__(self, timeout: float = 8.0, parent=None):
        super().__init__(parent)
        self.timeout = timeout

    def run(self):
        try:
            devices = asyncio.run(scan_for_btchat_devices(self.timeout))
            self.found.emit(devices)
        except Exception as e:  # noqa: BLE001
            self.error.emit(f"Scan failed: {e}")


class PairWorker(QThread):
    paired = pyqtSignal(bool)
    error = pyqtSignal(str)

    def __init__(self, device_id: str, parent=None):
        super().__init__(parent)
        self.device_id = device_id

    def run(self):
        try:
            ok = asyncio.run(pair_device(self.device_id))
            self.paired.emit(ok)
        except Exception as e:  # noqa: BLE001
            self.error.emit(f"Pairing failed: {e}")