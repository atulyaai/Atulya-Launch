"""
Atulya-Launch Web Application
Minimal FastAPI app for the control panel.
"""
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse


def create_app() -> FastAPI:
    app = FastAPI(
        title="Atulya-Launch",
        description="Lightweight cPanel alternative",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )

    config_dir = Path(os.environ.get("ATULYA_CONFIG_DIR", "/etc/atulya-launch"))
    data_dir = Path(os.environ.get("ATULYA_DATA_DIR", "/var/lib/atulya-launch"))

    @app.get("/")
    async def index():
        return {"status": "ok", "panel": "Atulya-Launch", "version": "0.1.0"}

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    @app.get("/api/status")
    async def api_status():
        import psutil
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        return {
            "cpu_percent": cpu,
            "memory_percent": mem.percent,
            "memory_used_mb": round(mem.used / 1024 / 1024, 1),
            "disk_percent": disk.percent,
            "disk_free_gb": round(disk.free / 1024 / 1024 / 1024, 1),
        }

    return app
