"""Database initialization and connection management for Atulya Launch.

Uses SQLite with WAL mode and provides a context-managed connection,
schema creation/migration, and an audit log helper.
"""

import os
import sqlite3
import json
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager
from typing import Any, Iterator

_db_path: Path | None = None
_initialized: bool = False

SCHEMA_VERSION: int = 4

SCHEMA: str = """
    CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL
    );
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
    CREATE TABLE IF NOT EXISTS plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        sites_limit INTEGER DEFAULT 0,
        disk_limit_mb INTEGER DEFAULT 0,
        db_limit INTEGER DEFAULT 0,
        email_limit INTEGER DEFAULT 0,
        bandwidth_limit_mb INTEGER DEFAULT 0,
        price_monthly REAL DEFAULT 0,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS user_plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        plan_id INTEGER NOT NULL,
        assigned_at TEXT NOT NULL,
        expires_at TEXT,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (plan_id) REFERENCES plans(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS cron_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        domain TEXT,
        command TEXT NOT NULL,
        schedule TEXT NOT NULL,
        enabled INTEGER DEFAULT 1,
        created_at TEXT NOT NULL,
        last_run TEXT,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS migrations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT NOT NULL,
        domain TEXT,
        status TEXT NOT NULL DEFAULT 'pending',
        import_data TEXT,
        created_at TEXT NOT NULL,
        completed_at TEXT
    );
    CREATE TABLE IF NOT EXISTS node_apps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        domain TEXT,
        app_type TEXT NOT NULL,
        entry_point TEXT NOT NULL,
        port INTEGER,
        process_id INTEGER,
        status TEXT DEFAULT 'stopped',
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS servers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        host TEXT NOT NULL,
        port INTEGER DEFAULT 22,
        username TEXT,
        auth_type TEXT DEFAULT 'password',
        auth_data TEXT,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS branding (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT UNIQUE NOT NULL,
        value TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS reseller_clients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reseller_id INTEGER NOT NULL,
        client_id INTEGER NOT NULL UNIQUE,
        assigned_at TEXT NOT NULL,
        FOREIGN KEY (reseller_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (client_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS reseller_allocations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reseller_id INTEGER NOT NULL UNIQUE,
        max_clients INTEGER DEFAULT 5,
        max_sites INTEGER DEFAULT 10,
        max_dbs INTEGER DEFAULT 5,
        max_emails INTEGER DEFAULT 10,
        disk_limit_mb INTEGER DEFAULT 1024,
        created_at TEXT NOT NULL,
        FOREIGN KEY (reseller_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS rate_limit_attempts (
        key TEXT NOT NULL,
        attempted_at REAL NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_rate_limit_attempts_key_time
        ON rate_limit_attempts (key, attempted_at);
    CREATE TABLE IF NOT EXISTS flash_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_token TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT 'info',
        message TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
"""


def reset_db() -> None:
    """Reset the global database path and initialization flag."""
    global _db_path, _initialized
    _db_path = None
    _initialized = False


def init_db(config_dir: Path, force: bool = False) -> None:
    """Initialize the SQLite database, creating tables and applying migrations."""
    global _db_path, _initialized
    if _initialized and not force:
        return
    _db_path = config_dir / "panel.db"
    try:
        _init_schema()
    except sqlite3.OperationalError:
        import tempfile
        _db_path = Path(tempfile.gettempdir()) / "atulya-launch" / "panel.db"
        _db_path.parent.mkdir(parents=True, exist_ok=True)
        _init_schema()
    _initialized = True


def _init_schema() -> None:
    """Create tables and apply lightweight migrations on the selected DB path."""
    with connect_raw() as conn:
        conn.executescript(SCHEMA)
        row: Any = conn.execute("SELECT MAX(version) as v FROM schema_version").fetchone()
        current_version: int = row["v"] if row and row["v"] else 0
        if current_version < 3:
            try:
                conn.executescript("ALTER TABLE users ADD COLUMN parent_user_id INTEGER REFERENCES users(id);")
            except Exception:
                pass
        if current_version < SCHEMA_VERSION:
            conn.execute(
                "INSERT OR REPLACE INTO schema_version (version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, datetime.utcnow().isoformat() + "Z"),
            )


def connect_raw() -> sqlite3.Connection:
    """Open a raw SQLite connection with row factory and PRAGMAs set."""
    if _db_path is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    conn: sqlite3.Connection = sqlite3.connect(str(_db_path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Context manager that yields a connection and commits on success."""
    conn: sqlite3.Connection = connect_raw()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def audit_log(user: str, action: str, status: str, details: dict | None = None) -> None:
    """Write an entry to the audit_log table."""
    if _db_path is None:
        return
    try:
        conn: sqlite3.Connection = sqlite3.connect(str(_db_path), timeout=5)
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
