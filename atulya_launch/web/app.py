"""FastAPI application factory for the Atulya Launch web panel.

Sets up routes, authentication, rate limiting, CSRF protection, and
global exception handlers.
"""

import os
import time
import secrets
import hashlib
import importlib
import pkgutil
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Any

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates


from .. import core
from .database import init_db
from .auth import get_current_user, authenticate, create_user, destroy_session


class RateLimiter:
    """SQLite-backed sliding window rate limiter with an in-memory fallback."""

    def __init__(self, max_attempts: int = 5, window_seconds: int = 300) -> None:
        self.max_attempts: int = max_attempts
        self.window: int = window_seconds
        self._attempts: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str) -> bool:
        """Check if the key is within the rate limit; record the attempt."""
        now: float = time.time()
        try:
            from .database import connect
            cutoff: float = now - self.window
            with connect() as conn:
                conn.execute("DELETE FROM rate_limit_attempts WHERE attempted_at < ?", (cutoff,))
                row: Any = conn.execute(
                    "SELECT COUNT(*) AS c FROM rate_limit_attempts WHERE key = ?",
                    (key,),
                ).fetchone()
                if row["c"] >= self.max_attempts:
                    return False
                conn.execute(
                    "INSERT INTO rate_limit_attempts (key, attempted_at) VALUES (?, ?)",
                    (key, now),
                )
                return True
        except Exception:
            pass
        self._attempts[key] = [t for t in self._attempts[key] if now - t < self.window]
        if len(self._attempts[key]) >= self.max_attempts:
            return False
        self._attempts[key].append(now)
        return True

    def reset(self, key: str) -> None:
        """Clear all recorded attempts for the given key."""
        try:
            from .database import connect
            with connect() as conn:
                conn.execute("DELETE FROM rate_limit_attempts WHERE key = ?", (key,))
        except Exception:
            pass
        self._attempts[key] = []


login_limiter: RateLimiter = RateLimiter(max_attempts=5, window_seconds=300)
global_limiter: RateLimiter = RateLimiter(max_attempts=60, window_seconds=60)


class CSRFToken:
    """CSRF token generator and validator using HMAC-SHA256."""

    def __init__(self) -> None:
        self._secret: str = secrets.token_hex(32)

    def generate(self, session_token: str) -> str:
        """Generate a CSRF token for the given session token."""
        msg: bytes = f"{session_token}:{self._secret}".encode()
        return hashlib.sha256(msg).hexdigest()[:16]

    def validate(self, session_token: str, token: str) -> bool:
        """Validate a CSRF token against the session token."""
        if not token or not session_token:
            return False
        expected: str = self.generate(session_token)
        return secrets.compare_digest(expected, token)


csrf: CSRFToken = CSRFToken()


def _csrf_exempt(path: str) -> bool:
    """Return whether a state-changing request should bypass CSRF validation."""
    return (
        path in {"/login", "/api/auth/login", "/api/auth/logout"}
        or path.startswith("/api/docs")
        or path.startswith("/openapi.json")
    )


def _register_api_routers(app: FastAPI) -> dict[str, list[str]]:
    """Mount every router from atulya_launch.web.api and report import failures."""
    from . import api

    registered: list[str] = []
    errors: list[str] = []
    for module_info in sorted(pkgutil.iter_modules(api.__path__), key=lambda item: item.name):
        if module_info.ispkg:
            continue
        module_name: str = f"{api.__name__}.{module_info.name}"
        try:
            module: Any = importlib.import_module(module_name)
            router: Any = getattr(module, "router", None)
            if router is None:
                errors.append(f"{module_info.name}: missing router")
                continue
            app.include_router(router)
            registered.append(module_info.name)
        except Exception as exc:
            errors.append(f"{module_info.name}: {exc.__class__.__name__}: {exc}")
    app.state.api_routers_registered = registered
    app.state.api_router_errors = errors
    return {"registered": registered, "errors": errors}


