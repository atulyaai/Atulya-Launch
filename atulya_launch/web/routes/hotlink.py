from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from ... import core
from ..auth import require_auth
from ..database import audit_log

router = APIRouter(prefix="/hotlink", tags=["hotlink"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))


@router.get("", response_class=HTMLResponse)
@require_auth
async def hotlink_page(request: Request):
    domains = list(core.site_list().keys())
    hotlink_configs = {}
    for d in domains:
        hotlink_configs[d] = core.hotlink_protection_get(d)
    dir_rules = core.ip_directory_list()
    return templates.TemplateResponse(request, "hotlink.html", {
        "user": request.state.user,
        "domains": domains,
        "hotlink_configs": hotlink_configs,
        "dir_rules": dir_rules,
    })


@router.post("/set")
@require_auth
async def hotlink_set(request: Request, domain: str = Form(...), enabled: str = Form("off"),
                      extensions: str = Form(""), allow_domains: str = Form("")):
    is_enabled = enabled == "on"
    ext_list = [e.strip() for e in extensions.split(",") if e.strip()] if extensions else None
    allow_list = [d.strip() for d in allow_domains.split(",") if d.strip()] if allow_domains else None
    result = core.hotlink_protection_set(domain, is_enabled, extensions=ext_list, allow_domains=allow_list)
    audit_log(request.state.user["username"], "hotlink.set", "ok" if result.get("ok") else "error",
              {"domain": domain, "enabled": is_enabled})
    return RedirectResponse("/hotlink", status_code=302)


@router.post("/dir/allow")
@require_auth
async def hotlink_dir_allow(request: Request, domain: str = Form(...), directory: str = Form(...), ip_address: str = Form(...)):
    result = core.ip_directory_allow_add(domain, directory, ip_address)
    audit_log(request.state.user["username"], "hotlink.dir_allow", "ok" if result.get("ok") else "error",
              {"domain": domain, "directory": directory, "ip": ip_address})
    return RedirectResponse("/hotlink", status_code=302)


@router.post("/dir/deny")
@require_auth
async def hotlink_dir_deny(request: Request, domain: str = Form(...), directory: str = Form(...), ip_address: str = Form(...)):
    result = core.ip_directory_deny_add(domain, directory, ip_address)
    audit_log(request.state.user["username"], "hotlink.dir_deny", "ok" if result.get("ok") else "error",
              {"domain": domain, "directory": directory, "ip": ip_address})
    return RedirectResponse("/hotlink", status_code=302)


@router.post("/dir/remove")
@require_auth
async def hotlink_dir_remove(request: Request, domain: str = Form(...), directory: str = Form(...), ip_address: str = Form(...)):
    core.ip_directory_remove(domain, directory, ip_address)
    return RedirectResponse("/hotlink", status_code=302)
