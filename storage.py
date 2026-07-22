"""
Local message history + identity storage (SQLite).

Kept deliberately simple for Phase 1: one contact = one device (MAC
address). This schema is intentionally future-friendly for Phase 3+
(multiple contacts, file transfer records) without needing a migration
right away.
"""
import sqlite3
import uuid
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path.home() / ".btchat" / "btchat.db"


def _ensure_dir():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def _connect():
    _ensure_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS identity (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS contacts (
                mac_address TEXT PRIMARY KEY,
                display_name TEXT,
                last_seen REAL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                msg_id TEXT PRIMARY KEY,
                contact_mac TEXT NOT NULL,
                sender_id TEXT NOT NULL,
                direction TEXT NOT NULL,   -- 'in' or 'out'
                text TEXT NOT NULL,
                timestamp REAL NOT NULL,
                delivered INTEGER DEFAULT 0
            )
        """)


def get_or_create_local_id() -> str:
    with _connect() as conn:
        row = conn.execute("SELECT value FROM identity WHERE key='local_id'").fetchone()
        if row:
            return row["value"]
        new_id = uuid.uuid4().hex
        conn.execute("INSERT INTO identity (key, value) VALUES ('local_id', ?)", (new_id,))
        return new_id


def get_display_name(default: str = "Me") -> str:
    with _connect() as conn:
        row = conn.execute("SELECT value FROM identity WHERE key='display_name'").fetchone()
        return row["value"] if row else default


def set_display_name(name: str):
    with _connect() as conn:
        conn.execute("""
            INSERT INTO identity (key, value) VALUES ('display_name', ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """, (name,))


def upsert_contact(mac_address: str, display_name: str = None, last_seen: float = None):
    with _connect() as conn:
        existing = conn.execute("SELECT * FROM contacts WHERE mac_address=?", (mac_address,)).fetchone()
        if existing:
            conn.execute("""
                UPDATE contacts SET
                    display_name = COALESCE(?, display_name),
                    last_seen = COALESCE(?, last_seen)
                WHERE mac_address=?
            """, (display_name, last_seen, mac_address))
        else:
            conn.execute("""
                INSERT INTO contacts (mac_address, display_name, last_seen)
                VALUES (?, ?, ?)
            """, (mac_address, display_name, last_seen))


def list_contacts():
    with _connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM contacts ORDER BY last_seen DESC")]


def save_message(msg_id: str, contact_mac: str, sender_id: str, direction: str, text: str, timestamp: float, delivered: bool = False):
    with _connect() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO messages (msg_id, contact_mac, sender_id, direction, text, timestamp, delivered)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (msg_id, contact_mac, sender_id, direction, text, timestamp, int(delivered)))


def mark_delivered(msg_id: str):
    with _connect() as conn:
        conn.execute("UPDATE messages SET delivered=1 WHERE msg_id=?", (msg_id,))


def get_history(contact_mac: str, limit: int = 200):
    with _connect() as conn:
        rows = conn.execute("""
            SELECT * FROM messages WHERE contact_mac=?
            ORDER BY timestamp ASC LIMIT ?
        """, (contact_mac, limit)).fetchall()
        return [dict(r) for r in rows]