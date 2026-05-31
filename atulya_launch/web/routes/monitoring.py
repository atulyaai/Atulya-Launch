import psutil
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from ... import core
from ..auth import require_auth

router = APIRouter(prefix="/monitoring")
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))


@router.get("", response_class=HTMLResponse)
@require_auth
async def monitoring_page(request: Request):
    status = core.system_status()
    processes = get_top_processes()
    return templates.TemplateResponse(request, "monitoring.html", {
        "user": request.state.user,
        "status": status,
        "processes": processes,
    })


@router.get("/api/live")
@require_auth
async def live_metrics(request: Request):
    cpu_percent = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage(str(core.CONFIG_DIR))
    net = psutil.net_io_counters()
    load = get_load_average()
    processes = get_top_processes()
    return JSONResponse({
        "cpu_percent": cpu_percent,
        "cpu_count": psutil.cpu_count(),
        "memory": {"total": mem.total, "used": mem.used, "percent": mem.percent},
        "disk": {"total": disk.total, "used": disk.used, "percent": disk.percent},
        "network": {"bytes_sent": net.bytes_sent, "bytes_recv": net.bytes_recv},
        "load_average": load,
        "processes": processes,
        "services": core.service_summary(),
    })


@router.get("/api/processes")
@require_auth
async def api_processes(request: Request):
    return JSONResponse(get_top_processes())


def get_top_processes():
    procs = []
    for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
        try:
            info = proc.info
            procs.append({
                "pid": info["pid"],
                "name": info["name"],
                "cpu": round(info["cpu_percent"] or 0, 1),
                "memory": round(info["memory_percent"] or 0, 1),
                "status": info["status"],
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    procs.sort(key=lambda p: p["cpu"], reverse=True)
    return procs[:30]


def get_load_average():
    try:
        load1, load5, load15 = psutil.getloadavg()
        return {"1m": round(load1, 2), "5m": round(load5, 2), "15m": round(load15, 2)}
    except (AttributeError, OSError):
        return {"1m": 0, "5m": 0, "15m": 0}
