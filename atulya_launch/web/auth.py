"""JWT authentication system for Atulya-Launch web panel."""

import secrets
import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from atulya_launch import utils

router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer()

SECRET_KEY: Optional[str] = None
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24
CONFIG_KEY = "web.auth"


def _load_secret_key() -> str:
    global SECRET_KEY
    if SECRET_KEY is not None:
        return SECRET_KEY
    config = utils.load_config()
    auth_cfg = config.get("web", {}).get("auth", {})
    stored = auth_cfg.get("secret_key")
    if stored:
        SECRET_KEY = stored
        return SECRET_KEY
    SECRET_KEY = secrets.token_hex(32)
    auth_cfg["secret_key"] = SECRET_KEY
    web_cfg = config.get("web", {})
    web_cfg["auth"] = auth_cfg
    config["web"] = web_cfg
    utils.save_config(config)
    return SECRET_KEY


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = ACCESS_TOKEN_EXPIRE_HOURS * 3600


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


def _ensure_admin_user() -> None:
    config = utils.load_config()
    auth_cfg = config.get("web", {}).get("auth", {})
    if not auth_cfg.get("admin_user"):
        default_password = utils.generate_password(16)
        auth_cfg["admin_user"] = "admin"
        auth_cfg["admin_password_hash"] = pwd_context.hash(default_password)
        web_cfg = config.get("web", {})
        web_cfg["auth"] = auth_cfg
        config["web"] = web_cfg
        utils.save_config(config)
        print(f"[atulya-launch] Generated admin credentials — user: admin  password: {default_password}")


def create_access_token(data: dict, expires_delta: Optional[datetime.timedelta] = None) -> str:
    secret = _load_secret_key()
    to_encode = data.copy()
    expire = datetime.datetime.now(datetime.timezone.utc) + (expires_delta or datetime.timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS))
    to_encode.update({"exp": expire, "iat": datetime.datetime.now(datetime.timezone.utc)})
    return jwt.encode(to_encode, secret, algorithm=ALGORITHM)


def verify_token(token: str) -> dict:
    secret = _load_secret_key()
    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    return verify_token(credentials.credentials)


def _verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def _hash_password(password: str) -> str:
    return pwd_context.hash(password)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest):
    """Authenticate and return a JWT token."""
    _ensure_admin_user()
    config = utils.load_config()
    auth_cfg = config.get("web", {}).get("auth", {})
    admin_user = auth_cfg.get("admin_user", "admin")
    admin_hash = auth_cfg.get("admin_password_hash", "")

    if body.username != admin_user or not _verify_password(body.password, admin_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_access_token({"sub": body.username})
    return TokenResponse(access_token=token)


@router.get("/me")
def get_me(user: dict = Depends(get_current_user)):
    """Return current authenticated user info."""
    return {"username": user.get("sub"), "expires_at": user.get("exp")}


@router.post("/change-password")
def change_password(body: ChangePasswordRequest, user: dict = Depends(get_current_user)):
    """Change the admin password."""
    config = utils.load_config()
    auth_cfg = config.get("web", {}).get("auth", {})
    admin_hash = auth_cfg.get("admin_password_hash", "")

    if not _verify_password(body.current_password, admin_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")

    auth_cfg["admin_password_hash"] = _hash_password(body.new_password)
    web_cfg = config.get("web", {})
    web_cfg["auth"] = auth_cfg
    config["web"] = web_cfg
    utils.save_config(config)
    return {"status": "password changed"}


def init_auth():
    """Initialise auth module: load secret key, ensure admin user exists."""
    _load_secret_key()
    _ensure_admin_user()
