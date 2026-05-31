"""Email management API (Postfix / Dovecot)."""

import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

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


def _email_file():
    return utils.CONFIG_DIR / "email.json"


def _load_email() -> dict:
    p = _email_file()
    if not p.exists():
        return {"accounts": {}, "aliases": {}, "forwarders": {}}
    import json
    return json.loads(p.read_text())


def _save_email(data: dict):
    p = _email_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    import json
    p.write_text(json.dumps(data, indent=2))


# ── Accounts ──────────────────────────────────────────────────────────────

@router.get("/accounts")
def list_accounts(user: dict = Depends(get_current_user)):
    data = _load_email()
    accounts = {}
    for k, v in data.get("accounts", {}).items():
        safe = {**v}
        safe.pop("password_hash", None)
        accounts[k] = safe
    return {"accounts": accounts}


@router.post("/accounts")
def create_account(body: AccountCreate, user: dict = Depends(get_current_user)):
    data = _load_email()
    if body.email in data.get("accounts", {}):
        raise HTTPException(status_code=409, detail="Account already exists")
    from passlib.context import CryptContext
    ctx = CryptContext(schemes=["sha512_crypt"], deprecated="auto")
    accounts = data.setdefault("accounts", {})
    accounts[body.email] = {
        "email": body.email,
        "password_hash": ctx.hash(body.password),
        "quota_mb": body.quota_mb,
        "created_at": datetime.datetime.now().isoformat(),
    }
    _save_email(data)
    if utils.is_linux():
        utils.run_command(
            ["useradd", "-m", "-s", "/usr/sbin/nologin", body.email.split("@")[0]],
            check=False,
        )
    return {"status": "created", "email": body.email}


@router.delete("/accounts/{account}")
def delete_account(account: str, user: dict = Depends(get_current_user)):
    data = _load_email()
    if account not in data.get("accounts", {}):
        raise HTTPException(status_code=404, detail="Account not found")
    del data["accounts"][account]
    _save_email(data)
    return {"status": "deleted", "email": account}


@router.put("/accounts/{account}/password")
def change_password(account: str, body: PasswordChange, user: dict = Depends(get_current_user)):
    data = _load_email()
    if account not in data.get("accounts", {}):
        raise HTTPException(status_code=404, detail="Account not found")
    from passlib.context import CryptContext
    ctx = CryptContext(schemes=["sha512_crypt"], deprecated="auto")
    data["accounts"][account]["password_hash"] = ctx.hash(body.new_password)
    _save_email(data)
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
