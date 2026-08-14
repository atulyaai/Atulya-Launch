"""SQLite-backed backup management — replaces config.json for web routes."""

from __future__ import annotations

import os
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..web.database import connect, audit_log


def list_backups() -> dict[str, Any]:
    """Return all backups from SQLite."""
    with connect() as conn:
        rows = conn.execute("SELECT * FROM backups ORDER BY created_at DESC").fetchall()
    backups = {}
    for row in rows:
        b = dict(row)
        backups[b["name"]] = {
            "name": b["name"],
            "path": b["path"],
            "size": b["size"],
            "created_at": b["created_at"],
        }
    return backups


def create_backup(name: str | None = None) -> dict[str, Any]:
    """Create a backup and store metadata in SQLite."""
    from .. import core
    core.ensure_dirs()
    stamp = datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y%m%d_%H%M%S")
    backup_name = name or f"backup-{stamp}"
    archive_path = core.BACKUPS_DIR / f"{backup_name}.zip"

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        if core.CONFIG_FILE.exists():
            archive.write(core.CONFIG_FILE, "config.json")
        for site_root in core.WEBROOTS_DIR.glob("*"):
            if site_root.is_dir():
                for item in site_root.rglob("*"):
                    if item.is_file():
                        archive.write(item, item.relative_to(core.CONFIG_DIR))

    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO backups (name, path, size, created_at) VALUES (?, ?, ?, ?)",
            (backup_name, str(archive_path), archive_path.stat().st_size, now),
        )

    audit_log("system", "backup.create", "ok", {"name": backup_name})
    return {
        "name": backup_name,
        "path": str(archive_path),
        "size": archive_path.stat().st_size,
        "created_at": now,
    }


def delete_backup(name: str) -> bool:
    """Delete a backup from SQLite and filesystem."""
    with connect() as conn:
        row = conn.execute("SELECT path FROM backups WHERE name = ?", (name,)).fetchone()
        if not row:
            return False
        backup_path = Path(row["path"])
        if backup_path.exists():
            backup_path.unlink()
        conn.execute("DELETE FROM backups WHERE name = ?", (name,))

    audit_log("system", "backup.delete", "ok", {"name": name})
    return True


def restore_backup(name: str) -> dict[str, Any]:
    """Restore a backup from SQLite metadata."""
    backups = list_backups()
    backup = backups.get(name)
    if not backup:
        raise ValueError(f"backup not found: {name}")

    archive_path = Path(backup["path"])
    if not archive_path.exists():
        raise ValueError(f"backup archive missing: {archive_path}")

    from .. import core
    restore_dir = core.CACHE_DIR / f"restore-{name}-{datetime.now(timezone.utc).replace(tzinfo=None).strftime('%Y%m%d%H%M%S')}"
    restore_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(archive_path, "r") as archive:
        archive.extractall(restore_dir)

    restored_config = restore_dir / "config.json"
    if restored_config.exists():
        shutil.copy2(restored_config, core.CONFIG_FILE)

    audit_log("system", "backup.restore", "ok", {"name": name})
    return {"name": name, "restored_from": str(archive_path)}
