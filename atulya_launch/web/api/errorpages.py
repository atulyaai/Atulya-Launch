"""Custom error pages API."""

import os
import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/errorpages", tags=["errorpages"])

ERRORPAGES_FILE = utils.CONFIG_DIR / "errorpages.json"


def _load_errorpages() -> dict:
    if ERRORPAGES_FILE.exists():
        with open(ERRORPAGES_FILE, "r") as f:
            return json.load(f) or {}
    return {}


def _save_errorpages(data: dict):
    utils.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(ERRORPAGES_FILE, "w") as f:
        json.dump(data, f, indent=2)


class ErrorPageUpdate(BaseModel):
    content: str
    content_type: str = "text/html"


DEFAULT_ERROR_PAGES = {
    "404": "<!DOCTYPE html><html><head><title>404 Not Found</title></head><body><h1>404 - Page Not Found</h1><p>The requested page could not be found.</p></body></html>",
    "500": "<!DOCTYPE html><html><head><title>500 Internal Server Error</title></head><body><h1>500 - Internal Server Error</h1><p>Something went wrong on our end.</p></body></html>",
    "403": "<!DOCTYPE html><html><head><title>403 Forbidden</title></head><body><h1>403 - Forbidden</h1><p>You do not have permission to access this resource.</p></body></html>",
    "502": "<!DOCTYPE html><html><head><title>502 Bad Gateway</title></head><body><h1>502 - Bad Gateway</h1><p>The server received an invalid response.</p></body></html>",
    "503": "<!DOCTYPE html><html><head><title>503 Service Unavailable</title></head><body><h1>503 - Service Unavailable</h1><p>The service is temporarily unavailable.</p></body></html>",
}


@router.get("/{domain}")
def get_error_pages(domain: str, user: dict = Depends(get_current_user)):
    data = _load_errorpages()
    domain_pages = data.get(domain, {})
    # Merge with defaults
    result = {}
    for code, default in DEFAULT_ERROR_PAGES.items():
        result[code] = {
            "content": domain_pages.get(code, default),
            "custom": code in domain_pages,
            "content_type": "text/html",
        }
    return {"domain": domain, "pages": result}


@router.put("/{domain}/{code}")
def set_error_page(domain: str, code: str, body: ErrorPageUpdate, user: dict = Depends(get_current_user)):
    if code not in DEFAULT_ERROR_PAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported error code: {code}")
    data = _load_errorpages()
    if domain not in data:
        data[domain] = {}
    data[domain][code] = body.content
    _save_errorpages(data)
    # Write nginx error page if Linux
    if utils.is_linux():
        error_dir = f"/var/www/{domain}/error_pages"
        os.makedirs(error_dir, exist_ok=True)
        page_file = f"{error_dir}/{code}.html"
        with open(page_file, "w") as f:
            f.write(body.content)
    return {"status": "updated", "domain": domain, "code": code}


@router.delete("/{domain}/{code}")
def reset_error_page(domain: str, code: str, user: dict = Depends(get_current_user)):
    if code not in DEFAULT_ERROR_PAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported error code: {code}")
    data = _load_errorpages()
    if domain in data and code in data[domain]:
        del data[domain][code]
        _save_errorpages(data)
    # Remove custom file if Linux
    if utils.is_linux():
        page_file = f"/var/www/{domain}/error_pages/{code}.html"
        if os.path.exists(page_file):
            os.remove(page_file)
    return {"status": "reset to default", "domain": domain, "code": code}
