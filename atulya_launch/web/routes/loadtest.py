"""Routes for load testing."""
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from ... import core
from ..auth import require_admin
from ..database import audit_log

router: APIRouter = APIRouter(prefix="/loadtest")
templates: Jinja2Templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))


@router.get("", response_class=HTMLResponse)
@require_admin
async def loadtest_page(request: Request) -> HTMLResponse:
    """Render the load testing page."""
    return templates.TemplateResponse(request, "loadtest.html", {"user": request.state.user})


@router.post("/run")
@require_admin
async def loadtest_run(request: Request, target: str = Form(...), requests: int = Form(10), concurrency: int = Form(2)) -> JSONResponse:
    """Run a load test against a target URL."""
    result: dict = core.load_test(target, requests=requests, concurrency=concurrency)
    audit_log(request.state.user["username"], "loadtest.run", "ok", {"target": target, "requests": requests, "concurrency": concurrency})
    return JSONResponse(result)


@router.get("/api/run")
@require_admin
async def api_run(request: Request, target: str = "http://127.0.0.1:8080", requests: int = 5, concurrency: int = 2) -> JSONResponse:
    """API endpoint to run a load test."""
    return JSONResponse(core.load_test(target, requests=requests, concurrency=concurrency))
