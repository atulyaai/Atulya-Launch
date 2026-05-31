"""Flash message helpers backed by SQLite."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from starlette.requests import Request

from .database import connect


def add_flash(session_token: str | None, message: str, category: str = "info") -> None:
    """Store a flash message for a session."""
    if not session_token or not message:
        return
    with connect() as conn:
        conn.execute(
            "INSERT INTO flash_messages (session_token, category, message, created_at) VALUES (?, ?, ?, ?)",
            (session_token, category, message, datetime.utcnow().isoformat() + "Z"),
        )


def pop_flashes(session_token: str | None) -> list[dict[str, Any]]:
    """Return and delete all flash messages for a session."""
    if not session_token:
        return []
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, category, message, created_at FROM flash_messages WHERE session_token = ? ORDER BY id",
            (session_token,),
        ).fetchall()
        if rows:
            conn.execute(
                "DELETE FROM flash_messages WHERE id IN (%s)" % ",".join("?" for _ in rows),
                [row["id"] for row in rows],
            )
    return [dict(row) for row in rows]


def request_flashes(request: Request) -> list[dict[str, Any]]:
    """Template helper that pops flash messages for the current request."""
    cached = getattr(request.state, "_flashes", None)
    if cached is not None:
        return cached
    token = request.cookies.get("session_token")
    flashes = pop_flashes(token)
    request.state._flashes = flashes
    return flashes
