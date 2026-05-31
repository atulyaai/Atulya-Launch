"""Authentication and session management for Atulya Launch.

Provides password hashing, user creation, login/logout, session tokens,
account lockout, and auth decorators for route protection.
"""

import os
import hashlib
import base64
import secrets
import time
from datetime import datetime, timedelta
from functools import wraps
from collections import defaultdict
from typing import Any, Callable

from starlette.requests import Request
from starlette.responses import RedirectResponse, JSONResponse

from ..web.database import connect, audit_log


PASSWORD_MIN_LENGTH: int = int(os.environ.get("PANEL_PASSWORD_MIN_LENGTH", "8"))


def validate_password_policy(password: str) -> list[str]:
    """Validate password against minimum length, upper, lower, and digit rules."""
    errors: list[str] = []
    if len(password) < PASSWORD_MIN_LENGTH:
        errors.append(f"must be at least {PASSWORD_MIN_LENGTH} characters")
    if not any(c.isupper() for c in password):
        errors.append("must contain an uppercase letter")
    if not any(c.islower() for c in password):
        errors.append("must contain a lowercase letter")
    if not any(c.isdigit() for c in password):
        errors.append("must contain a digit")
    return errors


_attempts: dict[str, list[float]] = defaultdict(list)


def _check_lockout(username: str) -> bool:
    """Check if the username is currently locked out due to too many attempts."""
    now: float = time.time()
    _attempts[username] = [t for t in _attempts[username] if now - t < 900]
    return len(_attempts[username]) >= 10


def _record_attempt(username: str) -> None:
    """Record a failed login attempt for the given username."""
    _attempts[username].append(time.time())


def _reset_attempts(username: str) -> None:
    """Clear all recorded login attempts for the given username."""
    _attempts[username] = []


def hash_password(password: str, salt: bytes | None = None) -> str:
    """Hash a password using PBKDF2-SHA256 with a random salt."""
    salt_bytes: bytes = salt if salt is not None else secrets.token_bytes(16)
    digest: bytes = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, 200_000)
    salt_text: str = base64.urlsafe_b64encode(salt_bytes).decode("ascii")
    digest_text: str = base64.urlsafe_b64encode(digest).decode("ascii")
    return f"pbkdf2_sha256$200000${salt_text}${digest_text}"


def verify_password(password: str, encoded: str) -> bool:
    """Verify a password against a PBKDF2-SHA256 hash string."""
    try:
        algorithm: str
        rounds: str
        salt_text: str
        digest_text: str
        algorithm, rounds, salt_text, digest_text = encoded.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        salt: bytes = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected: bytes = base64.urlsafe_b64decode(digest_text.encode("ascii"))
        actual: bytes = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(rounds))
        return secrets.compare_digest(actual, expected)
    except Exception:
        return False


def create_user(username: str, password: str, role: str = "admin", skip_policy: bool = False) -> None:
    """Create a new user with the given username, password, and role."""
    from .database import connect
    if not skip_policy:
        pw_errors: list[str] = validate_password_policy(password)
        if pw_errors:
            raise ValueError(f"Password policy: {'; '.join(pw_errors)}")
    pw_hash: str = hash_password(password)
    with connect() as cur:
        try:
            cur.execute(
                "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
                (username, pw_hash, role, datetime.utcnow().isoformat() + "Z"),
            )
        except Exception as e:
            if "UNIQUE" in str(e):
                raise ValueError(f"username already exists: {username}")
            raise


def authenticate(username: str, password: str) -> dict | None:
    """Authenticate a user; return a session dict with token or None on failure."""
    if not username or not password:
        return None
    if _check_lockout(username):
        audit_log(username, "auth.login", "denied", {"reason": "locked_out"})
        return None
    with connect() as cur:
        row: Any = cur.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if not row:
            _record_attempt(username)
            audit_log(username, "auth.login", "denied", {"reason": "unknown_user"})
            return None
        if not verify_password(password, row["password_hash"]):
            _record_attempt(username)
            audit_log(username, "auth.login", "denied", {"reason": "bad_password"})
            return None
        _reset_attempts(username)

        max_sessions: int = int(os.environ.get("PANEL_MAX_SESSIONS", "5"))
        sessions: list[Any] = cur.execute(
            "SELECT token FROM sessions WHERE user_id = ? AND expires_at > ? ORDER BY created_at ASC",
            (row["id"], datetime.utcnow().isoformat() + "Z"),
        ).fetchall()
        if len(sessions) >= max_sessions:
            cur.execute("DELETE FROM sessions WHERE token = ?", (sessions[0]["token"],))

        token: str = secrets.token_urlsafe(32)
        expires: str = (datetime.utcnow() + timedelta(hours=24)).isoformat() + "Z"
        cur.execute(
            "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, row["id"], datetime.utcnow().isoformat() + "Z", expires),
        )
        cur.execute("UPDATE users SET last_login = ? WHERE id = ?", (datetime.utcnow().isoformat() + "Z", row["id"]))
        user_data: dict = dict(row)
    audit_log(username, "auth.login", "ok")
    return {"token": token, "user": user_data, "expires": expires}


