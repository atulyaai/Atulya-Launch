"""Two-factor authentication API."""

import os
import json
import secrets
import hashlib
import hmac
import struct
import time
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/2fa", tags=["2fa"])

TWOFACONFIG_FILE = utils.CONFIG_DIR / "twofa.json"


def _load_2fa_config() -> dict:
    if TWOFACONFIG_FILE.exists():
        with open(TWOFACONFIG_FILE, "r") as f:
            return json.load(f) or {}
    return {}


def _save_2fa_config(data: dict):
    utils.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(TWOFACONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _generate_totp_secret(length=20) -> str:
    return secrets.token_hex(length)[:32]


def _totp_code(secret: str, time_step=30) -> str:
    key = bytes.fromhex(secret)
    counter = int(time.time()) // time_step
    counter_bytes = struct.pack(">Q", counter)
    h = hmac.new(key, counter_bytes, hashlib.sha1).digest()
    offset = h[-1] & 0x0F
    code = struct.unpack(">I", h[offset:offset+4])[0] & 0x7FFFFFFF
    return str(code % 1000000).zfill(6)


def _generate_qr_data_uri(secret: str, username: str) -> str:
    import base64
    otpauth = f"otpauth://totp/AtulyaLaunch:{username}?secret={secret}&issuer=AtulyaLaunch&digits=6&period=30"
    # Return as data URI for QR code generation
    return f"data:text/plain,{otpauth}"


class VerifyRequest(BaseModel):
    code: str


class DisableRequest(BaseModel):
    code: str


@router.get("/status")
def twofa_status(user: dict = Depends(get_current_user)):
    config = _load_2fa_config()
    username = user.get("sub", "admin")
    user_2fa = config.get(username, {})
    return {"enabled": user_2fa.get("enabled", False), "username": username}


@router.post("/enable")
def enable_2fa(user: dict = Depends(get_current_user)):
    config = _load_2fa_config()
    username = user.get("sub", "admin")
    if username in config and config[username].get("enabled"):
        raise HTTPException(status_code=400, detail="2FA is already enabled")
    secret = _generate_totp_secret()
    config[username] = {
        "secret": secret,
        "enabled": False,
        "pending": True,
    }
    _save_2fa_config(config)
    qr_uri = _generate_qr_data_uri(secret, username)
    return {
        "secret": secret,
        "qr_code": qr_uri,
        "message": "Scan the QR code with your authenticator app, then verify with /api/2fa/verify",
    }


@router.post("/verify")
def verify_2fa(body: VerifyRequest, user: dict = Depends(get_current_user)):
    config = _load_2fa_config()
    username = user.get("sub", "admin")
    if username not in config:
        raise HTTPException(status_code=400, detail="2FA not configured. Call /api/2fa/enable first.")
    user_2fa = config[username]
    secret = user_2fa.get("secret", "")
    if not secret:
        raise HTTPException(status_code=400, detail="No secret found. Re-enable 2FA.")
    code = body.code
    # Check current and previous time steps for clock drift
    for offset in (-1, 0, 1):
        key = bytes.fromhex(secret)
        counter = (int(time.time()) // 30) + offset
        counter_bytes = struct.pack(">Q", counter)
        h = hmac.new(key, counter_bytes, hashlib.sha1).digest()
        idx = h[-1] & 0x0F
        expected = struct.unpack(">I", h[idx:idx+4])[0] & 0x7FFFFFFF
        expected_code = str(expected % 1000000).zfill(6)
        if hmac.compare_digest(code, expected_code):
            config[username]["enabled"] = True
            config[username]["pending"] = False
            _save_2fa_config(config)
            return {"status": "2FA enabled successfully"}
    raise HTTPException(status_code=400, detail="Invalid code")


@router.post("/disable")
def disable_2fa(body: DisableRequest, user: dict = Depends(get_current_user)):
    config = _load_2fa_config()
    username = user.get("sub", "admin")
    if username not in config or not config[username].get("enabled"):
        raise HTTPException(status_code=400, detail="2FA is not enabled")
    secret = config[username].get("secret", "")
    # Verify current code before disabling
    for offset in (-1, 0, 1):
        key = bytes.fromhex(secret)
        counter = (int(time.time()) // 30) + offset
        counter_bytes = struct.pack(">Q", counter)
        h = hmac.new(key, counter_bytes, hashlib.sha1).digest()
        idx = h[-1] & 0x0F
        expected = struct.unpack(">I", h[idx:idx+4])[0] & 0x7FFFFFFF
        expected_code = str(expected % 1000000).zfill(6)
        if hmac.compare_digest(body.code, expected_code):
            config[username]["enabled"] = False
            _save_2fa_config(config)
            return {"status": "2FA disabled"}
    raise HTTPException(status_code=400, detail="Invalid code")


@router.get("/backup-codes")
def get_backup_codes(user: dict = Depends(get_current_user)):
    config = _load_2fa_config()
    username = user.get("sub", "admin")
    if username not in config or not config[username].get("enabled"):
        raise HTTPException(status_code=400, detail="2FA must be enabled first")
    codes = [secrets.token_hex(4).upper() for _ in range(10)]
    config[username]["backup_codes"] = codes
    _save_2fa_config(config)
    return {"backup_codes": codes, "message": "Save these codes. They will not be shown again."}