def create_app() -> FastAPI:
    """Create and configure the FastAPI application with all routes."""
    app: FastAPI = FastAPI(title="Atulya Launch", docs_url="/api/docs", redoc_url=None)

    config_dir: Path = core.ensure_dirs()
    init_db(config_dir)

    try:
        with __import__("contextlib").nullcontext():
            from .database import connect
            with connect() as cur:
                row: Any = cur.execute("SELECT COUNT(*) as c FROM users").fetchone()
                if row["c"] == 0:
                    admin_pass: str = os.environ.get("ADMIN_PASS", "admin")
                    create_user("admin", admin_pass, skip_policy=True)
    except Exception:
        pass

    templates: Jinja2Templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

    @app.middleware("http")
    async def csrf_middleware(request: Request, call_next: Any) -> Response:
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not _csrf_exempt(request.url.path):
            auth_header: str = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                session_token: str | None = request.cookies.get("session_token")
                if session_token:
                    submitted: str = request.headers.get("X-CSRF-Token", "")
                    if not csrf.validate(session_token, submitted):
                        return JSONResponse({"error": "invalid csrf token"}, status_code=403)
        return await call_next(request)

    from .routes import dashboard, sites, dns, email as email_mod, databases, ssl as ssl_mod, files, backups, monitoring, firewall, apps, settings, docker, migrations, cron as cron_mod, deploy, logs, security, loadtest, servers, mail as mail_mod, subdomains, redirects as redirect_mod, ipdeny, hotlink
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
    app.include_router(migrations.router)
    app.include_router(cron_mod.router)
    app.include_router(deploy.router)
    app.include_router(logs.router)
    app.include_router(security.router)
    app.include_router(loadtest.router)
    app.include_router(servers.router)
    app.include_router(mail_mod.router)
    app.include_router(subdomains.router)
    app.include_router(redirect_mod.router)
    app.include_router(ipdeny.router)
    app.include_router(hotlink.router)

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        if isinstance(exc, HTTPException):
            raise exc
        return JSONResponse(
            {"error": "internal server error", "detail": str(exc) if os.environ.get("PANEL_DEBUG") else None},
            status_code=500,
        )

    @app.get("/health")
    async def health() -> dict:
        from .database import connect
        db_ok: bool = False
        try:
            with connect() as cur:
                cur.execute("SELECT 1")
                db_ok = True
        except Exception:
            pass
        return {"status": "ok" if db_ok else "degraded", "database": db_ok, "version": core.__version__ if hasattr(core, "__version__") else "1.0.0"}

    @app.get("/api/sites")
    async def api_sites_root(request: Request) -> JSONResponse:
        user: Any = get_current_user(request)
        if not user:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return JSONResponse(list(core.site_list().values()))

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request) -> Response:
        user: Any = get_current_user(request)
        if user:
            return RedirectResponse("/dashboard", status_code=302)
        error: str | None = request.query_params.get("error")
        try:
            now: str = datetime.utcnow().isoformat() + "Z"
            with __import__("contextlib").nullcontext():
                from .database import connect
                with connect() as cur:
                    cur.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
        except Exception:
            pass
        return templates.TemplateResponse(request, "login.html", {"error": error})

    @app.post("/login")
    async def login_post(request: Request) -> RedirectResponse:
        client_ip: str = request.client.host if request.client else "unknown"
        if not login_limiter.check(client_ip):
            return RedirectResponse("/login?error=rate_limited", status_code=429)
        form: Any = await request.form()
        username: str = (form.get("username", "") or "").strip()
        password: str = form.get("password", "") or ""
        if not username or not password:
            return RedirectResponse("/login?error=1", status_code=302)
        result: Any = authenticate(username, password)
        if not result:
            return RedirectResponse("/login?error=1", status_code=302)
        login_limiter.reset(client_ip)
        response: RedirectResponse = RedirectResponse("/dashboard", status_code=302)
        response.set_cookie(
            "session_token", result["token"],
            httponly=True, samesite="lax",
            secure=os.environ.get("PANEL_HTTPS", "").lower() in ("1", "true"),
            max_age=86400,
            path="/",
        )
        return response

    @app.get("/logout")
    async def logout(request: Request) -> RedirectResponse:
        token: str | None = request.cookies.get("session_token")
        if token:
            destroy_session(token)
        response: RedirectResponse = RedirectResponse("/login", status_code=302)
        response.delete_cookie("session_token", path="/")
        return response

    @app.get("/api/auth/login", response_class=JSONResponse)
    async def api_login(request: Request) -> JSONResponse:
        return JSONResponse({"error": "use POST /login with form data"})

    @app.post("/api/auth/login")
    async def api_login_post(request: Request) -> JSONResponse:
        client_ip: str = request.client.host if request.client else "unknown"
        if not login_limiter.check(f"api:{client_ip}"):
            return JSONResponse({"error": "rate_limited"}, status_code=429)
        try:
            body: dict = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid json"}, status_code=400)
        username: str = (body.get("username", "") or "").strip()
        password: str = body.get("password", "") or ""
        if not username or not password:
            return JSONResponse({"error": "credentials required"}, status_code=400)
        result: Any = authenticate(username, password)
        if not result:
            return JSONResponse({"error": "invalid credentials"}, status_code=401)
        login_limiter.reset(f"api:{client_ip}")
        return JSONResponse({"token": result["token"], "expires": result["expires"]})

    @app.get("/api/auth/logout")
    async def api_logout(request: Request) -> JSONResponse:
        token: str | None = request.cookies.get("session_token")
        if not token:
            auth: str = request.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                token = auth[7:]
        if token:
            destroy_session(token)
        return JSONResponse({"ok": True})

    templates.env.globals["panel_version"] = "1.0.0"
    templates.env.globals["csrf_token"] = csrf.generate

    api_router_status: dict[str, list[str]] = _register_api_routers(app)

    @app.get("/api/router-status")
    async def api_router_status_endpoint() -> JSONResponse:
        return JSONResponse(api_router_status)

    return app


class _dummy:
    """Context manager stub for code paths that need a no-op context manager."""
    def __enter__(self) -> "_dummy": return self
    def __exit__(self, *a: Any) -> None: pass
