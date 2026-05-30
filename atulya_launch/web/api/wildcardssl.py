"""Wildcard SSL certificate management via DNS-01 challenge."""

import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/ssl/wildcard", tags=["ssl-wildcard"])

WILDCARD_CERTS_FILE = utils.CONFIG_DIR / "wildcard_ssl.json"


def _load_certs() -> dict:
    if WILDCARD_CERTS_FILE.exists():
        with open(WILDCARD_CERTS_FILE, "r") as f:
            return json.load(f) or {}
    return {}


def _save_certs(data: dict):
    utils.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(WILDCARD_CERTS_FILE, "w") as f:
        json.dump(data, f, indent=2)


class WildcardIssueRequest(BaseModel):
    domain: str
    email: str
    use_staging: bool = False
    dns_provider: Optional[str] = None
    dns_credentials: Optional[dict] = None


@router.post("")
def issue_wildcard(body: WildcardIssueRequest, user: dict = Depends(get_current_user)):
    if not utils.is_linux():
        raise HTTPException(status_code=400, detail="Wildcard SSL issuance is only supported on Linux")

    base_domain = body.domain.lstrip("*.")
    wildcard_domain = f"*.{base_domain}"

    cert_data = {
        "domain": base_domain,
        "wildcard_domain": wildcard_domain,
        "email": body.email,
        "staging": body.use_staging,
        "dns_provider": body.dns_provider,
        "status": "pending",
        "issued_at": None,
        "expires_at": None,
        "cert_path": None,
        "key_path": None,
    }

    certbot_args = [
        "certbot", "certonly", "--manual",
        "--preferred-challenges", "dns",
        "-d", wildcard_domain,
        "-d", base_domain,
        "--non-interactive",
        "--agree-tos",
        "-m", body.email,
        "--manual-public-ip-logging-ok",
    ]
    if body.use_staging:
        certbot_args.append("--staging")

    if body.dns_provider == "cloudflare" and body.dns_credentials:
        import os
        os.environ["CERTBOT_DNS_CLOUDFLARECredentials"] = body.dns_credentials.get("api_token", "")
        certbot_args.extend([
            "--dns-cloudflare",
            "--dns-cloudflare-credentials", "/dev/stdin",
        ])

    result = utils.run_command(certbot_args, check=False, timeout=120)

    if result and result.returncode == 0:
        cert_data["status"] = "issued"
        cert_data["issued_at"] = utils._now_iso() if hasattr(utils, "_now_iso") else __import__("datetime").datetime.now().isoformat()
        cert_data["expires_at"] = (__import__("datetime").datetime.now() + __import__("datetime").timedelta(days=90)).isoformat()
        cert_data["cert_path"] = f"/etc/letsencrypt/live/{base_domain}/fullchain.pem"
        cert_data["key_path"] = f"/etc/letsencrypt/live/{base_domain}/privkey.pem"
    else:
        cert_data["status"] = "failed"
        cert_data["error"] = result.stdout if result else "Certbot execution failed"

    certs = _load_certs()
    certs[base_domain] = cert_data
    _save_certs(certs)

    if cert_data["status"] == "failed":
        raise HTTPException(status_code=500, detail=cert_data.get("error", "Certificate issuance failed"))

    return {"certificate": cert_data}


@router.get("/list")
def list_wildcard_certs(user: dict = Depends(get_current_user)):
    return {"certificates": _load_certs()}
