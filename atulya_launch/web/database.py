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
