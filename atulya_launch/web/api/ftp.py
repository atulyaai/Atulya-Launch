"""FTP account management API (vsftpd)."""

import os
import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user
from atulya_launch.web.database import connect

router = APIRouter(prefix="/api/ftp", tags=["ftp"])

FTP_CONF = "/etc/vsftpd.conf"


class FTPAccountCreate(BaseModel):
    username: str
    password: str
    home_dir: Optional[str] = None
    quota_mb: int = 1024


class FTPPasswordChange(BaseModel):
    new_password: str


def _hash_password(password: str) -> str:
    """Hash password using passlib (cross-platform, Python 3.13+ safe)."""
    try:
        from passlib.hash import sha512_crypt
        return sha512_crypt.using(rounds=5000).hash(password)
    except ImportError:
        import hashlib
        import secrets
        salt = secrets.token_hex(16)
        hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
        return f"$pbkdf2-sha256$100000${salt}${hashed.hex()}"


def _load_ftp() -> dict:
    with connect() as conn:
        rows = conn.execute("SELECT username, home_dir, quota_mb, created_at FROM ftp_accounts").fetchall()
    return {r["username"]: dict(r) for r in rows}


def _save_ftp(data: dict):
    with connect() as conn:
        conn.execute("DELETE FROM ftp_accounts")
        for username, info in data.items():
            conn.execute(
                "INSERT INTO ftp_accounts (username, home_dir, quota_mb, created_at) VALUES (?, ?, ?, ?)",
                (username, info.get("home_dir", ""), info.get("quota_mb", 1024), info.get("created_at", "")),
            )


@router.get("/accounts")
def list_accounts(user: dict = Depends(get_current_user)):
    return {"accounts": _load_ftp()}


@router.post("/accounts")
def create_account(body: FTPAccountCreate, user: dict = Depends(get_current_user)):
    data = _load_ftp()
    if body.username in data:
        raise HTTPException(status_code=409, detail="FTP account already exists")
    home = body.home_dir or f"/home/{body.username}"
    if utils.is_linux():
        utils.run_command(["useradd", "-m", "-d", home, "-s", "/usr/sbin/nologin", body.username], check=False)
        hashed = _hash_password(body.password)
        utils.run_command(["chpasswd"], check=False)
        import subprocess
        subprocess.run(f"echo '{body.username}:{body.password}' | chpasswd", shell=True, check=False)
    from datetime import datetime
    with connect() as conn:
        conn.execute(
            "INSERT INTO ftp_accounts (username, home_dir, quota_mb, created_at) VALUES (?, ?, ?, ?)",
            (body.username, home, body.quota_mb, datetime.now().isoformat()),
        )
    return {"status": "created", "username": body.username}


@router.delete("/accounts/{username}")
def delete_account(username: str, user: dict = Depends(get_current_user)):
    data = _load_ftp()
    if username not in data:
        raise HTTPException(status_code=404, detail="Account not found")
    with connect() as conn:
        conn.execute("DELETE FROM ftp_accounts WHERE username = ?", (username,))
    if utils.is_linux():
        utils.run_command(["userdel", "-r", username], check=False)
    return {"status": "deleted", "username": username}


@router.put("/accounts/{username}/password")
def change_password(username: str, body: FTPPasswordChange, user: dict = Depends(get_current_user)):
    data = _load_ftp()
    if username not in data:
        raise HTTPException(status_code=404, detail="Account not found")
    if utils.is_linux():
        import subprocess
        subprocess.run(f"echo '{username}:{body.new_password}' | chpasswd", shell=True, check=False)
    return {"status": "password changed", "username": username}
