"""Backup Encryption API — GPG-based backup encryption."""

import json
import subprocess
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/backups", tags=["backup-encryption"])

ENCRYPTION_CONFIG_FILE = utils.CONFIG_DIR / "backup_encryption.json"


def _load_encryption_config() -> dict:
    if ENCRYPTION_CONFIG_FILE.exists():
        with open(ENCRYPTION_CONFIG_FILE, "r") as f:
            return json.load(f) or {}
    return {}


def _save_encryption_config(data: dict):
    utils.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(ENCRYPTION_CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _gpg_available() -> bool:
    result = utils.run_command(["gpg", "--version"], check=False)
    return result is not None and result.returncode == 0


def _list_gpg_keys() -> list:
    result = utils.run_command(
        ["gpg", "--list-keys", "--with-colons"],
        check=False,
    )
    if not result or result.returncode != 0:
        return []
    keys = []
    for line in result.stdout.splitlines():
        if line.startswith("pub:"):
            parts = line.split(":")
            if len(parts) >= 5:
                keys.append({
                    "key_id": parts[4],
                    "algo": parts[2],
                    "created": parts[4],
                })
    return keys


def _encrypt_file(input_path: str, output_path: str, recipient: Optional[str] = None, passphrase: Optional[str] = None) -> dict:
    cmd = ["gpg", "--batch", "--yes"]
    if recipient:
        cmd.extend(["--recipient", recipient, "--encrypt"])
    elif passphrase:
        cmd.extend(["--symmetric", "--passphrase", passphrase, "--cipher-algo", "AES256"])
    else:
        return {"error": "No recipient or passphrase specified"}
    cmd.extend(["--output", output_path, input_path])
    result = utils.run_command(cmd, check=False)
    if result and result.returncode == 0:
        return {"status": "encrypted", "output": output_path}
    return {"error": result.stderr if result else "GPG encryption failed"}


def _decrypt_file(input_path: str, output_path: str, passphrase: Optional[str] = None) -> dict:
    cmd = ["gpg", "--batch", "--yes", "--decrypt"]
    if passphrase:
        cmd.extend(["--passphrase", passphrase])
    cmd.extend(["--output", output_path, input_path])
    result = utils.run_command(cmd, check=False)
    if result and result.returncode == 0:
        return {"status": "decrypted", "output": output_path}
    return {"error": result.stderr if result else "GPG decryption failed"}


class EncryptionConfig(BaseModel):
    enabled: bool = False
    method: str = "gpg"
    gpg_recipient: Optional[str] = None
    passphrase: Optional[str] = None


class EncryptBackupRequest(BaseModel):
    backup_path: str
    recipient: Optional[str] = None
    passphrase: Optional[str] = None


class DecryptBackupRequest(BaseModel):
    backup_path: str
    passphrase: Optional[str] = None


@router.get("/encryption")
def get_encryption_status(user: dict = Depends(get_current_user)):
    config = _load_encryption_config()
    gpg_installed = _gpg_available()
    keys = _list_gpg_keys() if gpg_installed else []
    return {
        "enabled": config.get("enabled", False),
        "method": config.get("method", "gpg"),
        "gpg_recipient": config.get("gpg_recipient"),
        "gpg_installed": gpg_installed,
        "available_keys": keys,
    }


@router.put("/encryption")
def set_encryption_config(body: EncryptionConfig, user: dict = Depends(get_current_user)):
    if not _gpg_available():
        raise HTTPException(status_code=400, detail="GPG is not installed on this system")

    if body.method not in ("gpg", "password"):
        raise HTTPException(status_code=400, detail="Method must be 'gpg' or 'password'")

    if body.enabled:
        if body.method == "gpg" and not body.gpg_recipient:
            raise HTTPException(status_code=400, detail="GPG recipient key ID required")
        if body.method == "password" and not body.passphrase:
            raise HTTPException(status_code=400, detail="Passphrase required for password-based encryption")

    config = {
        "enabled": body.enabled,
        "method": body.method,
        "gpg_recipient": body.gpg_recipient,
        "passphrase": body.passphrase if body.method == "password" else None,
        "updated_at": datetime.now().isoformat(),
    }
    _save_encryption_config(config)
    return {"status": "updated", "encryption": config}


@router.post("/encrypt")
def encrypt_backup(body: EncryptBackupRequest, user: dict = Depends(get_current_user)):
    if not _gpg_available():
        raise HTTPException(status_code=400, detail="GPG is not installed")

    config = _load_encryption_config()
    if not config.get("enabled"):
        raise HTTPException(status_code=400, detail="Backup encryption is not enabled")

    from pathlib import Path
    if not Path(body.backup_path).exists():
        raise HTTPException(status_code=404, detail="Backup file not found")

    output_path = body.backup_path + ".gpg"
    recipient = body.recipient or config.get("gpg_recipient")
    passphrase = body.passphrase or config.get("passphrase")

    result = _encrypt_file(body.backup_path, output_path, recipient=recipient, passphrase=passphrase)
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@router.post("/decrypt")
def decrypt_backup(body: DecryptBackupRequest, user: dict = Depends(get_current_user)):
    if not _gpg_available():
        raise HTTPException(status_code=400, detail="GPG is not installed")

    from pathlib import Path
    if not Path(body.backup_path).exists():
        raise HTTPException(status_code=404, detail="Encrypted backup file not found")

    output_path = body.backup_path.replace(".gpg", "")
    passphrase = body.passphrase

    result = _decrypt_file(body.backup_path, output_path, passphrase=passphrase)
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@router.get("/encryption/keys")
def list_gpg_keys(user: dict = Depends(get_current_user)):
    if not _gpg_available():
        raise HTTPException(status_code=400, detail="GPG is not installed")
    return {"keys": _list_gpg_keys()}


@router.post("/encryption/generate-key")
def generate_gpg_key(user: dict = Depends(get_current_user)):
    if not _gpg_available():
        raise HTTPException(status_code=400, detail="GPG is not installed")

    config = _load_encryption_config()
    result = utils.run_command(
        [
            "gpg", "--batch", "--gen-key",
            f"Key-Type: RSA\nKey-Length: 4096\nName-Real: Atulya-Launch Backup\nName-Email: backup@atulya.local\nExpire-Date: 0\n%no-protection\n%commit",
        ],
        check=False,
    )
    if result and result.returncode == 0:
        keys = _list_gpg_keys()
        return {"status": "key_generated", "keys": keys}
    return {"status": "generation_failed", "error": result.stderr if result else "Unknown error"}
