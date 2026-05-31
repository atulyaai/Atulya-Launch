"""Two-factor authentication API — backed by SQLite."""

import hashlib
import json
import secrets
import hmac
import struct
import time
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch.web.auth import get_current_user
from atulya_launch.web.database import connect

router = APIRouter(prefix="/api/2fa", tags=["2fa"])


def _generate_totp_secret(length: int = 20) -> str:
    return secrets.token_hex(length)[:32]


def _verify_totp(secret: str, code: str) -> bool:
    for offset in (-1, 0, 1):
        try:
            key = bytes.fromhex(secret)
            counter = (int(time.time()) // 30) + offset
            counter_bytes = struct.pack(">Q", counter)
            h = hmac.new(key, counter_bytes, hashlib.sha1).digest()
            idx = h[-1] & 0x0F
            expected = struct.unpack(">I", h[idx:idx+4])[0] & 0x7FFFFFFF
            expected_code = str(expected % 1000000).zfill(6)
            if hmac.compare_digest(code, expected_code):
                return True
        except Exception:
            continue
    return False


def _get_user_2fa(username: str) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT secret, enabled, pending, backup_codes FROM twofa_settings WHERE username = ?",
            (username,),
        ).fetchone()
    if not row:
        return None
    entry = dict(row)
    try:
        entry["backup_codes"] = json.loads(entry.get("backup_codes") or "[]")
    except Exception:
        entry["backup_codes"] = []
    entry["enabled"] = bool(entry.get("enabled"))
    entry["pending"] = bool(entry.get("pending"))
    return entry


class VerifyRequest(BaseModel):
    code: str


class DisableRequest(BaseModel):
    code: str


@router.get("/status")
def twofa_status(user: dict = Depends(get_current_user)):
    username = user.get("sub", "admin")
    user_2fa = _get_user_2fa(username)
    return {"enabled": user_2fa["enabled"] if user_2fa else False, "username": username}


@router.post("/enable")
def enable_2fa(user: dict = Depends(get_current_user)):
    username = user.get("sub", "admin")
    existing = _get_user_2fa(username)
    if existing and existing.get("enabled"):
        raise HTTPException(status_code=400, detail="2FA is already enabled")
    secret = _generate_totp_secret()
    now = __import__("datetime").datetime.utcnow().isoformat() + "Z"
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO twofa_settings (username, secret, enabled, pending, backup_codes, created_at) VALUES (?, ?, 0, 1, '[]', ?)",
            (username, secret, now),
        )
    otpauth = f"otpauth://totp/AtulyaLaunch:{username}?secret={secret}&issuer=AtulyaLaunch&digits=6&period=30"
    return {
        "secret": secret,
        "qr_code": f"data:text/plain,{otpauth}",
        "message": "Scan the QR code with your authenticator app, then verify with /api/2fa/verify",
    }


@router.post("/verify")
def verify_2fa(body: VerifyRequest, user: dict = Depends(get_current_user)):
    username = user.get("sub", "admin")
    user_2fa = _get_user_2fa(username)
    if not user_2fa:
        raise HTTPException(status_code=400, detail="2FA not configured. Call /api/2fa/enable first.")
    secret = user_2fa.get("secret", "")
    if not secret:
        raise HTTPException(status_code=400, detail="No secret found. Re-enable 2FA.")
    import hashlib as _hashlib  # noqa: F811
    for offset in (-1, 0, 1):
        key = bytes.fromhex(secret)
        counter = (int(time.time()) // 30) + offset
        counter_bytes = struct.pack(">Q", counter)
        h = hmac.new(key, counter_bytes, _hashlib.sha1).digest()
        idx = h[-1] & 0x0F
        expected = struct.unpack(">I", h[idx:idx+4])[0] & 0x7FFFFFFF
        expected_code = str(expected % 1000000).zfill(6)
        if hmac.compare_digest(body.code, expected_code):
            with connect() as conn:
                conn.execute(
                    "UPDATE twofa_settings SET enabled = 1, pending = 0 WHERE username = ?",
                    (username,),
                )
            return {"status": "2FA enabled successfully"}
    raise HTTPException(status_code=400, detail="Invalid code")


@router.post("/disable")
def disable_2fa(body: DisableRequest, user: dict = Depends(get_current_user)):
    username = user.get("sub", "admin")
    user_2fa = _get_user_2fa(username)
    if not user_2fa or not user_2fa.get("enabled"):
        raise HTTPException(status_code=400, detail="2FA is not enabled")
    secret = user_2fa.get("secret", "")
    import hashlib as _hashlib  # noqa: F811
    for offset in (-1, 0, 1):
        key = bytes.fromhex(secret)
        counter = (int(time.time()) // 30) + offset
        counter_bytes = struct.pack(">Q", counter)
        h = hmac.new(key, counter_bytes, _hashlib.sha1).digest()
        idx = h[-1] & 0x0F
        expected = struct.unpack(">I", h[idx:idx+4])[0] & 0x7FFFFFFF
        expected_code = str(expected % 1000000).zfill(6)
        if hmac.compare_digest(body.code, expected_code):
            with connect() as conn:
                conn.execute("DELETE FROM twofa_settings WHERE username = ?", (username,))
            return {"status": "2FA disabled"}
    raise HTTPException(status_code=400, detail="Invalid code")


@router.get("/backup-codes")
def get_backup_codes(user: dict = Depends(get_current_user)):
    username = user.get("sub", "admin")
    user_2fa = _get_user_2fa(username)
    if not user_2fa or not user_2fa.get("enabled"):
        raise HTTPException(status_code=400, detail="2FA must be enabled first")
    codes = [secrets.token_hex(4).upper() for _ in range(10)]
    with connect() as conn:
        conn.execute(
            "UPDATE twofa_settings SET backup_codes = ? WHERE username = ?",
            (json.dumps(codes), username),
        )
    return {"backup_codes": codes, "message": "Save these codes. They will not be shown again."}
