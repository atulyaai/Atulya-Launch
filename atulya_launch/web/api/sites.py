"""Site management API."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import core, utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/sites", tags=["sites"])


class SiteCreate(BaseModel):
    domain: str
    web_root: Optional[str] = None
    server_type: Optional[str] = None
    php_enabled: bool = False
    extra_config: Optional[dict] = None


@router.get("")
def list_sites(user: dict = Depends(get_current_user)):
    return {"sites": core.site_list()}


@router.post("")
def create_site(body: SiteCreate, user: dict = Depends(get_current_user)):
    data = core.site_create(
        domain_name=body.domain,
        web_root=body.web_root,
        server_type=body.server_type,
        php_enabled=body.php_enabled,
        extra_config=body.extra_config,
    )
    return {"site": data}


@router.delete("/{domain}")
def delete_site(domain: str, user: dict = Depends(get_current_user)):
    ok = core.site_delete(domain)
    if not ok:
        raise HTTPException(status_code=404, detail="Site not found")
    return {"status": "deleted", "domain": domain}


@router.put("/{domain}/enable")
def enable_site(domain: str, user: dict = Depends(get_current_user)):
    ok = core.site_toggle(domain, enable=True)
    if not ok:
        raise HTTPException(status_code=404, detail="Site not found")
    return {"status": "enabled", "domain": domain}


@router.put("/{domain}/disable")
def disable_site(domain: str, user: dict = Depends(get_current_user)):
    ok = core.site_toggle(domain, enable=False)
    if not ok:
        raise HTTPException(status_code=404, detail="Site not found")
    return {"status": "disabled", "domain": domain}


@router.get("/{domain}/config")
def get_site_config(domain: str, user: dict = Depends(get_current_user)):
    sites = core.site_list()
    if domain not in sites:
        raise HTTPException(status_code=404, detail="Site not found")
    site = sites[domain]
    server_type = site.get("server_type", "nginx")
    from atulya_launch.core import _generate_server_config
    config_content = _generate_server_config(
        domain,
        site.get("web_root", f"/var/www/{domain}/public"),
        server_type,
        site.get("php_enabled", False),
        site.get("extra_config"),
    )
    return {"domain": domain, "server_type": server_type, "config": config_content}
