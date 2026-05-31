import sqlite3
import json
from pathlib import Path
from datetime import datetime, timedelta
from contextlib import contextmanager

_db_path: Path = None
_initialized = False

SCHEMA = """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'admin',
        created_at TEXT NOT NULL,
        last_login TEXT
    );
    CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS dns_zones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        domain TEXT UNIQUE NOT NULL,
        soa_primary TEXT,
        soa_email TEXT,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS dns_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        zone_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        type TEXT NOT NULL,
        value TEXT NOT NULL,
        ttl INTEGER DEFAULT 3600,
        created_at TEXT NOT NULL,
        FOREIGN KEY (zone_id) REFERENCES dns_zones(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS email_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        domain TEXT NOT NULL,
        mailbox TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        quota_mb INTEGER DEFAULT 1024,
        created_at TEXT NOT NULL,
        UNIQUE(domain, mailbox)
    );
    CREATE TABLE IF NOT EXISTS databases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        db_type TEXT NOT NULL DEFAULT 'mysql',
        username TEXT,
        password_hash TEXT,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS ssl_certs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        domain TEXT NOT NULL,
        cert_path TEXT,
        key_path TEXT,
        issuer TEXT,
        expires_at TEXT,
        auto_renew INTEGER DEFAULT 1,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        time TEXT NOT NULL,
        user TEXT,
        action TEXT NOT NULL,
        status TEXT NOT NULL,
        details TEXT
    );
"""


def reset_db():
    global _db_path, _initialized
    _db_path = None
    _initialized = False


def init_db(config_dir: Path, force=False):
    global _db_path, _initialized
    if _initialized and not force:
        return
    _db_path = config_dir / "panel.db"
    with connect() as cur:
        cur.executescript(SCHEMA)
    _initialized = True


@contextmanager
def connect():
    if _db_path is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    conn = sqlite3.connect(str(_db_path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def audit_log(user, action, status, details=None):
    if _db_path is None:
        return
    try:
        conn = sqlite3.connect(str(_db_path), timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute(
                "INSERT INTO audit_log (time, user, action, status, details) VALUES (?, ?, ?, ?, ?)",
                (datetime.utcnow().isoformat() + "Z", user, action, status, json.dumps(details or {})),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass
