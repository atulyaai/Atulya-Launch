"""Site management API."""

import os
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch.web.auth import get_current_user
from atulya_launch.web import sites_service

router = APIRouter(prefix="/api/sites", tags=["sites"])


class SiteCreate(BaseModel):
    domain: str
    web_root: Optional[str] = None
    proxy_pass: Optional[str] = None
    php: bool = False
    php_version: Optional[str] = None


@router.get("")
def list_sites(user: dict = Depends(get_current_user)):
    return {"sites": sites_service.list_sites()}


@router.post("")
def create_site(body: SiteCreate, user: dict = Depends(get_current_user)):
    try:
        data = sites_service.create_site(
            domain=body.domain,
            web_root=body.web_root,
            proxy_pass=body.proxy_pass,
            php=body.php,
            php_version=body.php_version,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"site": data}


@router.delete("/{domain}")
def delete_site(domain: str, user: dict = Depends(get_current_user)):
    ok = sites_service.delete_site(domain)
    if not ok:
        raise HTTPException(status_code=404, detail="Site not found")
    return {"status": "deleted", "domain": domain}


@router.put("/{domain}/enable")
def enable_site(domain: str, user: dict = Depends(get_current_user)):
    try:
        sites_service.toggle_site(domain, True)
    except ValueError:
        raise HTTPException(status_code=404, detail="Site not found")
    return {"status": "enabled", "domain": domain}


@router.put("/{domain}/disable")
def disable_site(domain: str, user: dict = Depends(get_current_user)):
    try:
        sites_service.toggle_site(domain, False)
    except ValueError:
        raise HTTPException(status_code=404, detail="Site not found")
    return {"status": "disabled", "domain": domain}


@router.get("/{domain}/config")
def get_site_config(domain: str, user: dict = Depends(get_current_user)):
    site = sites_service.get_site(domain)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    vhost_path = f"/etc/nginx/sites-available/{domain}.conf"
    config_content = ""
    if os.path.exists(vhost_path):
        with open(vhost_path) as f:
            config_content = f.read()
    return {"domain": domain, "config": config_content}
