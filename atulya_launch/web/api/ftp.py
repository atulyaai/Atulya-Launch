"""FTP account management API (vsftpd)."""

import os
import crypt
import subprocess
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/ftp", tags=["ftp"])

FTP_CONF = "/etc/vsftpd.conf"


class FTPAccountCreate(BaseModel):
    username: str
    password: str
    home_dir: Optional[str] = None
    quota_mb: int = 1024


class FTPPasswordChange(BaseModel):
    new_password: str


def _ftp_users_file():
    return utils.CONFIG_DIR / "ftp_accounts.json"


def _load_ftp() -> dict:
    p = _ftp_users_file()
    if not p.exists():
        return {}
    import json
    return json.loads(p.read_text())


def _save_ftp(data: dict):
    p = _ftp_users_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    import json
    p.write_text(json.dumps(data, indent=2))


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
        hashed = crypt.crypt(body.password, crypt.mksalt(crypt.METHOD_SHA256))
        utils.run_command(["chpasswd"], check=False)
        subprocess.run(f"echo '{body.username}:{body.password}' | chpasswd", shell=True, check=False)
    data[body.username] = {
        "username": body.username,
        "home_dir": home,
        "quota_mb": body.quota_mb,
        "created_at": __import__("datetime").datetime.now().isoformat(),
    }
    _save_ftp(data)
    return {"status": "created", "username": body.username}


@router.delete("/accounts/{username}")
def delete_account(username: str, user: dict = Depends(get_current_user)):
    data = _load_ftp()
    if username not in data:
        raise HTTPException(status_code=404, detail="Account not found")
    del data[username]
    _save_ftp(data)
    if utils.is_linux():
        utils.run_command(["userdel", "-r", username], check=False)
    return {"status": "deleted", "username": username}


@router.put("/accounts/{username}/password")
def change_password(username: str, body: FTPPasswordChange, user: dict = Depends(get_current_user)):
    data = _load_ftp()
    if username not in data:
        raise HTTPException(status_code=404, detail="Account not found")
    if utils.is_linux():
        subprocess.run(f"echo '{username}:{body.new_password}' | chpasswd", shell=True, check=False)
    return {"status": "password changed", "username": username}
