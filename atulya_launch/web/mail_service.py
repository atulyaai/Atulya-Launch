"""SQLite-backed mail helpers with platform-driver apply support."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from atulya_launch.drivers import get_platform_driver

from .auth import hash_password
from .database import connect


def _driver_dry_run() -> bool:
    return os.environ.get("ATULYA_DRIVER_APPLY", "").lower() not in {"1", "true", "yes"}


def list_accounts(domain: str | None = None) -> list[dict[str, Any]]:
    """Return email accounts, optionally filtered by domain."""
    query = "SELECT id, domain, mailbox, quota_mb, created_at FROM email_accounts"
    params: tuple[Any, ...] = ()
    if domain:
        query += " WHERE domain = ?"
        params = (domain,)
    query += " ORDER BY domain, mailbox"
    with connect() as conn:
        return [dict(row) for row in conn.execute(query, params).fetchall()]


def create_account(domain: str, mailbox: str, password: str, quota_mb: int = 1024) -> dict[str, Any]:
    """Create an email account in SQLite, then apply the domain mailbox map."""
    with connect() as conn:
        cursor = conn.execute(
            "INSERT INTO email_accounts (domain, mailbox, password_hash, quota_mb, created_at) VALUES (?, ?, ?, ?, ?)",
            (domain, mailbox, hash_password(password), quota_mb, datetime.utcnow().isoformat() + "Z"),
        )
        account_id = int(cursor.lastrowid)
    apply = apply_domain(domain)
    account = get_account(account_id)
    account["apply"] = apply
    return account


def delete_account(account_id: int) -> dict[str, Any]:
    """Delete an email account, then apply the affected domain mailbox map."""
    with connect() as conn:
        row = conn.execute("SELECT domain, mailbox FROM email_accounts WHERE id = ?", (account_id,)).fetchone()
        if not row:
            raise KeyError("Email account not found")
        domain = row["domain"]
        mailbox = row["mailbox"]
        conn.execute("DELETE FROM email_accounts WHERE id = ?", (account_id,))
    apply = apply_domain(domain)
    return {"id": account_id, "domain": domain, "mailbox": mailbox, "apply": apply}


def get_account(account_id: int) -> dict[str, Any]:
    """Return one email account without the password hash."""
    with connect() as conn:
        row = conn.execute(
            "SELECT id, domain, mailbox, quota_mb, created_at FROM email_accounts WHERE id = ?",
            (account_id,),
        ).fetchone()
        if not row:
            raise KeyError("Email account not found")
        return dict(row)


def apply_domain(domain: str) -> dict[str, Any]:
    """Apply all mailboxes for a domain through the current platform mail driver."""
    accounts = list_accounts(domain)
    driver = get_platform_driver(dry_run=_driver_dry_run())
    result = driver.mail.apply_domain(domain, accounts)
    return {
        "ok": result.ok,
        "action": result.action,
        "changed": result.changed,
        "message": result.message,
        "commands": result.commands,
        "files": result.files,
        "dry_run": _driver_dry_run(),
    }
