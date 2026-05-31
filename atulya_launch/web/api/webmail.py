"""Webmail (Roundcube) management API."""

from fastapi import APIRouter, Depends
from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/webmail", tags=["webmail"])


def _is_roundcube_installed():
    import os
    return os.path.exists("/var/lib/roundcube") or os.path.exists("/usr/share/roundcube")


@router.get("/status")
def webmail_status(user: dict = Depends(get_current_user)):
    installed = _is_roundcube_installed()
    config_path = "/etc/roundcube/config.inc.php" if utils.is_linux() else None
    config_exists = config_path and __import__("os").path.exists(config_path) if config_path else False
    return {
        "installed": installed,
        "config_exists": config_exists,
        "url": "/webmail" if installed else None,
    }


@router.post("/install")
def install_roundcube(user: dict = Depends(get_current_user)):
    if not utils.is_linux():
        return {"status": "skipped", "note": "Roundcube installation only on Linux"}
    if _is_roundcube_installed():
        return {"status": "already_installed"}
    utils.run_command(["apt-get", "install", "-y", "roundcube", "roundcube-pgsql"], check=False)
    return {"status": "installed", "url": "/webmail"}


@router.get("/config")
def get_config(user: dict = Depends(get_current_user)):
    if not utils.is_linux():
        return {"config": {}}
    config_path = "/etc/roundcube/config.inc.php"
    import os
    if not os.path.exists(config_path):
        return {"config": {}}
    try:
        with open(config_path, "r") as f:
            content = f.read()
        return {"config_path": config_path, "size": len(content)}
    except Exception:
        return {"config": {}}
