"""Per-Site Error Logs API."""

import os
import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/sites", tags=["site-logs"])

LOG_PATHS = {
    "nginx_error": "/var/log/nginx/error.log",
    "nginx_access": "/var/log/nginx/access.log",
    "apache_error": "/var/log/apache2/error.log",
    "apache_access": "/var/log/apache2/access.log",
    "php_error": "/var/log/php_errors.log",
}


def _resolve_site_log_path(domain: str, log_type: str) -> Optional[str]:
    nginx_log = f"/var/log/nginx/{domain}_{log_type}.log"
    if Path(nginx_log).exists():
        return nginx_log

    nginx_global = LOG_PATHS.get(f"nginx_{log_type}")
    if nginx_global and Path(nginx_global).exists():
        return nginx_global

    apache_log = f"/var/log/apache2/{domain}_{log_type}.log"
    if Path(apache_log).exists():
        return apache_log

    site_config = utils.load_config().get("sites", {}).get(domain, {})
    web_root = site_config.get("web_root", f"/var/www/{domain}")
    custom_log = Path(web_root) / "logs" / f"{log_type}.log"
    if custom_log.exists():
        return str(custom_log)

    return None


def _read_log_lines(file_path: str, lines: int = 100, search: Optional[str] = None, level: Optional[str] = None) -> dict:
    try:
        with open(file_path, "r", errors="replace") as f:
            all_lines = f.readlines()
    except PermissionError:
        return {"error": "Permission denied", "lines": []}
    except FileNotFoundError:
        return {"error": "Log file not found", "lines": []}

    if search:
        all_lines = [l for l in all_lines if search.lower() in l.lower()]

    if level:
        level_patterns = {
            "error": r"\berror\b|\bfatal\b|\bcritical\b",
            "warning": r"\bwarning\b|\bwarn\b",
            "notice": r"\bnotice\b|\binfo\b",
            "debug": r"\bdebug\b",
        }
        pattern = level_patterns.get(level.lower())
        if pattern:
            all_lines = [l for l in all_lines if re.search(pattern, l, re.IGNORECASE)]

    total = len(all_lines)
    result_lines = [l.rstrip() for l in all_lines[-lines:]]

    return {
        "file": file_path,
        "total_lines": total,
        "returned_lines": len(result_lines),
        "lines": result_lines,
    }


@router.get("/{domain}/logs/error")
def get_site_error_logs(
    domain: str,
    lines: int = Query(100, ge=1, le=10000),
    search: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    sites = utils.load_config().get("sites", {})
    if domain not in sites:
        raise HTTPException(status_code=404, detail="Site not found")

    log_path = _resolve_site_log_path(domain, "error")
    if not log_path:
        return {"error": "No error log found for this site", "lines": [], "suggestion": "Ensure logging is configured"}

    return _read_log_lines(log_path, lines=lines, search=search)


@router.get("/{domain}/logs/access")
def get_site_access_logs(
    domain: str,
    lines: int = Query(100, ge=1, le=10000),
    search: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    sites = utils.load_config().get("sites", {})
    if domain not in sites:
        raise HTTPException(status_code=404, detail="Site not found")

    log_path = _resolve_site_log_path(domain, "access")
    if not log_path:
        return {"error": "No access log found for this site", "lines": []}

    return _read_log_lines(log_path, lines=lines, search=search)


@router.get("/{domain}/logs/{log_type}")
def get_site_logs(
    domain: str,
    log_type: str,
    lines: int = Query(100, ge=1, le=10000),
    search: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    sites = utils.load_config().get("sites", {})
    if domain not in sites:
        raise HTTPException(status_code=404, detail="Site not found")

    if log_type not in ("error", "access", "php", "combined"):
        raise HTTPException(status_code=400, detail="Invalid log type. Use: error, access, php, combined")

    log_path = _resolve_site_log_path(domain, log_type)
    if not log_path:
        return {"error": f"No {log_type} log found for this site", "lines": []}

    return _read_log_lines(log_path, lines=lines, search=search, level=level)


@router.get("/{domain}/logs")
def list_available_logs(domain: str, user: dict = Depends(get_current_user)):
    sites = utils.load_config().get("sites", {})
    if domain not in sites:
        raise HTTPException(status_code=404, detail="Site not found")

    available = []
    for log_type in ("error", "access", "php"):
        log_path = _resolve_site_log_path(domain, log_type)
        if log_path:
            p = Path(log_path)
            stat = p.stat() if p.exists() else None
            available.append({
                "type": log_type,
                "path": log_path,
                "size_bytes": stat.st_size if stat else 0,
                "readable": p.exists() and os.access(log_path, os.R_OK),
            })

    return {"domain": domain, "logs": available}
