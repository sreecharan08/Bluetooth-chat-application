"""
Wire protocol for BTChat.

Every message sent over the RFCOMM socket is:
    [4-byte big-endian length][UTF-8 JSON payload]

The length prefix means we never have to guess where one message ends
and the next begins, even if TCP/RFCOMM splits or coalesces packets.
"""
import json
import struct
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum


class MessageType(str, Enum):
    TEXT = "text"
    ACK = "ack"
    TYPING = "typing"
    HELLO = "hello"        # sent right after connect, carries sender identity
    PING = "ping"
    PONG = "pong"


HEADER_SIZE = 4  # bytes, unsigned big-endian length prefix


@dataclass
class Envelope:
    type: MessageType
    sender_id: str
    payload: dict = field(default_factory=dict)
    msg_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: float = field(default_factory=time.time)

    def to_bytes(self) -> bytes:
        data = json.dumps(asdict(self), default=str).encode("utf-8")
        return struct.pack(">I", len(data)) + data

    @staticmethod
    def from_dict(d: dict) -> "Envelope":
        return Envelope(
            type=MessageType(d["type"]),
            sender_id=d["sender_id"],
            payload=d.get("payload", {}),
            msg_id=d.get("msg_id") or uuid.uuid4().hex,
            timestamp=d.get("timestamp") if d.get("timestamp") is not None else time.time(),
        )


class FrameReader:
    """
    Feed raw bytes in as they arrive from the socket; get back complete
    Envelope objects as soon as they're fully received. Handles partial
    reads/writes transparently.
    """

    def __init__(self):
        self._buf = bytearray()

    def feed(self, chunk: bytes):
        self._buf.extend(chunk)

    def pop_messages(self):
        messages = []
        while True:
            if len(self._buf) < HEADER_SIZE:
                break
            length = struct.unpack(">I", self._buf[:HEADER_SIZE])[0]
            total = HEADER_SIZE + length
            if len(self._buf) < total:
                break
            raw = self._buf[HEADER_SIZE:total]
            del self._buf[:total]
            try:
                d = json.loads(raw.decode("utf-8"))
                messages.append(Envelope.from_dict(d))
            except (json.JSONDecodeError, KeyError, ValueError):
                # Corrupt frame - drop it rather than crashing the reader.
                continue
        return messages


def make_text_message(sender_id: str, text: str) -> Envelope:
    return Envelope(type=MessageType.TEXT, sender_id=sender_id, payload={"text": text})


def make_hello(sender_id: str, display_name: str) -> Envelope:
    return Envelope(type=MessageType.HELLO, sender_id=sender_id, payload={"display_name": display_name})


def make_ack(sender_id: str, for_msg_id: str) -> Envelope:
    return Envelope(type=MessageType.ACK, sender_id=sender_id, payload={"for_msg_id": for_msg_id})