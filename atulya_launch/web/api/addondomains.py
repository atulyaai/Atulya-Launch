"""Addon domains — extra domains attached to an account with their own docroot."""

import datetime
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user
from atulya_launch.web.database import connect, audit_log

router = APIRouter(prefix="/api/addon-domains", tags=["addon domains"])

VALID_DOMAIN = re.compile(r"^(?=.{1,253}$)([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}$")


class AddonDomainCreate(BaseModel):
    domain: str
    root_domain: str
    document_root: Optional[str] = None


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat() + "Z"


def _validate_domain(domain: str) -> None:
    if not VALID_DOMAIN.match(domain):
        raise HTTPException(status_code=400, detail=f"Invalid domain: {domain}")


@router.get("")
def list_addon_domains(user: dict = Depends(get_current_user)):
    with connect() as conn:
        rows = conn.execute("SELECT * FROM addon_domains ORDER BY domain").fetchall()
    return {"addon_domains": [dict(r) for r in rows]}


@router.post("")
def create_addon_domain(body: AddonDomainCreate, user: dict = Depends(get_current_user)):
    _validate_domain(body.domain)
    _validate_domain(body.root_domain)
    if body.domain == body.root_domain:
        raise HTTPException(status_code=400, detail="Addon domain must differ from its root domain")

    site = utils.load_config().get("sites", {}).get(body.root_domain)
    if not site:
        raise HTTPException(status_code=400, detail=f"Root domain {body.root_domain} is not a managed site")

    web_root = site.get("web_root") or str(utils.CONFIG_DIR / "sites" / body.root_domain)
    document_root = body.document_root or str(__import__("pathlib").Path(web_root) / body.domain.split(".")[0])

    now = _now()
    username = user.get("sub", "admin")
    try:
        with connect() as conn:
            cursor = conn.execute(
                "INSERT INTO addon_domains (domain, root_domain, document_root, created_by, created_at) VALUES (?, ?, ?, ?, ?)",
                (body.domain, body.root_domain, document_root, username, now),
            )
            addon_id = cursor.lastrowid
    except Exception as e:
        if "UNIQUE" in str(e):
            raise HTTPException(status_code=409, detail="Addon domain already exists")
        raise HTTPException(status_code=500, detail=str(e))

    target = __import__("pathlib").Path(document_root)
    try:
        target.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    # Register as a served site + DNS zone so the addon domain resolves and serves.
    from atulya_launch import core
    try:
        core.site_create(body.domain, web_root=str(target), )
    except Exception:
        pass
    try:
        with connect() as conn:
            if not conn.execute("SELECT id FROM dns_zones WHERE domain = ?", (body.domain,)).fetchone():
                conn.execute(
                    "INSERT INTO dns_zones (domain, soa_primary, soa_email, created_at) VALUES (?, 'ns1', 'admin', ?)",
                    (body.domain, now),
                )
                conn.execute(
                    "INSERT INTO dns_records (zone_id, name, type, value, ttl, created_at) VALUES "
                    "(last_insert_rowid(), ?, 'A', '127.0.0.1', 3600, ?)",
                    (body.domain, now),
                )
    except Exception:
        pass

    audit_log(username, "addon_domain.create", "ok", {"domain": body.domain, "root": body.root_domain})
    return {"status": "created", "id": addon_id, "domain": body.domain, "document_root": document_root}


@router.delete("/{domain}")
def delete_addon_domain(domain: str, user: dict = Depends(get_current_user)):
    with connect() as conn:
        cursor = conn.execute("DELETE FROM addon_domains WHERE domain = ?", (domain,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Addon domain not found")
    from atulya_launch import core
    try:
        core.site_delete(domain)
    except Exception:
        pass
    audit_log(user.get("sub", "admin"), "addon_domain.delete", "ok", {"domain": domain})
    return {"status": "deleted", "domain": domain}