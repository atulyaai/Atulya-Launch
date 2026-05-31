"""Security Advisor - Automated security scanning and scoring."""

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/security-advisor", tags=["security-advisor"])

ADVISOR_DIR = utils.CONFIG_DIR / "security-advisor"
RESULT_FILE = ADVISOR_DIR / "last_scan.json"
CONFIG_FILE = ADVISOR_DIR / "config.json"


def _ensure_dirs():
    ADVISOR_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(json.dumps({
            "auto_scan_enabled": True,
            "scan_interval_hours": 24,
            "last_scan": None,
        }, indent=2))


def _load_config() -> dict:
    _ensure_dirs()
    return json.loads(CONFIG_FILE.read_text())


def _save_config(data: dict):
    _ensure_dirs()
    CONFIG_FILE.write_text(json.dumps(data, indent=2))


def _load_result() -> dict:
    _ensure_dirs()
    if RESULT_FILE.exists():
        return json.loads(RESULT_FILE.read_text())
    return {}


def _save_result(data: dict):
    _ensure_dirs()
    RESULT_FILE.write_text(json.dumps(data, indent=2))


class SecurityCheck:
    def __init__(self, name: str, category: str, description: str, severity: str = "info"):
        self.name = name
        self.category = category
        self.description = description
        self.severity = severity
        self.status = "unknown"
        self.details = ""
        self.fix = ""
        self.score_impact = 0


def _check_ssh_config() -> SecurityCheck:
    check = SecurityCheck(
        name="SSH Configuration",
        category="access",
        description="Check SSH daemon security settings",
        severity="high",
    )
    sshd_config = Path("/etc/ssh/sshd_config")
    if not sshd_config.exists():
        check.status = "skip"
        check.details = "SSH config not found (non-Linux or SSH not installed)"
        return check

    content = sshd_config.read_text()
    issues = []

    if "PermitRootLogin yes" in content:
        issues.append("Root login is permitted")
        check.score_impact -= 15

    if "PasswordAuthentication yes" in content or "PasswordAuthentication" not in content:
        issues.append("Password authentication is enabled (recommend key-only)")
        check.score_impact -= 5

    if "X11Forwarding yes" in content:
        issues.append("X11 forwarding is enabled")
        check.score_impact -= 3

    if "Protocol 1" in content:
        issues.append("Insecure SSH Protocol 1 is enabled")
        check.score_impact -= 20

    if not issues:
        check.status = "pass"
        check.details = "SSH configuration looks secure"
        check.score_impact = 5
    else:
        check.status = "fail"
        check.details = "; ".join(issues)
        check.fix = "Edit /etc/ssh/sshd_config and set: PermitRootLogin no, PasswordAuthentication no, X11Forwarding no, then run: systemctl restart sshd"

    return check


def _check_firewall() -> SecurityCheck:
    check = SecurityCheck(
        name="Firewall Status",
        category="network",
        description="Verify firewall is active and configured",
        severity="high",
    )
    if not utils.is_linux():
        check.status = "skip"
        check.details = "Firewall check only available on Linux"
        return check

    result = utils.run_command(["ufw", "status"], check=False)
    if result and hasattr(result, 'stdout') and "active" in (result.stdout or "").lower():
        check.status = "pass"
        check.details = "UFW firewall is active"
        check.score_impact = 10
    else:
        result2 = utils.run_command(["firewall-cmd", "--state"], check=False)
        if result2 and hasattr(result2, 'stdout') and "running" in (result2.stdout or "").lower():
            check.status = "pass"
            check.details = "firewalld is active"
            check.score_impact = 10
        else:
            check.status = "fail"
            check.details = "No active firewall detected"
            check.fix = "Run: ufw enable (Ubuntu) or systemctl enable --now firewalld (CentOS/RHEL)"
            check.score_impact = -20

    return check


def _check_fail2ban() -> SecurityCheck:
    check = SecurityCheck(
        name="Fail2ban Protection",
        category="access",
        description="Verify Fail2ban is running and protecting services",
        severity="high",
    )
    if not utils.is_linux():
        check.status = "skip"
        check.details = "Fail2ban check only available on Linux"
        return check

    result = utils.run_command(["systemctl", "is-active", "fail2ban"], check=False)
    if result and hasattr(result, 'returncode') and result.returncode == 0:
        jails = utils.run_command(["fail2ban-client", "status"], check=False)
        jail_count = 0
        banned_count = 0
        if jails and hasattr(jails, 'stdout') and jails.stdout:
            for line in jails.stdout.split('\n'):
                if 'Jail list' in line:
                    jail_count = len(line.split(':')[-1].split(','))
                if 'Currently banned' in line:
                    try:
                        banned_count = int(line.split(':')[-1].strip())
                    except ValueError:
                        pass
        check.status = "pass"
        check.details = f"Fail2ban active with {jail_count} jails, {banned_count} IPs currently banned"
        check.score_impact = 10
    else:
        check.status = "fail"
        check.details = "Fail2ban is not running"
        check.fix = "Run: apt install fail2ban && systemctl enable --now fail2ban"
        check.score_impact = -15

    return check


