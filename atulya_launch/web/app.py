from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .. import core
from .database import init_db, connect as db_connect
from .auth import get_current_user, require_auth, require_admin, authenticate, hash_password, create_user, destroy_session


def create_app():
    app = FastAPI(title="Atulya Launch", docs_url="/api/docs", redoc_url=None)

    config_dir = core.ensure_dirs()
    init_db(config_dir)

    try:
        from .database import connect
        with connect() as cur:
            row = cur.execute("SELECT COUNT(*) as c FROM users").fetchone()
            if row["c"] == 0:
                create_user("admin", "admin")
    except Exception:
        pass

    templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

    from .routes import dashboard, sites, dns, email as email_mod, databases, ssl as ssl_mod, files, backups, monitoring, firewall, apps, settings, docker
    app.include_router(dashboard.router)
    app.include_router(sites.router)
    app.include_router(dns.router)
    app.include_router(email_mod.router)
    app.include_router(databases.router)
    app.include_router(ssl_mod.router)
    app.include_router(files.router)
    app.include_router(backups.router)
    app.include_router(monitoring.router)
    app.include_router(firewall.router)
    app.include_router(apps.router)
    app.include_router(settings.router)
    app.include_router(docker.router)

    @app.get("/api/sites")
    async def api_sites_root(request: Request):
        user = get_current_user(request)
        if not user:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return JSONResponse(list(core.site_list().values()))

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request):
        user = get_current_user(request)
        if user:
            return RedirectResponse("/dashboard", status_code=302)
        error = request.query_params.get("error")
        return templates.TemplateResponse(request, "login.html", {"error": error})

    @app.post("/login")
    async def login_post(request: Request):
        form = await request.form()
        username = form.get("username", "")
        password = form.get("password", "")
        result = authenticate(username, password)
        if not result:
            return RedirectResponse("/login?error=1", status_code=302)
        response = RedirectResponse("/dashboard", status_code=302)
        response.set_cookie("session_token", result["token"], httponly=True, samesite="lax", max_age=86400)
        return response

    @app.get("/logout")
    async def logout(request: Request):
        token = request.cookies.get("session_token")
        if token:
            destroy_session(token)
        response = RedirectResponse("/login", status_code=302)
        response.delete_cookie("session_token")
        return response

    @app.get("/api/auth/login", response_class=JSONResponse)
    async def api_login(request: Request):
        return JSONResponse({"error": "use POST /login with form data"})

    @app.post("/api/auth/login")
    async def api_login_post(request: Request):
        body = await request.json()
        result = authenticate(body.get("username", ""), body.get("password", ""))
        if not result:
            return JSONResponse({"error": "invalid credentials"}, status_code=401)
        return JSONResponse({"token": result["token"], "expires": result["expires"]})

    @app.get("/api/auth/logout")
    async def api_logout(request: Request):
        token = request.cookies.get("session_token")
        if not token:
            auth = request.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                token = auth[7:]
        if token:
            destroy_session(token)
        return JSONResponse({"ok": True})

    return app


class _dummy:
    def __enter__(self): return self
    def __exit__(self, *a): pass
