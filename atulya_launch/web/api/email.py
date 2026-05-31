"""Email management API (Postfix / Dovecot) with SQLite backend."""

import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user
from atulya_launch.web.database import connect

router = APIRouter(prefix="/api/email", tags=["email"])


class AccountCreate(BaseModel):
    email: str
    password: str
    quota_mb: int = 1024


class PasswordChange(BaseModel):
    new_password: str


class AliasCreate(BaseModel):
    source: str
    destination: str


class ForwarderCreate(BaseModel):
    source: str
    destination: str


# ── Accounts ──────────────────────────────────────────────────────────────

@router.get("/accounts")
def list_accounts(user: dict = Depends(get_current_user)):
    with connect() as conn:
        rows = conn.execute("SELECT domain, mailbox, quota_mb, created_at FROM email_accounts ORDER BY domain, mailbox").fetchall()
    accounts = [dict(r) for r in rows]
    return {"accounts": accounts}


@router.post("/accounts")
def create_account(body: AccountCreate, user: dict = Depends(get_current_user)):
    parts = body.email.split("@")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise HTTPException(status_code=400, detail="Invalid email format")
    mailbox, domain = parts
    from atulya_launch.web.auth import hash_password
    pw_hash = hash_password(body.password)
    with connect() as conn:
        existing = conn.execute(
            "SELECT id FROM email_accounts WHERE domain = ? AND mailbox = ?", (domain, mailbox)
        ).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="Account already exists")
        conn.execute(
            "INSERT INTO email_accounts (domain, mailbox, password_hash, quota_mb, created_at) VALUES (?, ?, ?, ?, ?)",
            (domain, mailbox, pw_hash, body.quota_mb, datetime.datetime.utcnow().isoformat() + "Z"),
        )
    _apply_mail_config(domain)
    return {"status": "created", "email": body.email}


@router.delete("/accounts/{account}")
def delete_account(account: str, user: dict = Depends(get_current_user)):
    parts = account.split("@")
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail="Invalid email format")
    mailbox, domain = parts
    with connect() as conn:
        cursor = conn.execute(
            "DELETE FROM email_accounts WHERE domain = ? AND mailbox = ?", (domain, mailbox)
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Account not found")
    _apply_mail_config(domain)
    return {"status": "deleted", "email": account}


@router.put("/accounts/{account}/password")
def change_password(account: str, body: PasswordChange, user: dict = Depends(get_current_user)):
    parts = account.split("@")
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail="Invalid email format")
    mailbox, domain = parts
    from atulya_launch.web.auth import hash_password
    pw_hash = hash_password(body.new_password)
    with connect() as conn:
        cursor = conn.execute(
            "UPDATE email_accounts SET password_hash = ? WHERE domain = ? AND mailbox = ?",
            (pw_hash, domain, mailbox),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Account not found")
    return {"status": "password changed", "email": account}


# ── Aliases ───────────────────────────────────────────────────────────────

@router.get("/aliases")
def list_aliases(user: dict = Depends(get_current_user)):
    return {"aliases": _load_email().get("aliases", {})}


@router.post("/aliases")
def create_alias(body: AliasCreate, user: dict = Depends(get_current_user)):
    data = _load_email()
    aliases = data.setdefault("aliases", {})
    aliases[body.source] = body.destination
    _save_email(data)
    return {"status": "created", "source": body.source, "destination": body.destination}


@router.delete("/aliases/{alias}")
def delete_alias(alias: str, user: dict = Depends(get_current_user)):
    data = _load_email()
    aliases = data.get("aliases", {})
    if alias not in aliases:
        raise HTTPException(status_code=404, detail="Alias not found")
    del aliases[alias]
    _save_email(data)
    return {"status": "deleted", "alias": alias}


# ── Forwarders ────────────────────────────────────────────────────────────

@router.get("/forwarders")
def list_forwarders(user: dict = Depends(get_current_user)):
    return {"forwarders": _load_email().get("forwarders", {})}


@router.post("/forwarders")
def create_forwarder(body: ForwarderCreate, user: dict = Depends(get_current_user)):
    data = _load_email()
    forwarders = data.setdefault("forwarders", {})
    forwarders[body.source] = body.destination
    _save_email(data)
    return {"status": "created", "source": body.source, "destination": body.destination}


# ── Mail driver integration ──────────────────────────────────────────────

def _apply_mail_config(domain: str):
    """Apply mail configuration through the platform driver."""
    try:
        from atulya_launch.drivers import get_platform_driver
        driver = get_platform_driver(dry_run=utils.is_linux() is False)
        with connect() as conn:
            rows = conn.execute(
                "SELECT mailbox FROM email_accounts WHERE domain = ?", (domain,)
            ).fetchall()
        mailboxes = [{"mailbox": r["mailbox"]} for r in rows]
        driver.mail.apply_domain(domain, mailboxes)
    except Exception:
        pass


def _load_email() -> dict:
    """Load email data (aliases, forwarders) from JSON for backward compat."""
    p = utils.CONFIG_DIR / "email.json"
    if not p.exists():
        return {"accounts": {}, "aliases": {}, "forwarders": {}}
    import json
    return json.loads(p.read_text())


def _save_email(data: dict):
    """Save email data (aliases, forwarders) to JSON."""
    p = utils.CONFIG_DIR / "email.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    import json
    p.write_text(json.dumps(data, indent=2))
