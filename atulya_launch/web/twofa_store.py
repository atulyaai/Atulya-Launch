"""Unified TOTP/2FA store backed by SQLite.

Single source of truth for two-factor authentication secrets, enabled state,
and backup codes. Replaces the previously divergent config.json, twofa.json,
and per-module SQLite reads so the login challenge, the settings page, and the
API all agree.
"""

import hashlib
import hmac
import json
import secrets
import struct
import time
from datetime import datetime, timezone
from typing import Any

from .database import connect


def _now() -> str:
    return datetime.now(timezone.utc).isoformat() + "Z"


def _backup_codes_from_row(row: Any) -> list[str]:
    try:
        return json.loads(row.get("backup_codes") or "[]")
    except Exception:
        return []


def get_user_2fa(username: str) -> dict | None:
    """Return 2FA record for a user or None if not configured."""
    with connect() as conn:
        row = conn.execute(
            "SELECT secret, enabled, pending, backup_codes FROM twofa_settings WHERE username = ?",
            (username,),
        ).fetchone()
    if not row:
        return None
    entry = dict(row)
    entry["backup_codes"] = _backup_codes_from_row(row)
    entry["enabled"] = bool(entry.get("enabled"))
    entry["pending"] = bool(entry.get("pending"))
    return entry


def is_enabled(username: str) -> bool:
    """Return whether 2FA is fully enabled for a user."""
    record = get_user_2fa(username)
    return bool(record and record.get("enabled"))


def verify_totp(secret: str, code: str) -> bool:
    """Verify a TOTP code against a secret (RFC 6238, SHA1, 30s window)."""
    try:
        key = bytes.fromhex(secret)
    except Exception:
        return False
    for offset in (-1, 0, 1):
        try:
            counter = (int(time.time()) // 30) + offset
            counter_bytes = struct.pack(">Q", counter)
            h = hmac.new(key, counter_bytes, hashlib.sha1).digest()
            idx = h[-1] & 0x0F
            expected = struct.unpack(">I", h[idx : idx + 4])[0] & 0x7FFFFFFF
            expected_code = str(expected % 1000000).zfill(6)
            if hmac.compare_digest(code, expected_code):
                return True
        except Exception:
            continue
    return False


def verify(username: str, code: str) -> bool:
    """Verify a code for a user, consuming backup codes on match.

    Returns True when 2FA is not enabled (no challenge required), matching the
    previous no-op behavior for users without 2FA.
    """
    record = get_user_2fa(username)
    if not record or not record.get("enabled"):
        return True
    secret = record.get("secret", "")
    if secret and verify_totp(secret, code):
        return True
    codes = record["backup_codes"]
    if code in codes:
        codes.remove(code)
        with connect() as conn:
            conn.execute(
                "UPDATE twofa_settings SET backup_codes = ? WHERE username = ?",
                (json.dumps(codes), username),
            )
        return True
    return False


def generate_secret() -> str:
    """Generate a new random TOTP secret (hex-encoded)."""
    return secrets.token_hex(20)


def provisioning_uri(username: str, secret: str, issuer: str = "AtulyaLaunch") -> str:
    """Build an otpauth:// URI for the QR code / authenticator app."""
    return f"otpauth://totp/{issuer}:{username}?secret={secret}&issuer={issuer}&digits=6&period=30"


def start_setup(username: str) -> dict:
    """Begin 2FA setup: store a pending secret and return provisioning info."""
    secret = generate_secret()
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO twofa_settings (username, secret, enabled, pending, backup_codes, created_at) "
            "VALUES (?, ?, 0, 1, '[]', ?)",
            (username, secret, _now()),
        )
    return {
        "secret": secret,
        "uri": provisioning_uri(username, secret),
        "qr_code": f"data:text/plain,{provisioning_uri(username, secret)}",
        "message": "Scan the QR code with your authenticator app, then verify with a code.",
    }


def enable(username: str, code: str) -> dict:
    """Enable 2FA for a user after a valid code is provided."""
    record = get_user_2fa(username)
    if not record:
        return {"ok": False, "error": "no pending 2FA setup"}
    if record.get("enabled"):
        return {"ok": False, "error": "2FA is already enabled"}
    if not verify_totp(record.get("secret", ""), code):
        return {"ok": False, "error": "invalid code"}
    codes = [secrets.token_hex(4).upper() for _ in range(10)]
    with connect() as conn:
        conn.execute(
            "UPDATE twofa_settings SET enabled = 1, pending = 0, backup_codes = ? WHERE username = ?",
            (json.dumps(codes), username),
        )
    return {"ok": True, "status": "2FA enabled successfully", "backup_codes": codes}


def disable(username: str, code: str) -> dict:
    """Disable 2FA for a user after a valid TOTP or backup code."""
    record = get_user_2fa(username)
    if not record:
        return {"ok": False, "error": "2FA not configured"}
    if not record.get("enabled"):
        return {"ok": False, "error": "2FA is not enabled"}
    if record.get("secret") and verify_totp(record["secret"], code):
        pass
    elif code not in record["backup_codes"]:
        return {"ok": False, "error": "invalid code"}
    with connect() as conn:
        conn.execute("DELETE FROM twofa_settings WHERE username = ?", (username,))
    return {"ok": True, "status": "2FA disabled"}


def regenerate_backup_codes(username: str) -> dict:
    """Replace and return a fresh set of backup codes (requires 2FA enabled)."""
    record = get_user_2fa(username)
    if not record or not record.get("enabled"):
        return {"ok": False, "error": "2FA must be enabled first"}
    codes = [secrets.token_hex(4).upper() for _ in range(10)]
    with connect() as conn:
        conn.execute(
            "UPDATE twofa_settings SET backup_codes = ? WHERE username = ?",
            (json.dumps(codes), username),
        )
    return {"ok": True, "backup_codes": codes}


def status(username: str) -> dict:
    """Return the enabled state for a user."""
    return {"enabled": is_enabled(username)}