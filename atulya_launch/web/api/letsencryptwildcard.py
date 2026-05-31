"""Let's Encrypt Wildcard SSL via DNS-01 Challenge API."""

import json
import subprocess
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/ssl/wildcard", tags=["ssl-wildcard"])

WILDCARD_CONFIG_FILE = utils.CONFIG_DIR / "wildcard_ssl.json"
CERTBOT_DIR = utils.CONFIG_DIR / "certs" / "wildcard"


def _load_wildcard_config() -> dict:
    if WILDCARD_CONFIG_FILE.exists():
        with open(WILDCARD_CONFIG_FILE, "r") as f:
            return json.load(f) or {}
    return {}


def _save_wildcard_config(data: dict):
    utils.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(WILDCARD_CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _certbot_available() -> bool:
    return shutil.which("certbot") is not None


def _install_certbot():
    utils.run_command(["apt-get", "update", "-qq"], check=False)
    utils.run_command(["apt-get", "install", "-y", "-qq", "certbot"], check=False)
    utils.run_command(
        ["pip3", "install", "certbot-dns-cloudflare", "certbot-dns-route53", "certbot-dns-google"],
        check=False,
    )


def _issue_wildcard_cert(
    domain: str,
    dns_provider: str,
    provider_config: dict,
    email: str,
    use_staging: bool = False,
) -> dict:
    base_domain = domain.lstrip("*.") if domain.startswith("*.") else domain
    cert_name = base_domain.replace(".", "-")

    if dns_provider == "cloudflare":
        cloudflare_conf = provider_config.get("cloudflare_ini_path", "/tmp/cloudflare.ini")
        Cloudflare_ini = provider_config.get("cloudflare_ini")
        if Cloudflare_ini:
            Path("/tmp").mkdir(parents=True, exist_ok=True)
            Path(cloudflare_conf).write_text(Cloudflare_ini)
            utils.run_command(["chmod", "600", cloudflare_conf], check=False)

        cmd = [
            "certbot", "certonly",
            "--dns-cloudflare",
            "--dns-cloudflare-credentials", cloudflare_conf,
            "--dns-cloudflare-propagation-seconds", "30",
            "-d", f"*.{base_domain}",
            "-d", base_domain,
            "--email", email,
            "--agree-tos",
            "--non-interactive",
        ]
    elif dns_provider == "route53":
        cmd = [
            "certbot", "certonly",
            "--dns-route53",
            "-d", f"*.{base_domain}",
            "-d", base_domain,
            "--email", email,
            "--agree-tos",
            "--non-interactive",
        ]
    elif dns_provider == "google":
        credentials_file = provider_config.get("credentials_file", "")
        cmd = [
            "certbot", "certonly",
            "--dns-google",
            "--dns-google-credentials", credentials_file,
            "-d", f"*.{base_domain}",
            "-d", base_domain,
            "--email", email,
            "--agree-tos",
            "--non-interactive",
        ]
    elif dns_provider == "manual":
        cmd = [
            "certbot", "certonly",
            "--manual",
            "--preferred-challenges", "dns",
            "-d", f"*.{base_domain}",
            "-d", base_domain,
            "--email", email,
            "--agree-tos",
            "--non-interactive",
        ]
    else:
        return {"error": f"Unsupported DNS provider: {dns_provider}"}

    if use_staging:
        cmd.append("--staging")

    cmd.extend(["--cert-name", cert_name])

    result = utils.run_command(cmd, check=False, timeout=300)
    if not result or result.returncode != 0:
        error = result.stderr if result and hasattr(result, "stderr") else "Certbot failed"
        return {"error": error}

    cert_path = Path(f"/etc/letsencrypt/live/{cert_name}")
    fullchain = cert_path / "fullchain.pem"
    privkey = cert_path / "privkey.pem"

    return {
        "status": "issued",
        "domain": base_domain,
        "wildcard": f"*.{base_domain}",
        "cert_path": str(fullchain),
        "key_path": str(privkey),
        "cert_name": cert_name,
        "dns_provider": dns_provider,
        "staging": use_staging,
        "issued_at": datetime.now().isoformat(),
    }


class WildcardIssue(BaseModel):
    domain: str
    email: str
    dns_provider: str
    cloudflare_ini: Optional[str] = None
    cloudflare_ini_path: Optional[str] = None
    route53_profile: Optional[str] = None
    google_credentials_file: Optional[str] = None
    use_staging: bool = False


class WildcardRenew(BaseModel):
    domain: str


@router.post("/issue")
def issue_wildcard_cert(body: WildcardIssue, user: dict = Depends(get_current_user)):
    if not _certbot_available():
        _install_certbot()
        if not _certbot_available():
            raise HTTPException(status_code=500, detail="Failed to install certbot")

    if body.dns_provider not in ("cloudflare", "route53", "google", "manual"):
        raise HTTPException(status_code=400, detail="dns_provider must be cloudflare, route53, google, or manual")

    provider_config = {}
    if body.dns_provider == "cloudflare":
        if body.cloudflare_ini:
            provider_config["cloudflare_ini"] = body.cloudflare_ini
        if body.cloudflare_ini_path:
            provider_config["cloudflare_ini_path"] = body.cloudflare_ini_path
    elif body.dns_provider == "google":
        if not body.google_credentials_file:
            raise HTTPException(status_code=400, detail="google_credentials_file required for Google DNS")
        provider_config["credentials_file"] = body.google_credentials_file

    base_domain = body.domain.lstrip("*.") if body.domain.startswith("*.") else body.domain
    result = _issue_wildcard_cert(
        domain=body.domain,
        dns_provider=body.dns_provider,
        provider_config=provider_config,
        email=body.email,
        use_staging=body.use_staging,
    )

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    config = _load_wildcard_config()
    config[base_domain] = result
    _save_wildcard_config(config)

    return result


@router.post("/renew")
def renew_wildcard_cert(body: WildcardRenew, user: dict = Depends(get_current_user)):
    base_domain = body.domain.lstrip("*.") if body.domain.startswith("*.") else body.domain
    config = _load_wildcard_config()
    cert_info = config.get(base_domain)
    if not cert_info:
        raise HTTPException(status_code=404, detail="No wildcard cert found for this domain")

    cert_name = cert_info.get("cert_name", base_domain.replace(".", "-"))
    result = utils.run_command(
        ["certbot", "renew", "--cert-name", cert_name, "--non-interactive"],
        check=False,
        timeout=300,
    )
    if not result or result.returncode != 0:
        error = result.stderr if result and hasattr(result, "stderr") else "Renewal failed"
        raise HTTPException(status_code=500, detail=error)

    cert_info["renewed_at"] = datetime.now().isoformat()
    config[base_domain] = cert_info
    _save_wildcard_config(config)

    return {"status": "renewed", "domain": base_domain, "cert_name": cert_name}


@router.get("/certs")
def list_wildcard_certs(user: dict = Depends(get_current_user)):
    config = _load_wildcard_config()
    return {"certificates": config}


@router.get("/certs/{domain}")
def get_wildcard_cert(domain: str, user: dict = Depends(get_current_user)):
    config = _load_wildcard_config()
    cert = config.get(domain)
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found")
    return {"certificate": cert}


@router.post("/install/{domain}")
def install_wildcard_cert(domain: str, user: dict = Depends(get_current_user)):
    config = _load_wildcard_config()
    cert_info = config.get(domain)
    if not cert_info:
        raise HTTPException(status_code=404, detail="Certificate not found")

    cert_path = cert_info.get("cert_path")
    key_path = cert_info.get("key_path")

    ssl_dir = utils.CONFIG_DIR / "ssl" / domain
    ssl_dir.mkdir(parents=True, exist_ok=True)

    import shutil
    if cert_path and Path(cert_path).exists():
        shutil.copy2(cert_path, ssl_dir / "fullchain.pem")
    if key_path and Path(key_path).exists():
        shutil.copy2(key_path, ssl_dir / "privkey.pem")

    all_config = utils.load_config()
    all_config.setdefault("ssl", {})[domain] = {
        "domain": domain,
        "cert_path": str(ssl_dir / "fullchain.pem"),
        "key_path": str(ssl_dir / "privkey.pem"),
        "wildcard": True,
        "installed_at": datetime.now().isoformat(),
    }
    utils.save_config(all_config)

    return {"status": "installed", "domain": domain, "path": str(ssl_dir)}
