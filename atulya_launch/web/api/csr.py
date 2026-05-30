"""CSR (Certificate Signing Request) generator API."""

import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/ssl/csr", tags=["csr"])

CSR_FILE = utils.CONFIG_DIR / "csrs.json"


def _load_csrs() -> dict:
    if CSR_FILE.exists():
        with open(CSR_FILE, "r") as f:
            return json.load(f) or {}
    return {}


def _save_csrs(data: dict):
    utils.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CSR_FILE, "w") as f:
        json.dump(data, f, indent=2)


class CSRGenerateRequest(BaseModel):
    common_name: str
    organization: Optional[str] = None
    organizational_unit: Optional[str] = None
    country: Optional[str] = None
    state: Optional[str] = None
    locality: Optional[str] = None
    email: Optional[str] = None
    key_size: int = 2048
    san_domains: Optional[list] = None


@router.post("")
def generate_csr(body: CSRGenerateRequest, user: dict = Depends(get_current_user)):
    if not utils.is_linux():
        raise HTTPException(status_code=400, detail="CSR generation is only supported on Linux")

    import subprocess
    import tempfile

    key_path = None
    csr_path = None
    key_content = None
    csr_content = None

    try:
        key_file = tempfile.NamedTemporaryFile(delete=False, suffix=".key")
        key_path = key_file.name
        key_file.close()

        csr_file = tempfile.NamedTemporaryFile(delete=False, suffix=".csr")
        csr_path = csr_file.name
        csr_file.close()

        subject_parts = [f"/CN={body.common_name}"]
        if body.organization:
            subject_parts.append(f"/O={body.organization}")
        if body.organizational_unit:
            subject_parts.append(f"/OU={body.organizational_unit}")
        if body.country:
            subject_parts.append(f"/C={body.country}")
        if body.state:
            subject_parts.append(f"/S={body.state}")
        if body.locality:
            subject_parts.append(f"/L={body.locality}")
        if body.email:
            subject_parts.append(f"/emailAddress={body.email}")
        subject = "".join(subject_parts)

        openssl_cmd = [
            "openssl", "req", "-new", "-newkey", f"rsa:{body.key_size}",
            "-nodes", "-keyout", key_path, "-out", csr_path,
            "-subj", subject,
        ]

        san_ext = ""
        if body.san_domains:
            san_entries = [f"DNS:{body.common_name}"]
            for d in body.san_domains:
                san_entries.append(f"DNS:{d}")
            san_ext = ",".join(san_entries)

        if san_ext:
            ext_file = tempfile.NamedTemporaryFile(delete=False, mode="w", suffix=".cnf", prefix="openssl_")
            ext_file.write(f"[req]\ndistinguished_name = req_dn\nreq_extensions = v3_req\n\n[req_dn]\n\n[v3_req]\nsubjectAltName = {san_ext}\n")
            ext_file.close()
            openssl_cmd.extend(["-config", ext_file.name])

        result = utils.run_command(openssl_cmd, check=False)

        if result and result.returncode != 0:
            raise HTTPException(status_code=500, detail=f"OpenSSL error: {result.stderr}")

        with open(key_path, "r") as f:
            key_content = f.read()
        with open(csr_path, "r") as f:
            csr_content = f.read()

        import hashlib
        csr_id = hashlib.sha256(csr_content.encode()).hexdigest()[:16]

        csr_record = {
            "id": csr_id,
            "common_name": body.common_name,
            "organization": body.organization,
            "country": body.country,
            "state": body.state,
            "locality": body.locality,
            "email": body.email,
            "key_size": body.key_size,
            "san_domains": body.san_domains or [],
            "csr": csr_content,
            "private_key": key_content,
            "created_at": __import__("datetime").datetime.now().isoformat(),
        }

        csrs = _load_csrs()
        csrs[csr_id] = csr_record
        _save_csrs(csrs)

        return {"csr": csr_record}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        import os
        if key_path and os.path.exists(key_path):
            os.unlink(key_path)
        if csr_path and os.path.exists(csr_path):
            os.unlink(csr_path)


@router.get("/list")
def list_csrs(user: dict = Depends(get_current_user)):
    csrs = _load_csrs()
    return {"csrs": csrs}