def _check_ssl_certs() -> SecurityCheck:
    check = SecurityCheck(
        name="SSL Certificates",
        category="encryption",
        description="Check for expired or soon-to-expire SSL certificates",
        severity="medium",
    )
    if not utils.is_linux():
        check.status = "skip"
        check.details = "SSL check only available on Linux"
        return check

    certs_dir = Path("/etc/letsencrypt/live")
    if not certs_dir.exists():
        check.status = "info"
        check.details = "No Let's Encrypt certificates found"
        check.score_impact = 0
        return check

    expiring = []
    for domain_dir in certs_dir.iterdir():
        cert = domain_dir / "fullchain.pem"
        if cert.exists():
            result = utils.run_command(
                ["openssl", "x509", "-enddate", "-noout", "-in", str(cert)],
                check=False,
            )
            if result and hasattr(result, 'stdout') and result.stdout:
                try:
                    date_str = result.stdout.strip().replace("notAfter=", "")
                    from email.utils import parsedate_to_datetime
                    expiry = parsedate_to_datetime(date_str)
                    from datetime import timezone
                    days_left = (expiry.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)).days
                    if days_left < 30:
                        expiring.append(f"{domain_dir.name}: {days_left} days left")
                except Exception:
                    pass

    if expiring:
        check.status = "fail"
        check.details = f"Expiring soon: {'; '.join(expiring)}"
        check.fix = "Run: certbot renew --force-renewal"
        check.score_impact = -10
    else:
        check.status = "pass"
        check.details = "All SSL certificates are valid"
        check.score_impact = 5

    return check


def _check_password_policy() -> SecurityCheck:
    check = SecurityCheck(
        name="Password Policy",
        category="access",
        description="Check if strong password policy is enforced",
        severity="medium",
    )
    config = utils.load_config()
    policy = config.get("security", {}).get("password_policy", {})
    min_length = policy.get("min_length", 8)
    require_complex = policy.get("require_complexity", False)

    issues = []
    if min_length < 12:
        issues.append(f"Minimum password length is {min_length} (recommended: 12+)")
        check.score_impact -= 5
    if not require_complexity:
        issues.append("Password complexity requirements not enforced")
        check.score_impact -= 5

    if not issues:
        check.status = "pass"
        check.details = f"Password policy enforced (min length: {min_length})"
        check.score_impact = 5
    else:
        check.status = "warn"
        check.details = "; ".join(issues)
        check.fix = "Update password policy in Security settings"

    return check


def _check_auto_updates() -> SecurityCheck:
    check = SecurityCheck(
        name="Automatic Security Updates",
        category="system",
        description="Verify automatic security updates are configured",
        severity="medium",
    )
    if not utils.is_linux():
        check.status = "skip"
        check.details = "Auto-update check only available on Linux"
        return check

    unattended = Path("/etc/apt/apt.conf.d/20auto-upgrades")
    if unattended.exists():
        content = unattended.read_text()
        if '"1"' in content:
            check.status = "pass"
            check.details = "Automatic security updates are enabled"
            check.score_impact = 10
            return check

    check.status = "fail"
    check.details = "Automatic security updates are not configured"
    check.fix = "Run: apt install unattended-upgrades && dpkg-reconfigure -plow unattended-upgrades"
    check.score_impact = -10
    return check


def _check_disk_usage() -> SecurityCheck:
    check = SecurityCheck(
        name="Disk Usage",
        category="system",
        description="Check if disk usage is critically high",
        severity="medium",
    )
    try:
        import psutil
        usage = psutil.disk_usage("/")
        percent = usage.percent
        if percent > 90:
            check.status = "fail"
            check.details = f"Disk usage is at {percent}% (critical)"
            check.fix = "Free disk space or expand volume"
            check.score_impact = -15
        elif percent > 80:
            check.status = "warn"
            check.details = f"Disk usage is at {percent}% (warning)"
            check.fix = "Consider freeing disk space"
            check.score_impact = -5
        else:
            check.status = "pass"
            check.details = f"Disk usage is at {percent}% (healthy)"
            check.score_impact = 5
    except ImportError:
        check.status = "skip"
        check.details = "psutil not available"
    return check


