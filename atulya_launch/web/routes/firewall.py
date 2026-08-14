"""Routes for firewall (UFW) and Fail2Ban management."""
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from ... import core
from ..auth import require_auth
from ..database import audit_log

router: APIRouter = APIRouter(prefix="/firewall")
templates: Jinja2Templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))


@router.get("", response_class=HTMLResponse)
@require_auth
async def firewall_page(request: Request) -> HTMLResponse:
    """Render the firewall management page."""
    status: dict = core.firewall_status()
    rules: list = core.firewall_list_rules()
    fail2ban: dict = core.fail2ban_status()
    return templates.TemplateResponse(request, "firewall.html", {
        "user": request.state.user,
        "status": status,
        "rules": rules,
        "fail2ban": fail2ban,
    })


@router.post("/ufw/enable")
@require_auth
async def ufw_enable(request: Request) -> RedirectResponse:
    """Enable the UFW firewall."""
    result: dict = core.firewall_enable()
    audit_log(request.state.user["username"], "firewall.ufw_enable", "ok" if result.get("ok") else "error")
    return RedirectResponse("/firewall", status_code=302)


@router.post("/ufw/disable")
@require_auth
async def ufw_disable(request: Request) -> RedirectResponse:
    """Disable the UFW firewall."""
    result: dict = core.firewall_disable()
    audit_log(request.state.user["username"], "firewall.ufw_disable", "ok" if result.get("ok") else "error")
    return RedirectResponse("/firewall", status_code=302)


@router.post("/ufw/allow")
@require_auth
async def ufw_allow(request: Request, port: str = Form(...), proto: str = Form("tcp")) -> RedirectResponse:
    """Allow a port through the firewall."""
    core.firewall_allow(port, proto)
    audit_log(request.state.user["username"], "firewall.ufw_allow", "ok", {"port": port, "proto": proto})
    return RedirectResponse("/firewall", status_code=302)


@router.post("/ufw/deny")
@require_auth
async def ufw_deny(request: Request, port: str = Form(...), proto: str = Form("tcp")) -> RedirectResponse:
    """Deny a port through the firewall."""
    core.firewall_deny(port, proto)
    audit_log(request.state.user["username"], "firewall.ufw_deny", "ok", {"port": port, "proto": proto})
    return RedirectResponse("/firewall", status_code=302)


@router.post("/fail2ban/restart")
@require_auth
async def fail2ban_restart(request: Request) -> RedirectResponse:
    """Restart the Fail2Ban service."""
    result: dict = core.fail2ban_restart()
    audit_log(request.state.user["username"], "firewall.fail2ban_restart", "ok" if result.get("ok") else "error")
    return RedirectResponse("/firewall", status_code=302)


@router.get("/api/status")
@require_auth
async def api_firewall_status(request: Request) -> JSONResponse:
    """API endpoint returning firewall and Fail2Ban status."""
    return JSONResponse({
        "ufw": core.firewall_status(),
        "rules": core.firewall_list_rules(),
        "fail2ban": core.fail2ban_status(),
    })
