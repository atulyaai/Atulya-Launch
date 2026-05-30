"""SSL auto-renewal API — certbot cron management."""

import datetime
from fastapi import APIRouter, Depends, HTTPException

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/ssl/autorenew", tags=["ssl-autorenew"])

AUTORENEW_FILE = utils.CONFIG_DIR / "ssl_autorenew.json"


def _load_autorenew() -> dict:
    if AUTORENEW_FILE.exists():
        import json
        return json.loads(AUTORENEW_FILE.read_text())
    return {"enabled": False, "cron_installed": False, "last_check": None}


def _save_autorenew(data: dict):
    AUTORENEW_FILE.parent.mkdir(parents=True, exist_ok=True)
    import json
    AUTORENEW_FILE.write_text(json.dumps(data, indent=2))


def _is_certbot_available() -> bool:
    result = utils.run_command(["which", "certbot"], check=False)
    return result is not None and result.returncode == 0


def _cron_entry_exists() -> bool:
    result = utils.run_command(["crontab", "-l"], check=False)
    if not result or result.returncode != 0:
        return False
    return "certbot renew" in result.stdout


def _add_cron_entry():
    script_content = "#!/bin/bash\ncertbot renew --quiet --deploy-hook 'systemctl reload nginx'\n"
    hook_path = utils.CONFIG_DIR / "scripts" / "certbot-renew.sh"
    hook_path.parent.mkdir(parents=True, exist_ok=True)
    hook_path.write_text(script_content)
    hook_path.chmod(0o755)
    cron_line = f"0 3 * * * {hook_path}"
    temp_cron = utils.CONFIG_DIR / "temp_cron"
    utils.run_command(
        f"crontab -l > {temp_cron} 2>/dev/null; echo '{cron_line}' >> {temp_cron}; crontab {temp_cron}",
        check=False,
    )


def _remove_cron_entry():
    result = utils.run_command(["crontab", "-l"], check=False)
    if not result or result.returncode != 0:
        return
    lines = result.stdout.splitlines()
    filtered = [l for l in lines if "certbot renew" not in l and "certbot-renew.sh" not in l]
    temp_cron = utils.CONFIG_DIR / "temp_cron_filtered"
    temp_cron.write_text("\n".join(filtered) + "\n")
    utils.run_command(["crontab", str(temp_cron)], check=False)
    temp_cron.unlink(missing_ok=True)


@router.get("/status")
def get_status(user: dict = Depends(get_current_user)):
    data = _load_autorenew()
    certbot = _is_certbot_available()
    cron_active = _cron_entry_exists()
    certs = utils.load_config().get("ssl", {})
    return {
        "enabled": data.get("enabled", False),
        "certbot_available": certbot,
        "cron_installed": cron_active,
        "certificates_count": len(certs),
        "last_check": data.get("last_check"),
    }


@router.post("/enable")
def enable_autorenew(user: dict = Depends(get_current_user)):
    if not utils.is_linux():
        raise HTTPException(status_code=400, detail="Auto-renewal is only supported on Linux")
    if not _is_certbot_available():
        raise HTTPException(status_code=400, detail="certbot is not installed")
    _add_cron_entry()
    data = _load_autorenew()
    data["enabled"] = True
    data["cron_installed"] = True
    data["last_check"] = datetime.datetime.now().isoformat()
    _save_autorenew(data)
    return {"status": "enabled", "cron": "0 3 * * * certbot renew"}


@router.post("/disable")
def disable_autorenew(user: dict = Depends(get_current_user)):
    _remove_cron_entry()
    data = _load_autorenew()
    data["enabled"] = False
    data["cron_installed"] = False
    _save_autorenew(data)
    return {"status": "disabled"}


@router.post("/trigger")
def trigger_renewal(user: dict = Depends(get_current_user)):
    if not _is_certbot_available():
        raise HTTPException(status_code=400, detail="certbot is not installed")
    result = utils.run_command(["certbot", "renew", "--non-interactive"], check=False, timeout=120)
    success = result is not None and result.returncode == 0
    data = _load_autorenew()
    data["last_check"] = datetime.datetime.now().isoformat()
    data["last_result"] = "success" if success else "failed"
    _save_autorenew(data)
    if not success:
        detail = result.stderr if result else "Renewal command failed"
        raise HTTPException(status_code=500, detail=detail)
    return {"status": "renewed", "output": result.stdout if result else ""}
