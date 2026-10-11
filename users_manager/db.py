import os
import sqlite3
import threading
from pathlib import Path

_write_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    chat_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bot_users (
    chat_id INTEGER NOT NULL,
    platform TEXT NOT NULL,
    bot_name TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    PRIMARY KEY (chat_id, platform, bot_name)
);
"""


def resolve_db_path(db_path=None) -> Path:
    if db_path is not None:
        return Path(db_path)
    env = os.getenv("USERS_DB_PATH")
    if env:
        return Path(env)
    raise RuntimeError("USERS_DB_PATH is not set and no db_path was given")


def connect(db_path=None) -> sqlite3.Connection:
    path = resolve_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def init_db(db_path=None) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)


def record_user(
    db_path,
    chat_id: int,
    username,
    first_name,
    last_name,
    platform: str,
    bot_name: str,
    now_iso: str,
) -> None:
    with _write_lock:
        with connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO users (chat_id, username, first_name, last_name, first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    username=excluded.username,
                    first_name=excluded.first_name,
                    last_name=excluded.last_name,
                    last_seen=excluded.last_seen
                """,
                (chat_id, username, first_name, last_name, now_iso, now_iso),
            )
            conn.execute(
                """
                INSERT INTO bot_users (chat_id, platform, bot_name, first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(chat_id, platform, bot_name) DO UPDATE SET
                    last_seen=excluded.last_seen
                """,
                (chat_id, platform, bot_name, now_iso, now_iso),
            )


def count_users(db_path=None) -> int:
    with connect(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) FROM users").fetchone()
        return int(row[0])


def count_bot_users(db_path=None) -> dict:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT platform, bot_name, COUNT(*) FROM bot_users GROUP BY platform, bot_name ORDER BY platform, bot_name"
        ).fetchall()
        return {(platform, bot_name): count for platform, bot_name, count in rows}
