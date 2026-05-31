"""SQLite-backed DNS helpers with platform-driver apply support."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from atulya_launch.drivers import BindZone, get_platform_driver

from .database import connect


VALID_RECORD_TYPES: set[str] = {"A", "AAAA", "CNAME", "MX", "TXT", "NS", "SRV", "PTR"}


def _driver_dry_run() -> bool:
    return os.environ.get("ATULYA_DRIVER_APPLY", "").lower() not in {"1", "true", "yes"}


def _serial() -> int:
    return int(datetime.utcnow().strftime("%Y%m%d%H"))


def list_zones() -> dict[str, dict[str, Any]]:
    """Return all DNS zones keyed by domain for API compatibility."""
    with connect() as conn:
        rows = conn.execute("SELECT * FROM dns_zones ORDER BY domain").fetchall()
        zones: dict[str, dict[str, Any]] = {}
        for row in rows:
            zone = dict(row)
            records = [
                _record_to_api(dict(record))
                for record in conn.execute(
                    "SELECT * FROM dns_records WHERE zone_id = ? ORDER BY id",
                    (zone["id"],),
                ).fetchall()
            ]
            zones[zone["domain"]] = {
                "id": zone["id"],
                "domain": zone["domain"],
                "name": zone["domain"],
                "nameservers": [zone.get("soa_primary") or f"ns1.{zone['domain']}"],
                "records": records,
                "created_at": zone["created_at"],
            }
        return zones


def create_zone(domain: str, nameservers: list[str] | None = None) -> dict[str, Any]:
    """Create a DNS zone in SQLite."""
    ns = nameservers or [f"ns1.{domain}", f"ns2.{domain}"]
    with connect() as conn:
        existing = conn.execute("SELECT id FROM dns_zones WHERE domain = ?", (domain,)).fetchone()
        if existing:
            raise ValueError("Zone already exists")
        conn.execute(
            "INSERT INTO dns_zones (domain, soa_primary, soa_email, created_at) VALUES (?, ?, ?, ?)",
            (domain, ns[0], f"admin.{domain}", datetime.utcnow().isoformat() + "Z"),
        )
    return get_zone(domain)


def delete_zone(domain: str) -> bool:
    """Delete a DNS zone and remove it from the platform DNS driver."""
    with connect() as conn:
        row = conn.execute("SELECT id FROM dns_zones WHERE domain = ?", (domain,)).fetchone()
        if not row:
            return False
        conn.execute("DELETE FROM dns_zones WHERE id = ?", (row["id"],))
    driver = get_platform_driver(dry_run=_driver_dry_run())
    driver.dns.delete_zone(domain)
    return True


def get_zone(domain: str) -> dict[str, Any]:
    """Return one DNS zone with records."""
    zones = list_zones()
    if domain not in zones:
        raise KeyError("Zone not found")
    return zones[domain]


def add_record(domain: str, record_type: str, name: str, value: str, ttl: int = 3600) -> dict[str, Any]:
    """Add a DNS record to a zone."""
    record_type = record_type.upper()
    if record_type not in VALID_RECORD_TYPES:
        raise ValueError("Invalid record type")
    with connect() as conn:
        zone = conn.execute("SELECT id FROM dns_zones WHERE domain = ?", (domain,)).fetchone()
        if not zone:
            raise KeyError("Zone not found")
        cursor = conn.execute(
            "INSERT INTO dns_records (zone_id, name, type, value, ttl, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (zone["id"], name, record_type, value, ttl, datetime.utcnow().isoformat() + "Z"),
        )
        record_id = cursor.lastrowid
    return get_record(domain, int(record_id))


def update_record(domain: str, record_id: int, name: str | None = None, value: str | None = None, ttl: int | None = None) -> dict[str, Any]:
    """Update a DNS record."""
    current = get_record(domain, record_id)
    with connect() as conn:
        conn.execute(
            "UPDATE dns_records SET name = ?, value = ?, ttl = ? WHERE id = ?",
            (
                name if name is not None else current["name"],
                value if value is not None else current["content"],
                ttl if ttl is not None else current["ttl"],
                record_id,
            ),
        )
    return get_record(domain, record_id)


def delete_record(domain: str, record_id: int) -> bool:
    """Delete a DNS record from a zone."""
    with connect() as conn:
        zone = conn.execute("SELECT id FROM dns_zones WHERE domain = ?", (domain,)).fetchone()
        if not zone:
            raise KeyError("Zone not found")
        cursor = conn.execute(
            "DELETE FROM dns_records WHERE id = ? AND zone_id = ?",
            (record_id, zone["id"]),
        )
        return cursor.rowcount > 0


def get_record(domain: str, record_id: int) -> dict[str, Any]:
    """Return one DNS record in API shape."""
    with connect() as conn:
        row = conn.execute(
            """
            SELECT r.* FROM dns_records r
            JOIN dns_zones z ON z.id = r.zone_id
            WHERE z.domain = ? AND r.id = ?
            """,
            (domain, record_id),
        ).fetchone()
        if not row:
            raise KeyError("Record not found")
        return _record_to_api(dict(row))


def apply_zone(domain: str) -> dict[str, Any]:
    """Apply a zone through the current platform DNS driver."""
    zone = get_zone(domain)
    driver = get_platform_driver(dry_run=_driver_dry_run())
    result = driver.dns.apply_zone(
        BindZone(
            domain=domain,
            serial=_serial(),
            records=[
                {
                    "name": record["name"],
                    "type": record["type"],
                    "value": record["content"],
                    "ttl": record.get("ttl", 3600),
                }
                for record in zone["records"]
            ],
        )
    )
    return {
        "ok": result.ok,
        "action": result.action,
        "changed": result.changed,
        "message": result.message,
        "commands": result.commands,
        "files": result.files,
        "dry_run": _driver_dry_run(),
    }


def _record_to_api(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record["id"],
        "type": record["type"],
        "name": record["name"],
        "content": record["value"],
        "value": record["value"],
        "ttl": record["ttl"],
        "created_at": record["created_at"],
    }
