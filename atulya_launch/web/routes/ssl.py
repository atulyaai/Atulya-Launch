from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from ... import core
from ..auth import require_auth
from ..database import connect, audit_log

router = APIRouter(prefix="/ssl")
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))


@router.get("", response_class=HTMLResponse)
@require_auth
async def ssl_list(request: Request):
    with connect() as cur:
        certs = [dict(r) for r in cur.execute("SELECT * FROM ssl_certs ORDER BY domain").fetchall()]
    return templates.TemplateResponse(request, "ssl.html", {
        "user": request.state.user,
        "certs": certs,
    })


@router.post("/issue")
@require_auth
async def ssl_issue(request: Request, domain: str = Form(...)):
    result = core.ssl_issue_letsencrypt(domain)
    with connect() as cur:
        cur.execute(
            "INSERT INTO ssl_certs (domain, cert_path, key_path, issuer, expires_at, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (domain, result.get("cert_path"), result.get("key_path"), "Let's Encrypt", result.get("expires_at"), __import__("datetime").datetime.utcnow().isoformat() + "Z"),
        )
    audit_log(request.state.user["username"], "ssl.issue", "ok", {"domain": domain})
    return RedirectResponse("/ssl", status_code=302)


@router.post("/renew")
@require_auth
async def ssl_renew(request: Request, cert_id: int = Form(...)):
    with connect() as cur:
        row = cur.execute("SELECT * FROM ssl_certs WHERE id = ?", (cert_id,)).fetchone()
    if row:
        result = core.ssl_renew(row["domain"])
        audit_log(request.state.user["username"], "ssl.renew", "ok", {"domain": row["domain"]})
        return JSONResponse(result)
    return JSONResponse({"error": "certificate not found"}, status_code=404)


@router.post("/delete")
@require_auth
async def ssl_delete(request: Request, cert_id: int = Form(...)):
    with connect() as cur:
        cur.execute("DELETE FROM ssl_certs WHERE id = ?", (cert_id,))
    audit_log(request.state.user["username"], "ssl.delete", "ok", {"cert_id": cert_id})
    return RedirectResponse("/ssl", status_code=302)


@router.get("/api/certs")
@require_auth
async def api_certs(request: Request):
    with connect() as cur:
        certs = [dict(r) for r in cur.execute("SELECT * FROM ssl_certs").fetchall()]
    return JSONResponse(certs)
