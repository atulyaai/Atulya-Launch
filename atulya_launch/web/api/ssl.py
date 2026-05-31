"""SSL certificate management API."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import core, utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/ssl", tags=["ssl"])


class IssueRequest(BaseModel):
    domain: str


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
    result = core.ssl_issue_letsencrypt(body.domain)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"certificate": result}


@router.post("/renew/{domain}")
def renew_certificate(domain: str, user: dict = Depends(get_current_user)):
    certs = core.ssl_list()
    if domain not in certs:
        raise HTTPException(status_code=404, detail="Certificate not found")
    result = core.ssl_renew(domain)
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
    from atulya_launch.web.database import connect
    conn = connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO ssl_certs (domain, cert_path, key_path, issuer, expires_at, auto_renew) VALUES (?, ?, ?, ?, ?, ?)",
            (body.domain, str(cert_dir / "fullchain.pem"), str(cert_dir / "privkey.pem"), "manual", None, 0),
        )
        conn.commit()
    finally:
        conn.close()
    
    # Apply SSL config via driver layer (for web servers that need certificate paths)
    try:
        from atulya_launch.drivers import get_platform_driver
        driver = get_platform_driver(dry_run=False)
        # For nginx, we might need to update the site config to point to these certs
        # This would be site-specific, so we'll just note that certs are installed
        # The actual SSL configuration in nginx/apache would be handled elsewhere
        pass
    except Exception:
        pass
    
    return {"status": "installed", "domain": body.domain}


@router.delete("/{domain}")
def delete_certificate(domain: str, user: dict = Depends(get_current_user)):
    from atulya_launch.web.database import connect
    conn = connect()
    try:
        row = conn.execute("SELECT domain FROM ssl_certs WHERE domain = ?", (domain,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Certificate not found")
        conn.execute("DELETE FROM ssl_certs WHERE domain = ?", (domain,))
        conn.commit()
    finally:
        conn.close()
    return {"status": "deleted", "domain": domain}
