import hashlib
import hmac
import base64
import secrets
from datetime import datetime, timedelta
from functools import wraps

from starlette.requests import Request
from starlette.responses import RedirectResponse, JSONResponse

from ..web.database import connect, audit_log


def hash_password(password, salt=None):
    salt_bytes = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, 200_000)
    salt_text = base64.urlsafe_b64encode(salt_bytes).decode("ascii")
    digest_text = base64.urlsafe_b64encode(digest).decode("ascii")
    return f"pbkdf2_sha256$200000${salt_text}${digest_text}"


def verify_password(password, encoded):
    try:
        algorithm, rounds, salt_text, digest_text = encoded.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(rounds))
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def create_user(username, password, role="admin"):
    from .database import connect
    pw_hash = hash_password(password)
    with connect() as cur:
        cur.execute(
            "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            (username, pw_hash, role, datetime.utcnow().isoformat() + "Z"),
        )


def authenticate(username, password):
    with connect() as cur:
        row = cur.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if not row:
            audit_log(username, "auth.login", "denied", {"reason": "unknown_user"})
            return None
        if not verify_password(password, row["password_hash"]):
            audit_log(username, "auth.login", "denied", {"reason": "bad_password"})
            return None
        token = secrets.token_urlsafe(32)
        expires = (datetime.utcnow() + timedelta(hours=24)).isoformat() + "Z"
        cur.execute(
            "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, row["id"], datetime.utcnow().isoformat() + "Z", expires),
        )
        cur.execute("UPDATE users SET last_login = ? WHERE id = ?", (datetime.utcnow().isoformat() + "Z", row["id"]))
        user_data = dict(row)
    audit_log(username, "auth.login", "ok")
    return {"token": token, "user": user_data, "expires": expires}


def validate_session(token):
    if not token:
        return None
    with connect() as cur:
        row = cur.execute(
            "SELECT s.*, u.username, u.role FROM sessions s JOIN users u ON s.user_id = u.id WHERE s.token = ? AND s.expires_at > ?",
            (token, datetime.utcnow().isoformat() + "Z"),
        ).fetchone()
        if row:
            return dict(row)
    return None


def destroy_session(token):
    with connect() as cur:
        cur.execute("DELETE FROM sessions WHERE token = ?", (token,))


def get_current_user(request: Request):
    token = request.cookies.get("session_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    return validate_session(token)


def require_auth(handler):
    @wraps(handler)
    async def wrapper(request: Request, *args, **kwargs):
        user = get_current_user(request)
        if not user:
            if request.url.path.startswith("/api/"):
                return JSONResponse({"error": "unauthorized"}, status_code=401)
            return RedirectResponse("/login", status_code=302)
        request.state.user = user
        return await handler(request, *args, **kwargs)
    return wrapper


def require_admin(handler):
    @wraps(handler)
    async def wrapper(request: Request, *args, **kwargs):
        user = get_current_user(request)
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
