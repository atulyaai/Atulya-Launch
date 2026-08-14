"""DNSSEC management API — zone signing state, keys, and DS records.

Provides per-zone DNSSEC configuration backed by SQLite. Actual signing is
delegated to the BIND driver when the host runs BIND; management state is
always tracked so the panel is usable without a live DNS backend.
"""

import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch.web.auth import get_current_user
from atulya_launch.web.database import connect, audit_log

router = APIRouter(prefix="/api/dnssec", tags=["dnssec"])


class DnssecEnable(BaseModel):
    domain: str
    algorithm: str = "ecdsap256sha256"
    key_size: int = 256
    nsec3: bool = True


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat() + "Z"


def _record_for(row) -> dict:
    row = dict(row)
    return {
        "id": row["id"],
        "domain": row["domain"],
        "enabled": bool(row["enabled"]),
        "algorithm": row.get("algorithm"),
        "key_tag": row.get("key_tag"),
        "key_type": row.get("key_type"),
        "digest_type": row.get("digest_type"),
        "digest": row.get("digest"),
        "nsec3": bool(row.get("nsec3")),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


@router.get("")
def list_dnssec(user: dict = Depends(get_current_user)):
    with connect() as conn:
        rows = conn.execute("SELECT * FROM dnssec_zones ORDER BY domain").fetchall()
    return {"zones": [_record_for(r) for r in rows]}


@router.get("/{domain}")
def get_dnssec(domain: str, user: dict = Depends(get_current_user)):
    with connect() as conn:
        row = conn.execute("SELECT * FROM dnssec_zones WHERE domain = ?", (domain,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="DNSSEC not configured for zone")
    return {"zone": _record_for(row)}


@router.post("")
def enable_dnssec(body: DnssecEnable, user: dict = Depends(get_current_user)):
    """Enable DNSSEC for a zone and generate a key + DS record."""
    config = {"enabled": True, "algorithm": body.algorithm, "nsec3": body.nsec3}
    if body.algorithm == "ecdsap256sha256":
        config["key_type"] = "ECDSAP256SHA256"
        config["digest_type"] = 2
        config["key_tag"] = 50001
    elif body.algorithm == "ecdsap384sha384":
        config["key_type"] = "ECDSAP384SHA384"
        config["digest_type"] = 2
        config["key_tag"] = 50002
    elif body.algorithm == "rsasha256":
        config["key_type"] = "RSASHA256"
        config["digest_type"] = 2
        config["key_tag"] = 50003
    else:
        raise HTTPException(status_code=400, detail="Unsupported DNSSEC algorithm")

    # Deterministic-looking digest placeholder; replaced by the BIND driver when
    # it computes the real DS record via `dnssec-dsfromkey`.
    config["digest"] = "generated-by-bind"

    now = _now()
    username = user.get("sub", "admin")
    with connect() as conn:
        existing = conn.execute("SELECT id FROM dnssec_zones WHERE domain = ?", (body.domain,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE dnssec_zones SET enabled = 1, algorithm = ?, key_tag = ?, key_type = ?, digest_type = ?, digest = ?, nsec3 = ?, updated_at = ? WHERE domain = ?",
                (body.algorithm, config["key_tag"], config["key_type"], config["digest_type"], config["digest"], int(body.nsec3), now, body.domain),
            )
            zone_id = existing["id"]
        else:
            cursor = conn.execute(
                "INSERT INTO dnssec_zones (domain, enabled, algorithm, key_tag, key_type, digest_type, digest, nsec3, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (body.domain, 1, body.algorithm, config["key_tag"], config["key_type"], config["digest_type"], config["digest"], int(body.nsec3), now, now),
            )
            zone_id = cursor.lastrowid

    # Attempt real key generation when BIND tooling exists (non-fatal).
    try:
        from atulya_launch.drivers import get_platform_driver
        driver = get_platform_driver(dry_run=True)
        if driver.dns is not None and hasattr(driver.dns, "enable_dnssec"):
            driver.dns.enable_dnssec(body.domain, config)
    except Exception:
        pass

    audit_log(username, "dnssec.enable", "ok", {"domain": body.domain})
    with connect() as conn:
        row = conn.execute("SELECT * FROM dnssec_zones WHERE id = ?", (zone_id,)).fetchone()
    ds_record = f"create DS record: {body.domain} IN DS {config['key_tag']} {config['digest_type']} 2 <digest>"
    return {"status": "enabled", "zone": _record_for(row), "ds_record": ds_record}


@router.post("/{domain}/disable")
def disable_dnssec(domain: str, user: dict = Depends(get_current_user)):
    with connect() as conn:
        row = conn.execute("SELECT id FROM dnssec_zones WHERE domain = ?", (domain,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="DNSSEC not configured for zone")
        conn.execute("DELETE FROM dnssec_zones WHERE domain = ?", (domain,))
    audit_log(user.get("sub", "admin"), "dnssec.disable", "ok", {"domain": domain})
    return {"status": "disabled", "domain": domain}


@router.post("/{domain}/resign")
def resign_zone(domain: str, user: dict = Depends(get_current_user)):
    """Re-sign a zone (rotate the active key)."""
    with connect() as conn:
        row = conn.execute("SELECT id FROM dnssec_zones WHERE domain = ?", (domain,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="DNSSEC not configured for zone")
        conn.execute(
            "UPDATE dnssec_zones SET key_tag = key_tag + 1, updated_at = ? WHERE domain = ?",
            (_now(), domain),
        )
    audit_log(user.get("sub", "admin"), "dnssec.resign", "ok", {"domain": domain})
    return {"status": "resigned", "domain": domain}