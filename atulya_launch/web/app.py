"""
Atulya-Launch Web Application
FastAPI app for the lightweight cPanel alternative.
"""
import os
from pathlib import Path

from fastapi import FastAPI, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from atulya_launch import core, utils
from atulya_launch.web.auth import get_current_user, init_auth


def create_app() -> FastAPI:
    app = FastAPI(
        title="Atulya-Launch",
        description="Lightweight cPanel alternative — < 50MB RAM idle",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        redoc_url=None,
    )

    static_dir = Path(__file__).parent / "static"

    # ── Initialise auth (ensure admin user exists) ──
    @app.on_event("startup")
    def startup():
        init_auth()

    # ── Mount routers ──────────────────────────────────────────────────
    from atulya_launch.web.auth import router as auth_router
    from atulya_launch.web.api.sites import router as sites_router
    from atulya_launch.web.api.dns import router as dns_router
    from atulya_launch.web.api.email import router as email_router
    from atulya_launch.web.api.db import router as db_router
    from atulya_launch.web.api.files import router as files_router
    from atulya_launch.web.api.ssl import router as ssl_router
    from atulya_launch.web.api.backup import router as backup_router
    from atulya_launch.web.api.monitor import router as monitor_router
    from atulya_launch.web.api.firewall import router as firewall_router
    from atulya_launch.web.api.cron import router as cron_router
    from atulya_launch.web.api.apps import router as apps_router
    from atulya_launch.web.api.system import router as system_router

    app.include_router(auth_router)
    app.include_router(sites_router)
    app.include_router(dns_router)
    app.include_router(email_router)
    app.include_router(db_router)
    app.include_router(files_router)
    app.include_router(ssl_router)
    app.include_router(backup_router)
    app.include_router(monitor_router)
    app.include_router(firewall_router)
    app.include_router(cron_router)
    app.include_router(apps_router)
    app.include_router(system_router)

    # ── Aggregated dashboard endpoint ──────────────────────────────────
    @app.get("/api/dashboard/stats")
    def dashboard_stats(user: dict = Depends(get_current_user)):
        sites = core.site_list()
        dbs = core.db_list()
        certs = core.ssl_list()
        backups = core.backup_list()
        try:
            status = core.monitor_status()
        except Exception:
            status = {}
        return {
            "sites_count": len(sites),
            "databases_count": len(dbs),
            "ssl_count": len(certs),
            "backups_count": len(backups),
            "cpu_percent": status.get("cpu", {}).get("percent", 0),
            "memory_percent": status.get("memory", {}).get("percent", 0),
            "disk_percent": status.get("disk", {}).get("percent", 0),
            "uptime_hours": status.get("uptime", {}).get("uptime_hours", 0),
        }

    # ── Settings endpoints ─────────────────────────────────────────────
    @app.get("/api/settings")
    def get_settings(user: dict = Depends(get_current_user)):
        return core.config_show()

    @app.post("/api/settings/password")
    def change_password(body: dict, user: dict = Depends(get_current_user)):
        from atulya_launch.web.auth import _verify_password, _hash_password
        config = utils.load_config()
        auth_cfg = config.get("web", {}).get("auth", {})
        admin_hash = auth_cfg.get("admin_password_hash", "")
        if not _verify_password(body.get("current_password", ""), admin_hash):
            return JSONResponse(status_code=400, content={"error": "Current password is incorrect"})
        auth_cfg["admin_password_hash"] = _hash_password(body.get("new_password", ""))
        web_cfg = config.get("web", {})
        web_cfg["auth"] = auth_cfg
        config["web"] = web_cfg
        utils.save_config(config)
        return {"status": "password changed"}

    # ── Kill process endpoint ──────────────────────────────────────────
    @app.post("/api/monitor/processes/{pid}/kill")
    def kill_process(pid: int, user: dict = Depends(get_current_user)):
        import signal
        try:
            os.kill(pid, signal.SIGTERM)
            return {"status": "killed", "pid": pid}
        except ProcessLookupError:
            return JSONResponse(status_code=404, content={"error": "Process not found"})
        except PermissionError:
            return JSONResponse(status_code=403, content={"error": "Permission denied"})

    # ── Health check ───────────────────────────────────────────────────
    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    # ── Serve SPA: all non-API routes return index.html ────────────────
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"error": "Not found"})
        file_path = static_dir / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(static_dir / "index.html"))

    return app
