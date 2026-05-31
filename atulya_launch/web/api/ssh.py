"""SSH key management API."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/ssh", tags=["ssh"])

SSH_KEYS_FILE = utils.CONFIG_DIR / "ssh_keys.json"


def _load_keys() -> dict:
    if SSH_KEYS_FILE.exists():
        import json
        with open(SSH_KEYS_FILE, "r") as f:
            return json.load(f) or {}
    return {}


def _save_keys(data: dict):
    utils.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    import json
    with open(SSH_KEYS_FILE, "w") as f:
        json.dump(data, f, indent=2)


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
    keys = _load_keys()
    username = user.get("sub", "admin")
    user_keys = {k: v for k, v in keys.items() if v.get("user") == username}
    return {"keys": user_keys}


@router.post("/keys")
def add_key(body: SSHKeyCreate, user: dict = Depends(get_current_user)):
    if not _validate_pubkey(body.public_key):
        raise HTTPException(status_code=400, detail="Invalid public key format")
    fp = _fingerprint_from_key(body.public_key)
    if not fp:
        raise HTTPException(status_code=400, detail="Could not compute fingerprint")
    keys = _load_keys()
    username = user.get("sub", "admin")
    key_name = body.name or fp.replace(":", "")[:16]
    keys[fp] = {
        "fingerprint": fp,
        "public_key": body.public_key.strip(),
        "name": key_name,
        "user": username,
    }
    _save_keys(keys)
    # Also add to authorized_keys on Linux
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
    keys = _load_keys()
    if fingerprint not in keys:
        raise HTTPException(status_code=404, detail="Key not found")
    del keys[fingerprint]
    _save_keys(keys)
    return {"status": "deleted", "fingerprint": fingerprint}


@router.get("/keys/{fingerprint}/verify")
def verify_key(fingerprint: str, user: dict = Depends(get_current_user)):
    keys = _load_keys()
    if fingerprint not in keys:
        raise HTTPException(status_code=404, detail="Key not found")
    key_data = keys[fingerprint]
    pubkey = key_data.get("public_key", "")
    valid = _validate_pubkey(pubkey)
    return {"fingerprint": fingerprint, "valid": valid, "name": key_data.get("name", "")}
