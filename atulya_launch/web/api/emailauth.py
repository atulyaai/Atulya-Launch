"""Email authentication records — SPF, DMARC, and DKIM policy management."""

import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from atulya_launch.web.auth import get_current_user
from atulya_launch.web.database import connect, audit_log

router = APIRouter(prefix="/api/email-auth", tags=["email auth"])


class EmailAuthUpdate(BaseModel):
    domain: str
    spf: Optional[str] = None
    dmarc: Optional[str] = None
    dkim_selector: Optional[str] = None
    dkim_policy: Optional[str] = None


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat() + "Z"


def default_spf(domain: str, include: Optional[str] = None) -> str:
    base = "v=spf1"
    if include:
        base += f" include:{include}"
    base += " mx -all"
    return base


def default_dmarc(domain: str, policy: str = "none") -> str:
    return f"v=DMARC1; p={policy}; rua=mailto:postmaster@{domain}; fo=1"


def _record_for(row) -> dict:
    row = dict(row)
    return {
        "domain": row["domain"],
        "spf": row.get("spf"),
        "dmarc": row.get("dmarc"),
        "dkim_selector": row.get("dkim_selector", "default"),
        "dkim_policy": row.get("dkim_policy", "relaxed"),
        "updated_at": row.get("updated_at"),
    }


@router.get("")
def list_records(user: dict = Depends(get_current_user)):
    with connect() as conn:
        rows = conn.execute("SELECT * FROM email_auth_records ORDER BY domain").fetchall()
    return {"records": [_record_for(r) for r in rows]}


@router.get("/defaults/{domain}")
def get_defaults(domain: str, user: dict = Depends(get_current_user)):
    return {
        "domain": domain,
        "spf": default_spf(domain),
        "dmarc": default_dmarc(domain),
        "spf_txt": f"{domain} IN TXT \"{default_spf(domain)}\"",
        "dmarc_txt": f"_dmarc.{domain} IN TXT \"{default_dmarc(domain)}\"",
    }


@router.post("")
def upsert_record(body: EmailAuthUpdate, user: dict = Depends(get_current_user)):
    domain = body.domain.lower()
    now = _now()
    with connect() as conn:
        existing = conn.execute("SELECT domain FROM email_auth_records WHERE domain = ?", (domain,)).fetchone()
        spf = body.spf
        dmarc = body.dmarc
        dkim_selector = body.dkim_selector
        dkim_policy = body.dkim_policy
        if existing:
            row = conn.execute("SELECT * FROM email_auth_records WHERE domain = ?", (domain,)).fetchone()
            spf = spf if spf is not None else row["spf"]
            dmarc = dmarc if dmarc is not None else row["dmarc"]
            dkim_selector = dkim_selector if dkim_selector is not None else row["dkim_selector"]
            dkim_policy = dkim_policy if dkim_policy is not None else row["dkim_policy"]
            conn.execute(
                "UPDATE email_auth_records SET spf = ?, dmarc = ?, dkim_selector = ?, dkim_policy = ?, updated_at = ? WHERE domain = ?",
                (spf, dmarc, dkim_selector, dkim_policy, now, domain),
            )
        else:
            conn.execute(
                "INSERT INTO email_auth_records (domain, spf, dmarc, dkim_selector, dkim_policy, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (domain, spf, dmarc, dkim_selector or "default", dkim_policy or "relaxed", now),
            )

    # Reflect the records into the DNS zone as TXT records when a zone exists.
    try:
        with connect() as conn:
            zone = conn.execute("SELECT id FROM dns_zones WHERE domain = ?", (domain,)).fetchone()
            if zone:
                known = {
                    r["name"]: r
                    for r in conn.execute("SELECT id, name, value FROM dns_records WHERE zone_id = ? AND type = 'TXT'", (zone["id"],)).fetchall()
                }
                if spf and spf.startswith("v=spf1"):
                    key = domain
                    if key in known:
                        conn.execute("UPDATE dns_records SET value = ? WHERE id = ?", (spf, known[key]["id"]))
                    else:
                        conn.execute("INSERT INTO dns_records (zone_id, name, type, value, ttl, created_at) VALUES (?, ?, 'TXT', ?, 3600, ?)", (zone["id"], key, spf, now))
                if dmarc and dmarc.startswith("v=DMARC1"):
                    key = f"_dmarc.{domain}"
                    if key in known:
                        conn.execute("UPDATE dns_records SET value = ? WHERE id = ?", (dmarc, known[key]["id"]))
                    else:
                        conn.execute("INSERT INTO dns_records (zone_id, name, type, value, ttl, created_at) VALUES (?, ?, 'TXT', ?, 3600, ?)", (zone["id"], key, dmarc, now))
    except Exception:
        pass

    audit_log(user.get("sub", "admin"), "email_auth.upsert", "ok", {"domain": domain})
    with connect() as conn:
        row = conn.execute("SELECT * FROM email_auth_records WHERE domain = ?", (domain,)).fetchone()
    return {"status": "saved", "record": _record_for(row)}


@router.post("/apply-defaults/{domain}")
def apply_defaults(domain: str, user: dict = Depends(get_current_user)):
    body = EmailAuthUpdate(domain=domain, spf=default_spf(domain), dmarc=default_dmarc(domain))
    return upsert_record(body=body, user=user)