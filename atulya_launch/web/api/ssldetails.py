"""SSL certificate details and revocation API."""

import datetime
import subprocess
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/ssl/cert", tags=["ssl-details"])


class RevokeRequest(BaseModel):
    reason: Optional[str] = "unspecified"


def _get_cert_details_from_file(cert_path: str) -> dict:
    result = utils.run_command(
        ["openssl", "x509", "-in", cert_path, "-text", "-noout"],
        check=False,
    )
    if not result or result.returncode != 0:
        return {}
    output = result.stdout
    details = {
        "subject": _extract_field(output, "Subject:"),
        "issuer": _extract_field(output, "Issuer:"),
        "serial": _extract_field(output, "Serial Number:"),
        "not_before": _extract_field(output, "Not Before:"),
        "not_after": _extract_field(output, "Not After :"),
        "san": _extract_san(output),
        "signature_algorithm": _extract_field(output, "Signature Algorithm:"),
        "public_key": _extract_public_key(output),
        "fingerprint_sha256": _get_fingerprint(cert_path, "sha256"),
        "fingerprint_sha1": _get_fingerprint(cert_path, "sha1"),
    }
    try:
        exp = datetime.datetime.strptime(details["not_after"], "%b %d %H:%M:%S %Y %Z")
        days_left = (exp - datetime.datetime.now()).days
        details["days_until_expiry"] = days_left
        details["expired"] = days_left < 0
    except (ValueError, TypeError, KeyError):
        details["days_until_expiry"] = None
        details["expired"] = None
    return details


def _extract_field(text: str, field: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith(field):
            return line[len(field):].strip()
    return ""


def _extract_san(text: str) -> list:
    san_lines = []
    in_san = False
    for line in text.splitlines():
        if "Subject Alternative Name:" in line:
            in_san = True
            continue
        if in_san:
            if line.startswith("DNS:"):
                san_lines.append(line.split("DNS:")[1].strip())
            elif not line.startswith(" ") and not line.startswith("\t"):
                in_san = False
    return san_lines


def _extract_public_key(text: str) -> str:
    for line in text.splitlines():
        if "Public Key Algorithm:" in line:
            return line.split("Public Key Algorithm:")[1].strip()
    return ""


def _get_fingerprint(cert_path: str, algo: str = "sha256") -> str:
    result = utils.run_command(
        ["openssl", "x509", "-in", cert_path, "-fingerprint", "-noout", "-", algo],
        check=False,
    )
    if result and result.returncode == 0:
        fp = result.stdout.strip()
        if "=" in fp:
            return fp.split("=", 1)[1]
    return ""


def _get_cert_chain(cert_path: str) -> list:
    result = utils.run_command(
        ["openssl", "crl2pkcs7", "-nocrl", "-certfile", cert_path],
        check=False,
    )
    if not result or result.returncode != 0:
        return []
    chain_result = utils.run_command(
        ["openssl", "pkcs7", "-print_certs", "-text", "-in", "/dev/stdin"],
        check=False,
    )
    return []


def _get_cert_from_live(domain: str) -> dict:
    result = utils.run_command(
        ["openssl", "s_client", "-connect", f"{domain}:443", "-servername", domain],
        check=False,
        timeout=10,
    )
    if not result or result.returncode != 0:
        return {}
    pem_lines = []
    capture = False
    for line in (result.stdout or "").splitlines():
        if "-----BEGIN CERTIFICATE-----" in line:
            capture = True
        if capture:
            pem_lines.append(line)
        if "-----END CERTIFICATE-----" in line:
            capture = False
            break
    if not pem_lines:
        return {}
    pem_text = "\n".join(pem_lines)
    cert_file = utils.CONFIG_DIR / "temp_cert.pem"
    cert_file.write_text(pem_text)
    details = _get_cert_details_from_file(str(cert_file))
    cert_file.unlink(missing_ok=True)
    return details


@router.get("/{domain}/details")
def get_cert_details(domain: str, user: dict = Depends(get_current_user)):
    ssl_config = utils.load_config().get("ssl", {})
    cert_info = ssl_config.get(domain, {})
    cert_path = cert_info.get("cert_path", f"/etc/letsencrypt/live/{domain}/fullchain.pem")
    if not Path(cert_path).exists():
        details = _get_cert_from_live(domain)
        if not details:
            raise HTTPException(status_code=404, detail=f"No certificate found for {domain}")
        return {
            "domain": domain,
            "source": "live",
            "details": details,
        }
    details = _get_cert_details_from_file(cert_path)
    key_path = cert_info.get("key_path", "")
    key_exists = Path(key_path).exists() if key_path else False
    return {
        "domain": domain,
        "source": "local",
        "cert_path": cert_path,
        "key_path": key_path,
        "key_exists": key_exists,
        "details": details,
    }


@router.post("/{domain}/revoke")
def revoke_certificate(domain: str, body: RevokeRequest, user: dict = Depends(get_current_user)):
    if not utils.is_linux():
        raise HTTPException(status_code=400, detail="Certificate revocation is only supported on Linux")
    ssl_config = utils.load_config().get("ssl", {})
    if domain not in ssl_config:
        raise HTTPException(status_code=404, detail="Certificate not found")
    cert_info = ssl_config[domain]
    cert_path = cert_info.get("cert_path", f"/etc/letsencrypt/live/{domain}/fullchain.pem")
    if not Path(cert_path).exists():
        raise HTTPException(status_code=404, detail="Certificate file not found on disk")
    result = utils.run_command(
        ["certbot", "revoke", "--cert-path", cert_path, "--reason", body.reason, "--non-interactive"],
        check=False,
        timeout=60,
    )
    if not result or result.returncode != 0:
        detail = result.stderr if result else "Revocation failed"
        raise HTTPException(status_code=500, detail=detail)
    cert_info["revoked"] = True
    cert_info["revoked_at"] = datetime.datetime.now().isoformat()
    cert_info["revoke_reason"] = body.reason
    ssl_config[domain] = cert_info
    all_config = utils.load_config()
    all_config["ssl"] = ssl_config
    utils.save_config(all_config)
    return {"status": "revoked", "domain": domain, "reason": body.reason}


@router.get("/{domain}/verify")
def verify_cert_live(domain: str, user: dict = Depends(get_current_user)):
    result = utils.run_command(
        ["openssl", "s_client", "-connect", f"{domain}:443", "-servername", domain],
        check=False,
        timeout=10,
    )
    if not result:
        return {"domain": domain, "valid": False, "error": "Could not connect"}
    output = result.stdout + (result.stderr or "")
    verified = "Verify return code: 0" in output
    return {
        "domain": domain,
        "valid": verified,
        "error_code": _extract_field(output, "Verify return code:"),
    }


from pathlib import Path
