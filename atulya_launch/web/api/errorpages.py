"""Custom error pages API."""

import os
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user
from atulya_launch.web.database import connect

router = APIRouter(prefix="/api/errorpages", tags=["errorpages"])


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
    with connect() as conn:
        rows = conn.execute(
            "SELECT code, content, content_type FROM error_pages WHERE domain = ?",
            (domain,),
        ).fetchall()
    custom = {r["code"]: {"content": r["content"], "content_type": r["content_type"]} for r in rows}
    result = {}
    for code, default in DEFAULT_ERROR_PAGES.items():
        if code in custom:
            result[code] = {"content": custom[code]["content"], "custom": True, "content_type": custom[code]["content_type"]}
        else:
            result[code] = {"content": default, "custom": False, "content_type": "text/html"}
    return {"domain": domain, "pages": result}


@router.put("/{domain}/{code}")
def set_error_page(domain: str, code: str, body: ErrorPageUpdate, user: dict = Depends(get_current_user)):
    if code not in DEFAULT_ERROR_PAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported error code: {code}")
    with connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO error_pages (domain, code, content, content_type)
               VALUES (?, ?, ?, ?)""",
            (domain, code, body.content, body.content_type),
        )
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
    with connect() as conn:
        conn.execute("DELETE FROM error_pages WHERE domain = ? AND code = ?", (domain, code))
    if utils.is_linux():
        page_file = f"/var/www/{domain}/error_pages/{code}.html"
        if os.path.exists(page_file):
            os.remove(page_file)
    return {"status": "reset to default", "domain": domain, "code": code}
