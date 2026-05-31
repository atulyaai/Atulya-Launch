"""SSH key management API."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user
from atulya_launch.web.database import connect

router = APIRouter(prefix="/api/ssh", tags=["ssh"])


def _fingerprint_from_key(pubkey: str) -> str:
    import hashlib, base64
    parts = pubkey.strip().split()
    if len(parts) < 2:
        return ""
    key_data = base64.b64decode(parts[1])
    fp = hashlib.md5(key_data).hexdigest()
    return ":".join(fp[i:i+2] for i in range(0, len(fp), 2))


def _validate_pubkey(pubkey: str) -> bool:
    parts = pubkey.strip().split()
    if len(parts) < 2:
        return False
    valid_prefixes = ("ssh-rsa", "ssh-ed25519", "ssh-dss", "ecdsa-sha2-")
    return parts[0] in valid_prefixes


class SSHKeyCreate(BaseModel):
    public_key: str
    name: Optional[str] = None


@router.get("/keys")
def list_keys(user: dict = Depends(get_current_user)):
    username = user.get("sub", "admin")
    with connect() as conn:
        rows = conn.execute(
            "SELECT fingerprint, public_key, name, user FROM ssh_keys WHERE user = ?",
            (username,),
        ).fetchall()
    keys = {r["fingerprint"]: dict(r) for r in rows}
    return {"keys": keys}


@router.post("/keys")
def add_key(body: SSHKeyCreate, user: dict = Depends(get_current_user)):
    if not _validate_pubkey(body.public_key):
        raise HTTPException(status_code=400, detail="Invalid public key format")
    fp = _fingerprint_from_key(body.public_key)
    if not fp:
        raise HTTPException(status_code=400, detail="Could not compute fingerprint")
    username = user.get("sub", "admin")
    key_name = body.name or fp.replace(":", "")[:16]
    from datetime import datetime
    with connect() as conn:
        existing = conn.execute("SELECT fingerprint FROM ssh_keys WHERE fingerprint = ?", (fp,)).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="Key already exists")
        conn.execute(
            "INSERT INTO ssh_keys (fingerprint, public_key, name, user, created_at) VALUES (?, ?, ?, ?, ?)",
            (fp, body.public_key.strip(), key_name, username, datetime.now().isoformat()),
        )
    if utils.is_linux():
        import os
        ssh_dir = os.path.expanduser("~/.ssh")
        os.makedirs(ssh_dir, exist_ok=True)
        auth_file = os.path.join(ssh_dir, "authorized_keys")
        existing = ""
        if os.path.exists(auth_file):
            with open(auth_file, "r") as f:
                existing = f.read()
        if body.public_key.strip() not in existing:
            with open(auth_file, "a") as f:
                f.write(body.public_key.strip() + "\n")
    return {"status": "added", "fingerprint": fp}


@router.delete("/keys/{fingerprint}")
def delete_key(fingerprint: str, user: dict = Depends(get_current_user)):
    with connect() as conn:
        row = conn.execute("SELECT fingerprint FROM ssh_keys WHERE fingerprint = ?", (fingerprint,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Key not found")
        conn.execute("DELETE FROM ssh_keys WHERE fingerprint = ?", (fingerprint,))
    return {"status": "deleted", "fingerprint": fingerprint}


@router.get("/keys/{fingerprint}/verify")
def verify_key(fingerprint: str, user: dict = Depends(get_current_user)):
    with connect() as conn:
        row = conn.execute(
            "SELECT fingerprint, public_key, name FROM ssh_keys WHERE fingerprint = ?",
            (fingerprint,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Key not found")
    valid = _validate_pubkey(row["public_key"])
    return {"fingerprint": fingerprint, "valid": valid, "name": row["name"] or ""}