def _check_log_exposure() -> SecurityCheck:
    check = SecurityCheck(
        name="Sensitive Log Exposure",
        category="files",
        description="Check if sensitive log files are publicly accessible",
        severity="high",
    )
    if not utils.is_linux():
        check.status = "skip"
        check.details = "Log exposure check only available on Linux"
        return check

    sites = utils.CONFIG_DIR / "sites"
    exposed = []
    if sites.exists():
        for site_dir in sites.iterdir():
            public = site_dir / "public_html"
            if public.exists():
                for log_name in [".env", "wp-config.php", "config.php", "database.yml"]:
                    log_file = public / log_name
                    if log_file.exists():
                        exposed.append(f"{site_dir.name}/{log_name}")

    if exposed:
        check.status = "fail"
        check.details = f"Sensitive files publicly accessible: {', '.join(exposed)}"
        check.fix = "Move these files outside the public_html directory or add deny rules in .htaccess/nginx config"
        check.score_impact = -20
    else:
        check.status = "pass"
        check.details = "No sensitive files found in public directories"
        check.score_impact = 5

    return check


ALL_CHECKS = [
    _check_ssh_config,
    _check_firewall,
    _check_fail2ban,
    _check_ssl_certs,
    _check_password_policy,
    _check_auto_updates,
    _check_disk_usage,
    _check_log_exposure,
]


@router.post("/scan")
def run_scan(user: dict = Depends(get_current_user)):
    results = []
    total_score = 100
    for check_fn in ALL_CHECKS:
        try:
            check = check_fn()
            results.append({
                "name": check.name,
                "category": check.category,
                "description": check.description,
                "severity": check.severity,
                "status": check.status,
                "details": check.details,
                "fix": check.fix,
                "score_impact": check.score_impact,
            })
            total_score += check.score_impact
        except Exception as e:
            results.append({
                "name": check_fn.__name__,
                "category": "error",
                "description": f"Check failed: {str(e)}",
                "severity": "info",
                "status": "error",
                "details": str(e),
                "fix": "",
                "score_impact": 0,
            })

    total_score = max(0, min(100, total_score))

    pass_count = sum(1 for r in results if r["status"] == "pass")
    fail_count = sum(1 for r in results if r["status"] == "fail")
    warn_count = sum(1 for r in results if r["status"] == "warn")

    scan_result = {
        "score": total_score,
        "grade": "A" if total_score >= 90 else "B" if total_score >= 75 else "C" if total_score >= 60 else "D" if total_score >= 40 else "F",
        "checks": results,
        "summary": {
            "total": len(results),
            "pass": pass_count,
            "fail": fail_count,
            "warn": warn_count,
            "skip": sum(1 for r in results if r["status"] == "skip"),
        },
        "scanned_at": datetime.now().isoformat(),
    }

    _save_result(scan_result)
    _ensure_dirs()
    config = _load_config()
    config["last_scan"] = datetime.now().isoformat()
    _save_config(config)

    return scan_result


@router.get("/results")
def get_results(user: dict = Depends(get_current_user)):
    result = _load_result()
    if not result:
        return {"message": "No scan results yet. Run a scan first.", "score": None}
    return result


@router.get("/config")
def get_advisor_config(user: dict = Depends(get_current_user)):
    return _load_config()


@router.post("/config")
def update_advisor_config(body: dict, user: dict = Depends(get_current_user)):
    config = _load_config()
    config.update(body)
    _save_config(config)
    return {"status": "updated", "config": config}


@router.get("/summary")
def get_summary(user: dict = Depends(get_current_user)):
    result = _load_result()
    if not result:
        return {"score": None, "grade": "N/A", "message": "No scan performed yet"}

    categories = {}
    for check in result.get("checks", []):
        cat = check["category"]
        if cat not in categories:
            categories[cat] = {"pass": 0, "fail": 0, "warn": 0, "total": 0}
        categories[cat]["total"] += 1
        if check["status"] == "pass":
            categories[cat]["pass"] += 1
        elif check["status"] == "fail":
            categories[cat]["fail"] += 1
        elif check["status"] == "warn":
            categories[cat]["warn"] += 1

    return {
        "score": result.get("score"),
        "grade": result.get("grade"),
        "last_scan": result.get("scanned_at"),
        "categories": categories,
    }
