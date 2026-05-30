"""SSL certificate management API."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import core, utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/ssl", tags=["ssl"])


class IssueRequest(BaseModel):
    domain: str
    email: str
    use_staging: bool = False


class InstallRequest(BaseModel):
    domain: str
    cert: str
    key: str
    chain: Optional[str] = None


@router.get("/certificates")
def list_certificates(user: dict = Depends(get_current_user)):
    return {"certificates": core.ssl_list()}


@router.post("/issue")
def issue_certificate(body: IssueRequest, user: dict = Depends(get_current_user)):
    result = core.ssl_issue(body.domain, body.email, use_staging=body.use_staging)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"certificate": result}


@router.post("/renew/{domain}")
def renew_certificate(domain: str, user: dict = Depends(get_current_user)):
    certs = core.ssl_list()
    if domain not in certs:
        raise HTTPException(status_code=404, detail="Certificate not found")
    result = core.ssl_renew()
    if result.get("status") == "failed":
        raise HTTPException(status_code=500, detail="Renewal failed")
    return result


@router.post("/install")
def install_certificate(body: InstallRequest, user: dict = Depends(get_current_user)):
    cert_dir = utils.CONFIG_DIR / "ssl" / body.domain
    cert_dir.mkdir(parents=True, exist_ok=True)
    (cert_dir / "fullchain.pem").write_text(body.cert)
    (cert_dir / "privkey.pem").write_text(body.key)
    if body.chain:
        (cert_dir / "chain.pem").write_text(body.chain)
    ssl_data = {
        "domain": body.domain,
        "cert_path": str(cert_dir / "fullchain.pem"),
        "key_path": str(cert_dir / "privkey.pem"),
        "installed_manually": True,
    }
    ssl_config = utils.load_config().get("ssl", {})
    ssl_config[body.domain] = ssl_data
    all_config = utils.load_config()
    all_config["ssl"] = ssl_config
    utils.save_config(all_config)
    return {"status": "installed", "domain": body.domain}


@router.delete("/{domain}")
def delete_certificate(domain: str, user: dict = Depends(get_current_user)):
    ssl_config = utils.load_config().get("ssl", {})
    if domain not in ssl_config:
        raise HTTPException(status_code=404, detail="Certificate not found")
    del ssl_config[domain]
    all_config = utils.load_config()
    all_config["ssl"] = ssl_config
    utils.save_config(all_config)
    return {"status": "deleted", "domain": domain}
