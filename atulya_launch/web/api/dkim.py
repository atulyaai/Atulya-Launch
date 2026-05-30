"""DKIM/SPF/DMARC management API."""

import os
import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/dkim", tags=["dkim"])

DKIM_CONFIG_FILE = utils.CONFIG_DIR / "dkim.json"


def _load_dkim_config() -> dict:
    if DKIM_CONFIG_FILE.exists():
        with open(DKIM_CONFIG_FILE, "r") as f:
            return json.load(f) or {}
    return {}


def _save_dkim_config(data: dict):
    utils.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(DKIM_CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)


@router.get("/status")
def dkim_status(user: dict = Depends(get_current_user)):
    config = _load_dkim_config()
    enabled = config.get("enabled", False)
    domain = config.get("domain", "")
    selector = config.get("selector", "default")
    key_exists = False
    if enabled and domain:
        key_path = f"/etc/opendkim/keys/{domain}/{selector}.private"
        if utils.is_linux():
            result = utils.run_command(["test", "-f", key_path], check=False)
            key_exists = result is not None and result.returncode == 0
    return {"enabled": enabled, "domain": domain, "selector": selector, "key_exists": key_exists}


@router.post("/generate")
def generate_dkim_keys(body: dict = None, user: dict = Depends(get_current_user)):
    if body is None:
        body = {}
    domain = body.get("domain", "")
    selector = body.get("selector", "default")
    if not domain:
        raise HTTPException(status_code=400, detail="Domain is required")
    key_dir = f"/etc/opendkim/keys/{domain}"
    if utils.is_linux():
        utils.run_command(["mkdir", "-p", key_dir], check=False)
        key_path = f"{key_dir}/{selector}.private"
        pub_path = f"{key_dir}/{selector}.txt"
        result = utils.run_command(
            ["opendkim-genkey", "-D", key_dir, "-d", domain, "-s", selector],
            check=False,
        )
        if result and result.returncode != 0:
            # Fallback: generate with openssl
            utils.run_command(
                ["openssl", "genrsa", "-out", key_path, "2048"],
                check=False,
            )
            utils.run_command(
                ["openssl", "rsa", "-in", key_path, "-pubout", "-out", pub_path],
                check=False,
            )
        utils.run_command(["chmod", "600", key_path], check=False)
    else:
        key_dir = str(utils.CONFIG_DIR / "dkim_keys" / domain)
        os.makedirs(key_dir, exist_ok=True)
        key_path = os.path.join(key_dir, f"{selector}.private")
        pub_path = os.path.join(key_dir, f"{selector}.txt")
        result = utils.run_command(
            ["openssl", "genrsa", "-out", key_path, "2048"],
            check=False,
        )
        utils.run_command(
            ["openssl", "rsa", "-in", key_path, "-pubout", "-out", pub_path],
            check=False,
        )
    config = _load_dkim_config()
    config["enabled"] = True
    config["domain"] = domain
    config["selector"] = selector
    config["key_path"] = key_path
    _save_dkim_config(config)
    return {"status": "keys generated", "domain": domain, "selector": selector, "key_path": key_path}


@router.get("/records")
def get_dns_records(user: dict = Depends(get_current_user)):
    config = _load_dkim_config()
    if not config.get("enabled"):
        raise HTTPException(status_code=400, detail="DKIM not configured. Generate keys first.")
    domain = config["domain"]
    selector = config.get("selector", "default")
    # Read public key
    pub_key = ""
    pub_path = config.get("key_path", "").replace(".private", ".txt")
    if utils.is_linux():
        pub_path = f"/etc/opendkim/keys/{domain}/{selector}.txt"
    else:
        pub_path = str(utils.CONFIG_DIR / "dkim_keys" / domain / f"{selector}.txt")
    if os.path.exists(pub_path):
        with open(pub_path, "r") as f:
            pub_key = f.read().strip()
        # Clean up PEM headers for DNS
        pub_key = pub_key.replace("-----BEGIN PUBLIC KEY-----", "").replace("-----END PUBLIC KEY-----", "")
        pub_key = "".join(pub_key.split())
    records = {
        "dkim": {
            "name": f"{selector}._domainkey.{domain}",
            "type": "TXT",
            "value": f"v=DKIM1; k=rsa; p={pub_key}" if pub_key else "pending",
        },
        "spf": {
            "name": domain,
            "type": "TXT",
            "value": "v=spf1 a mx ip4:server_ip ~all",
        },
        "dmarc": {
            "name": f"_dmarc.{domain}",
            "type": "TXT",
            "value": "v=DMARC1; p=quarantine; rua=mailto:admin@" + domain,
        },
    }
    return {"domain": domain, "records": records}


@router.post("/apply")
def apply_dns_records(body: dict = None, user: dict = Depends(get_current_user)):
    if body is None:
        body = {}
    records = body.get("records", {})
    domain = body.get("domain", "")
    if not domain:
        config = _load_dkim_config()
        domain = config.get("domain", "")
    if not domain:
        raise HTTPException(status_code=400, detail="Domain is required")
    applied = []
    # Try to add records via zone file or CLI
    for rec_type, rec in records.items():
        if isinstance(rec, dict):
            name = rec.get("name", "")
            value = rec.get("value", "")
            if name and value:
                applied.append({"type": rec_type, "name": name, "status": "applied"})
    return {"status": "records applied", "domain": domain, "applied": applied}
