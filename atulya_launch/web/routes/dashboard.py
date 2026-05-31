"""Routes for the main dashboard page."""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from typing import Any

from ... import core
from ..auth import require_auth, get_current_user
from ..database import connect

router: APIRouter = APIRouter()
templates: Jinja2Templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))


@router.get("/dashboard", response_class=HTMLResponse)
@require_auth
async def dashboard(request: Request) -> HTMLResponse:
    """Render the dashboard with system stats, sites, backups, and security data."""
    user: Any = request.state.user
    status: dict = core.system_status()
    sites: dict = core.site_list()
    backups: dict = core.backup_list()
    security: dict = core.security_scan()
    audit: list = core.audit_list(20)

    with connect() as cur:
        db_count: int = cur.execute("SELECT COUNT(*) as c FROM databases").fetchone()["c"]
        dns_count: int = cur.execute("SELECT COUNT(*) as c FROM dns_zones").fetchone()["c"]
        email_count: int = cur.execute("SELECT COUNT(*) as c FROM email_accounts").fetchone()["c"]
        ssl_count: int = cur.execute("SELECT COUNT(*) as c FROM ssl_certs").fetchone()["c"]
        user_count: int = cur.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]

    return templates.TemplateResponse(request, "dashboard.html", {
        "user": user,
        "status": status,
        "sites": sites,
        "backups": backups,
        "security": security,
        "audit": audit,
        "db_count": db_count,
        "dns_count": dns_count,
        "email_count": email_count,
        "ssl_count": ssl_count,
        "user_count": user_count,
    })


@router.get("/", response_class=HTMLResponse)
async def root(request: Request) -> HTMLResponse:
    """Redirect authenticated users to /dashboard, others to /login."""
    user: Any = get_current_user(request)
    if user:
        return HTMLResponse("", status_code=302, headers={"Location": "/dashboard"})
    return HTMLResponse("", status_code=302, headers={"Location": "/login"})