def validate_session(token: str | None) -> dict | None:
    """Validate a session token and return the session data, or None."""
    if not token:
        return None
    with connect() as cur:
        row: Any = cur.execute(
            "SELECT s.*, u.username, u.role FROM sessions s JOIN users u ON s.user_id = u.id WHERE s.token = ? AND s.expires_at > ?",
            (token, datetime.utcnow().isoformat() + "Z"),
        ).fetchone()
        if row:
            return dict(row)
    return None


def destroy_session(token: str | None) -> None:
    """Delete a session token from the database."""
    if not token:
        return
    with connect() as cur:
        cur.execute("DELETE FROM sessions WHERE token = ?", (token,))


def destroy_all_user_sessions(user_id: int) -> None:
    """Delete all sessions belonging to the given user."""
    with connect() as cur:
        cur.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))


def get_current_user(request: Request) -> dict | None:
    """Extract the current user from cookie or Bearer token."""
    token: str | None = request.cookies.get("session_token")
    if not token:
        auth_header: str = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    return validate_session(token)


_partial_sessions: dict[str, dict] = {}


def create_partial_session(username: str) -> str:
    """Create a temporary partial session token for 2FA challenge."""
    token: str = secrets.token_urlsafe(32)
    expires: float = time.time() + 300
    _partial_sessions[token] = {"username": username, "expires": expires}
    return token


def validate_partial_session(token: str | None) -> str | None:
    """Validate a partial session token and return the associated username."""
    if not token:
        return None
    data: dict | None = _partial_sessions.get(token)
    if not data:
        return None
    if time.time() > data["expires"]:
        _partial_sessions.pop(token, None)
        return None
    return data["username"]


def destroy_partial_session(token: str) -> None:
    """Remove a partial session token."""
    _partial_sessions.pop(token, None)


def cleanup_expired_partial_sessions() -> None:
    """Remove all expired partial session tokens."""
    now: float = time.time()
    expired: list[str] = [k for k, v in _partial_sessions.items() if now > v["expires"]]
    for k in expired:
        _partial_sessions.pop(k, None)


def require_auth(handler: Callable) -> Callable:
    """Decorator that requires a valid user session."""
    @wraps(handler)
    async def wrapper(request: Request, *args: Any, **kwargs: Any) -> Any:
        user: dict | None = get_current_user(request)
        if not user:
            if request.url.path.startswith("/api/"):
                return JSONResponse({"error": "unauthorized"}, status_code=401)
            return RedirectResponse("/login", status_code=302)
        request.state.user = user
        return await handler(request, *args, **kwargs)
    return wrapper


def require_admin(handler: Callable) -> Callable:
    """Decorator that requires an admin role session."""
    @wraps(handler)
    async def wrapper(request: Request, *args: Any, **kwargs: Any) -> Any:
        user: dict | None = get_current_user(request)
        if not user:
            if request.url.path.startswith("/api/"):
                return JSONResponse({"error": "unauthorized"}, status_code=401)
            return RedirectResponse("/login", status_code=302)
        if user.get("role") != "admin":
            if request.url.path.startswith("/api/"):
                return JSONResponse({"error": "forbidden"}, status_code=403)
            return RedirectResponse("/dashboard", status_code=302)
        request.state.user = user
        return await handler(request, *args, **kwargs)
    return wrapper


def require_reseller(handler: Callable) -> Callable:
    """Decorator that requires admin or reseller role."""
    @wraps(handler)
    async def wrapper(request: Request, *args: Any, **kwargs: Any) -> Any:
        user: dict | None = get_current_user(request)
        if not user:
            if request.url.path.startswith("/api/"):
                return JSONResponse({"error": "unauthorized"}, status_code=401)
            return RedirectResponse("/login", status_code=302)
        if user.get("role") not in ("admin", "reseller"):
            if request.url.path.startswith("/api/"):
                return JSONResponse({"error": "forbidden"}, status_code=403)
            return RedirectResponse("/dashboard", status_code=302)
        request.state.user = user
        return await handler(request, *args, **kwargs)
    return wrapper
