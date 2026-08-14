"""Site Publisher — quick marketing/under-construction template pages."""

import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user
from atulya_launch.web.database import connect, audit_log

router = APIRouter(prefix="/api/site-publisher", tags=["site publisher"])

TEMPLATES = {
    "coming_soon": {
        "name": "Coming Soon",
        "headline": "We're launching soon!",
        "default_html": "<h1 class='hs heading'>{title}</h1><p class='hs'>Something great is on the way.</p>",
    },
    "under_construction": {
        "name": "Under Construction",
        "headline": "Under Construction",
        "default_html": "<h1 class='hs heading'>{title}</h1><p class='hs'>This page is being built right now.</p>",
    },
    "maintenance": {
        "name": "Maintenance",
        "headline": "We'll be right back",
        "default_html": "<h1 class='hs heading'>{title}</h1><p class='hs'>Scheduled maintenance in progress.</p>",
    },
    "landing": {
        "name": "Simple Landing Page",
        "headline": "Welcome",
        "default_html": "<h1 class='hs heading'>{title}</h1><p class='hs'>{content}</p>",
    },
}


class PublishRequest(BaseModel):
    domain: str
    template: str = "coming_soon"
    title: str = "Welcome"
    content: str = ""
    published: bool = True


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat() + "Z"


@router.get("/templates")
def list_templates(user: dict = Depends(get_current_user)):
    return {"templates": TEMPLATES}


@router.get("")
def list_published(user: dict = Depends(get_current_user)):
    with connect() as conn:
        rows = conn.execute("SELECT * FROM site_publisher ORDER BY domain").fetchall()
    return {"pages": [dict(r) for r in rows]}


@router.post("")
def publish_page(body: PublishRequest, user: dict = Depends(get_current_user)):
    if body.template not in TEMPLATES:
        raise HTTPException(status_code=400, detail=f"Unknown template: {body.template}. Choices: {list(TEMPLATES)}")

    site = utils.load_config().get("sites", {}).get(body.domain)
    if not site:
        raise HTTPException(status_code=400, detail=f"Domain {body.domain} is not a managed site")

    template_html = TEMPLATES[body.template]["default_html"]
    page_html = template_html.replace("{title}", body.title).replace("{content}", body.content)
    page_html = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{body.title}</title>"
        "<style>body{margin:0;font-family:system-ui,sans-serif;background:#f6f7fb;display:grid;place-items:center;min-height:100vh;}"
        ".hs{text-align:center}body>.hs{max-width:40rem}holistic{color:#4f46e5;font-weight:700;font-size:2rem;margin-bottom:.5rem}</style>"
        "</head><body>"
        f"{page_html}"
        "</body></html>"
    )

    web_root = site.get("web_root") or str(utils.CONFIG_DIR / "sites" / body.domain)
    index_path = __import__("pathlib").Path(web_root) / "index.html"
    try:
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(page_html, encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write index.html: {e}")

    now = _now()
    username = user.get("sub", "admin")
    with connect() as conn:
        existing = conn.execute("SELECT id FROM site_publisher WHERE domain = ?", (body.domain,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE site_publisher SET template = ?, title = ?, content = ?, published = ?, updated_at = ? WHERE domain = ?",
                (body.template, body.title, body.content, int(body.published), now, body.domain),
            )
        else:
            conn.execute(
                "INSERT INTO site_publisher (domain, template, title, content, published, created_by, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (body.domain, body.template, body.title, body.content, int(body.published), username, now, now),
            )

    audit_log(username, "site_publisher.publish", "ok", {"domain": body.domain, "template": body.template})
    return {
        "status": "published" if body.published else "unpublished",
        "domain": body.domain,
        "template": body.template,
        "url": f"http://{body.domain}/",
    }


@router.delete("/{domain}")
def unpublish(domain: str, user: dict = Depends(get_current_user)):
    with connect() as conn:
        cursor = conn.execute("DELETE FROM site_publisher WHERE domain = ?", (domain,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="No published page for domain")
    audit_log(user.get("sub", "admin"), "site_publisher.delete", "ok", {"domain": domain})
    return {"status": "removed", "domain": domain}