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
from urllib.parse import parse_qs
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Any

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates


from .. import core
from .database import init_db, audit_log
from .auth import get_current_user, authenticate, create_user, destroy_session, validate_partial_session, destroy_partial_session, complete_2fa_login, _verify_totp
from .flash import add_flash, request_flashes


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


def _production_mode() -> bool:
    """Return whether production safety checks should be enforced."""
    return os.environ.get("ATULYA_PRODUCTION", os.environ.get("PANEL_PRODUCTION", "")).lower() in {"1", "true", "yes"}


def _register_api_routers(app: FastAPI) -> dict[str, list[str]]:
    """Mount every router from atulya_launch.web.api and report import failures."""
    from . import api

    registered: list[str] = []
    errors: list[str] = []
    for module_info in sorted(pkgutil.iter_modules(api.__path__), key=lambda item: item.name):
        if module_info.name == "plugins":
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

    # Auto-discover plugin API modules
    plugins_path = Path(__file__).parent / "api" / "plugins"
    if plugins_path.is_dir():
        for plugin_info in sorted(pkgutil.iter_modules([str(plugins_path)])):
            plugin_name: str = f"atulya_launch.web.api.plugins.{plugin_info.name}"
            try:
                plugin_module: Any = importlib.import_module(plugin_name)
                plugin_router: Any = getattr(plugin_module, "router", None)
                if plugin_router is not None:
                    app.include_router(plugin_router)
                    registered.append(f"plugins/{plugin_info.name}")
            except Exception as exc:
                errors.append(f"plugins/{plugin_info.name}: {exc.__class__.__name__}: {exc}")

    app.state.api_routers_registered = registered
    app.state.api_router_errors = errors
    return {"registered": registered, "errors": errors}


def _install_template_globals(template_sets: list[Any]) -> None:
    """Install shared template helpers across route-local Jinja environments."""
    for template_set in template_sets:
        template_set.env.globals["panel_version"] = "1.0.0"
        template_set.env.globals["csrf_token"] = csrf.generate
        template_set.env.globals["get_flashed_messages"] = request_flashes


def create_app() -> FastAPI:
    """Create and configure the FastAPI application with all routes."""
    app: FastAPI = FastAPI(title="Atulya Launch", docs_url="/api/docs", redoc_url=None)

    config_dir: Path = core.ensure_dirs()
    init_db(config_dir)

    try:
        from .sites_service import migrate_config_json_to_sqlite
        migrate_config_json_to_sqlite()
    except Exception:
        pass

    try:
        with __import__("contextlib").nullcontext():
            from .database import connect
            with connect() as cur:
                row: Any = cur.execute("SELECT COUNT(*) as c FROM users").fetchone()
                if row["c"] == 0:
                    admin_pass: str = os.environ.get("ADMIN_PASS", "admin")
                    if _production_mode() and admin_pass == "admin":
                        raise RuntimeError("ADMIN_PASS must be set to a non-default password in production mode")
                    create_user("admin", admin_pass, skip_policy=True)
    except RuntimeError:
        raise
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
                    if not submitted and "form" in request.headers.get("content-type", ""):
                        body = await request.body()
                        form_values = parse_qs(body.decode("utf-8"), keep_blank_values=True)
                        submitted = str((form_values.get("_csrf_token") or [""])[0])

                        async def receive() -> dict[str, Any]:
                            return {"type": "http.request", "body": body, "more_body": False}

                        request._receive = receive  # type: ignore[attr-defined]
                    if not csrf.validate(session_token, submitted):
                        return JSONResponse({"error": "invalid csrf token"}, status_code=403)
        return await call_next(request)

    from .routes import dashboard, sites, dns, email as email_mod, databases, ssl as ssl_mod, files, backups, monitoring, firewall, apps, settings, docker, migrations, cron as cron_mod, deploy, logs, security, loadtest, servers, mail as mail_mod, subdomains, redirects as redirect_mod, ipdeny, hotlink, sshterminal, webmail as webmail_mod
    _install_template_globals([
        templates,
        dashboard.templates,
        sites.templates,
        dns.templates,
        email_mod.templates,
        databases.templates,
        ssl_mod.templates,
        files.templates,
        backups.templates,
        monitoring.templates,
        firewall.templates,
        apps.templates,
        settings.templates,
        docker.templates,
        migrations.templates,
        cron_mod.templates,
        deploy.templates,
        logs.templates,
        security.templates,
        loadtest.templates,
        servers.templates,
        mail_mod.templates,
        sshterminal.templates,
        subdomains.templates,
        redirect_mod.templates,
        ipdeny.templates,
        hotlink.templates,
        webmail_mod.templates,
    ])
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
    app.include_router(sshterminal.router)
    app.include_router(subdomains.router)
    app.include_router(redirect_mod.router)
    app.include_router(ipdeny.router)
    app.include_router(hotlink.router)
    app.include_router(webmail_mod.router)

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
        if result.get("requires_2fa"):
            response = RedirectResponse("/login/2fa", status_code=302)
            response.set_cookie(
                "partial_token", result["partial_token"],
                httponly=True, samesite="lax",
                secure=os.environ.get("PANEL_HTTPS", "").lower() in ("1", "true"),
                max_age=300, path="/",
            )
            return response
        login_limiter.reset(client_ip)
        if result.get("must_change_password"):
            response = RedirectResponse("/settings/password?must_change=1", status_code=302)
            response.set_cookie(
                "session_token", result["token"],
                httponly=True, samesite="lax",
                secure=os.environ.get("PANEL_HTTPS", "").lower() in ("1", "true"),
                max_age=86400, path="/",
            )
            add_flash(result["token"], "You must change your password before continuing.", "warning")
            return response
        response: RedirectResponse = RedirectResponse("/dashboard", status_code=302)
        response.set_cookie(
            "session_token", result["token"],
            httponly=True, samesite="lax",
            secure=os.environ.get("PANEL_HTTPS", "").lower() in ("1", "true"),
            max_age=86400,
            path="/",
        )
        add_flash(result["token"], "Signed in successfully.", "success")
        return response

    @app.get("/login/2fa", response_class=HTMLResponse)
    async def login_2fa_page(request: Request) -> Response:
        partial_token: str | None = request.cookies.get("partial_token")
        username = validate_partial_session(partial_token)
        if not username:
            return RedirectResponse("/login?error=session_expired", status_code=302)
        error: str = request.query_params.get("error", "")
        return templates.TemplateResponse(request, "2fa_challenge.html", {"error": error, "username": username})

    @app.post("/login/2fa")
    async def login_2fa_post(request: Request) -> RedirectResponse:
        client_ip: str = request.client.host if request.client else "unknown"
        if not login_limiter.check(client_ip):
            return RedirectResponse("/login/2fa?error=rate_limited", status_code=429)
        partial_token: str | None = request.cookies.get("partial_token")
        username = validate_partial_session(partial_token)
        if not username:
            return RedirectResponse("/login?error=session_expired", status_code=302)
        form: Any = await request.form()
        code: str = (form.get("code", "") or "").strip()
        if not code or len(code) != 6:
            return RedirectResponse("/login/2fa?error=invalid_code", status_code=302)
        if not _verify_totp(username, code):
            audit_log(username, "auth.login.2fa_failed", "denied")
            return RedirectResponse("/login/2fa?error=invalid_code", status_code=302)
        destroy_partial_session(partial_token)
        login_limiter.reset(client_ip)
        session = complete_2fa_login(username)
        if not session:
            return RedirectResponse("/login?error=1", status_code=302)
        response = RedirectResponse("/dashboard", status_code=302)
        response.delete_cookie("partial_token", path="/")
        response.set_cookie(
            "session_token", session["token"],
            httponly=True, samesite="lax",
            secure=os.environ.get("PANEL_HTTPS", "").lower() in ("1", "true"),
            max_age=86400, path="/",
        )
        add_flash(session["token"], "Signed in successfully (2FA).", "success")
        return response

    @app.get("/logout")
    async def logout(request: Request) -> RedirectResponse:
        token: str | None = request.cookies.get("session_token")
        if token:
            add_flash(token, "Signed out successfully.", "info")
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
        if result.get("requires_2fa"):
            return JSONResponse({
                "requires_2fa": True,
                "partial_token": result["partial_token"],
                "message": "2FA code required. POST to /api/auth/2fa with partial_token and code.",
            })
        login_limiter.reset(f"api:{client_ip}")
        resp = {"token": result["token"], "expires": result["expires"]}
        if result.get("must_change_password"):
            resp["must_change_password"] = True
            resp["message"] = "You must change your password. POST to /api/auth/change-password."
        return JSONResponse(resp)

    @app.post("/api/auth/2fa")
    async def api_2fa_post(request: Request) -> JSONResponse:
        client_ip: str = request.client.host if request.client else "unknown"
        if not login_limiter.check(f"api:{client_ip}"):
            return JSONResponse({"error": "rate_limited"}, status_code=429)
        try:
            body: dict = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid json"}, status_code=400)
        partial_token: str = body.get("partial_token", "")
        code: str = body.get("code", "")
        if not partial_token or not code:
            return JSONResponse({"error": "partial_token and code required"}, status_code=400)
        username = validate_partial_session(partial_token)
        if not username:
            return JSONResponse({"error": "invalid or expired partial token"}, status_code=401)
        if not _verify_totp(username, code):
            audit_log(username, "auth.login.2fa_failed", "denied")
            return JSONResponse({"error": "invalid 2FA code"}, status_code=401)
        destroy_partial_session(partial_token)
        login_limiter.reset(f"api:{client_ip}")
        session = complete_2fa_login(username)
        if not session:
            return JSONResponse({"error": "login failed"}, status_code=500)
        return JSONResponse({"token": session["token"], "expires": session["expires"]})

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

    @app.post("/api/auth/change-password")
    async def api_change_password(request: Request) -> JSONResponse:
        user = get_current_user(request)
        if not user:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        try:
            body: dict = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid json"}, status_code=400)
        new_password = body.get("new_password", "")
        if not new_password or len(new_password) < 8:
            return JSONResponse({"error": "password must be at least 8 characters"}, status_code=400)
        from .auth import hash_password, validate_password_policy
        errors = validate_password_policy(new_password)
        if errors:
            return JSONResponse({"error": f"Password policy: {'; '.join(errors)}"}, status_code=400)
        pw_hash = hash_password(new_password)
        with connect() as cur:
            cur.execute("UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?", (pw_hash, user["id"]))
        audit_log(user["username"], "auth.password_change", "ok")
        return JSONResponse({"ok": True, "message": "Password changed successfully"})

    templates.env.globals["panel_version"] = "1.0.0"
    templates.env.globals["csrf_token"] = csrf.generate
    templates.env.globals["get_flashed_messages"] = request_flashes

    api_router_status: dict[str, list[str]] = _register_api_routers(app)

    @app.get("/api/router-status")
    async def api_router_status_endpoint() -> JSONResponse:
        return JSONResponse(api_router_status)

    # Start background scheduler
    try:
        from .scheduler import start_scheduler
        start_scheduler()
    except Exception:
        pass

    return app


class _dummy:
    """Context manager stub for code paths that need a no-op context manager."""
    def __enter__(self) -> "_dummy": return self
    def __exit__(self, *a: Any) -> None: pass
