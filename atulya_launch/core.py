import os
import re
import sys
import json
import hashlib
import zipfile
import tarfile
import tempfile
import shutil
import subprocess
import platform
import time
import secrets
import hmac
import base64
from pathlib import Path
from importlib import metadata
from datetime import datetime

import requests


def _default_config_dir():
    configured = os.environ.get("ATULYA_HOME")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".atulya"


CONFIG_DIR = _default_config_dir()
CONFIG_FILE = CONFIG_DIR / "config.json"
TOOLS_DIR = CONFIG_DIR / "tools"
CACHE_DIR = CONFIG_DIR / "cache"
SITES_DIR = CONFIG_DIR / "sites"
WEBROOTS_DIR = CONFIG_DIR / "webroots"
BACKUPS_DIR = CONFIG_DIR / "backups"
NGINX_DIR = CONFIG_DIR / "nginx"
LOGS_DIR = CONFIG_DIR / "logs"
AUDIT_LOG = LOGS_DIR / "audit.jsonl"

ATULYA_ORG = "atulyaai"


def _set_config_dir(config_dir):
    global CONFIG_DIR, CONFIG_FILE, TOOLS_DIR, CACHE_DIR
    global SITES_DIR, WEBROOTS_DIR, BACKUPS_DIR, NGINX_DIR, LOGS_DIR, AUDIT_LOG
    CONFIG_DIR = Path(config_dir)
    CONFIG_FILE = CONFIG_DIR / "config.json"
    TOOLS_DIR = CONFIG_DIR / "tools"
    CACHE_DIR = CONFIG_DIR / "cache"
    SITES_DIR = CONFIG_DIR / "sites"
    WEBROOTS_DIR = CONFIG_DIR / "webroots"
    BACKUPS_DIR = CONFIG_DIR / "backups"
    NGINX_DIR = CONFIG_DIR / "nginx"
    LOGS_DIR = CONFIG_DIR / "logs"
    AUDIT_LOG = LOGS_DIR / "audit.jsonl"


def ensure_dirs():
    candidates = [CONFIG_DIR]
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        candidates.append(Path(local_appdata) / "Atulya" / "Launch")
    candidates.append(Path(tempfile.gettempdir()) / "atulya-launch")
    candidates.append(Path.cwd() / ".atulya")

    last_error = None
    for base_dir in candidates:
        try:
            for d in [
                base_dir,
                base_dir / "tools",
                base_dir / "cache",
                base_dir / "sites",
                base_dir / "webroots",
                base_dir / "backups",
                base_dir / "nginx",
                base_dir / "logs",
            ]:
                d.mkdir(parents=True, exist_ok=True)
            _set_config_dir(base_dir)
            return CONFIG_DIR
        except OSError as error:
            last_error = error

    raise last_error


def load_config():
    ensure_dirs()
    if not CONFIG_FILE.exists():
        return default_config()
    with open(CONFIG_FILE) as f:
        cfg = json.load(f)
    merged = default_config()
    merged.update(cfg)
    merged["panel"] = {**default_config()["panel"], **merged.get("panel", {})}
    merged["settings"] = {**default_config()["settings"], **merged.get("settings", {})}
    for key in ["installed", "sites", "backups", "settings"]:
        merged.setdefault(key, {})
    merged.setdefault("sessions", {})
    return merged


def save_config(cfg):
    ensure_dirs()
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


def default_config():
    return {
        "panel": {
            "name": "Atulya Launch",
            "version": "0.2.0",
            "created_at": None,
            "admin_user": "admin",
            "api_token": None,
            "password_hash": None,
        },
        "settings": {
            "bind_host": "127.0.0.1",
            "bind_port": 8080,
            "public_exposure": False,
        },
        "installed": {},
        "sites": {},
        "backups": {},
        "sessions": {},
        "updated_at": None,
    }


def panel_init(admin_user="admin", admin_password=None, rotate_token=False):
    cfg = load_config()
    panel = cfg.setdefault("panel", {})
    if not panel.get("created_at"):
        panel["created_at"] = datetime.utcnow().isoformat() + "Z"
    panel["admin_user"] = admin_user
    generated_password = None
    if admin_password:
        panel["password_hash"] = hash_password(admin_password)
    elif not panel.get("password_hash"):
        generated_password = secrets.token_urlsafe(18)
        panel["password_hash"] = hash_password(generated_password)
    if rotate_token or not panel.get("api_token"):
        panel["api_token"] = secrets.token_urlsafe(32)
    save_config(cfg)
    audit_event("panel.init", "ok", {"admin_user": admin_user, "rotated_token": rotate_token})
    return {
        "config_dir": str(CONFIG_DIR),
        "admin_user": admin_user,
        "api_token": panel["api_token"],
        "generated_password": generated_password,
    }


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


def login(username, password):
    cfg = load_config()
    panel = cfg.get("panel", {})
    if username != panel.get("admin_user") or not verify_password(password, panel.get("password_hash", "")):
        audit_event("auth.login", "denied", {"username": username})
        return None
    token = secrets.token_urlsafe(32)
    cfg.setdefault("sessions", {})[token] = {
        "username": username,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    save_config(cfg)
    audit_event("auth.login", "ok", {"username": username})
    return token


def validate_session(token):
    if not token:
        return False
    return token in load_config().get("sessions", {})


def audit_event(action, status, details=None):
    ensure_dirs()
    event = {
        "time": datetime.utcnow().isoformat() + "Z",
        "action": action,
        "status": status,
        "details": details or {},
    }
    with open(AUDIT_LOG, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")
    return event


def audit_list(limit=100):
    ensure_dirs()
    if not AUDIT_LOG.exists():
        return []
    lines = AUDIT_LOG.read_text(encoding="utf-8").splitlines()[-limit:]
    return [json.loads(line) for line in lines if line.strip()]


def get_api_token():
    cfg = load_config()
    token = cfg.get("panel", {}).get("api_token")
    if not token:
        token = panel_init()["api_token"]
    return token


def validate_domain(domain):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,251}[A-Za-z0-9]", domain):
        raise ValueError("domain must contain only letters, numbers, dots and hyphens")
    if ".." in domain or "." not in domain:
        raise ValueError("domain must look like a real hostname, e.g. example.com")
    return domain.lower()


def _safe_path(path, base_dir=None):
    base = Path(base_dir or CONFIG_DIR).resolve()
    candidate = Path(path).expanduser().resolve()
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"path must stay inside {base}") from exc
    return candidate


def site_create(domain, web_root=None, proxy_pass=None, php=False):
    domain = validate_domain(domain)
    cfg = load_config()
    if domain in cfg["sites"]:
        raise ValueError(f"site already exists: {domain}")

    if web_root:
        root = _safe_path(web_root, CONFIG_DIR)
    else:
        root = WEBROOTS_DIR / domain / "public"
    root.mkdir(parents=True, exist_ok=True)

    index_path = root / "index.html"
    if not index_path.exists():
        index_path.write_text(
            f"<!doctype html><title>{domain}</title><h1>{domain}</h1><p>Hosted by Atulya Launch.</p>\n",
            encoding="utf-8",
        )

    site = {
        "domain": domain,
        "web_root": str(root),
        "proxy_pass": proxy_pass,
        "php": bool(php),
        "enabled": True,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "nginx_config": str(generate_nginx_config(domain, root, proxy_pass, php)),
    }
    cfg["sites"][domain] = site
    cfg["updated_at"] = datetime.utcnow().isoformat() + "Z"
    save_config(cfg)
    audit_event("site.create", "ok", {"domain": domain})
    return site


def site_list():
    return load_config().get("sites", {})


def site_get(domain):
    return site_list().get(validate_domain(domain))


def site_delete(domain):
    domain = validate_domain(domain)
    cfg = load_config()
    site = cfg.get("sites", {}).pop(domain, None)
    if not site:
        return False
    config_path = Path(site.get("nginx_config", ""))
    if config_path.exists() and _is_within_directory(NGINX_DIR, config_path):
        config_path.unlink()
    cfg["updated_at"] = datetime.utcnow().isoformat() + "Z"
    save_config(cfg)
    audit_event("site.delete", "ok", {"domain": domain})
    return True


def generate_nginx_config(domain, web_root, proxy_pass=None, php=False):
    NGINX_DIR.mkdir(parents=True, exist_ok=True)
    config_path = NGINX_DIR / f"{domain}.conf"
    if proxy_pass:
        body = f"""server {{
    listen 80;
    server_name {domain};

    location / {{
        proxy_pass {proxy_pass};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
}}
"""
    else:
        php_block = ""
        if php:
            php_block = """
    location ~ \\.php$ {
        include snippets/fastcgi-php.conf;
        fastcgi_pass unix:/run/php/php-fpm.sock;
    }
"""
        body = f"""server {{
    listen 80;
    server_name {domain};
    root {Path(web_root)};
    index index.html index.htm index.php;

    location / {{
        try_files $uri $uri/ =404;
    }}
{php_block}}}
"""
    config_path.write_text(body, encoding="utf-8")
    return config_path


def system_status():
    ensure_dirs()
    disk = shutil.disk_usage(CONFIG_DIR)
    uptime = time.monotonic()
    memory = memory_status()
    return {
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "config_dir": str(CONFIG_DIR),
        "cpu_count": os.cpu_count() or 1,
        "memory": memory,
        "disk": {
            "total": disk.total,
            "used": disk.used,
            "free": disk.free,
            "percent": round((disk.used / disk.total) * 100, 1) if disk.total else 0,
        },
        "process_uptime_seconds": int(uptime),
        "sites": len(site_list()),
        "backups": len(load_config().get("backups", {})),
        "services": service_summary(),
    }


def memory_status():
    try:
        import psutil

        mem = psutil.virtual_memory()
        return {
            "total": mem.total,
            "used": mem.used,
            "available": mem.available,
            "percent": mem.percent,
        }
    except Exception:
        return {"total": None, "used": None, "available": None, "percent": None}


def service_summary():
    names = ["nginx", "apache2", "mariadb", "mysql", "postgresql", "redis-server", "ssh", "fail2ban"]
    return {name: service_state(name) for name in names}


def service_state(name):
    if get_platform() != "linux" or not shutil.which("systemctl"):
        return "unknown"
    result = subprocess.run(["systemctl", "is-active", name], capture_output=True, text=True, check=False)
    return result.stdout.strip() or "unknown"


def nginx_apply_plan(domain=None):
    sites = site_list()
    targets = [validate_domain(domain)] if domain else sorted(sites)
    planned = []
    for name in targets:
        site = sites.get(name)
        if not site:
            raise ValueError(f"site not found: {name}")
        source = Path(site["nginx_config"])
        planned.append(
            {
                "domain": name,
                "source": str(source),
                "target": f"/etc/nginx/sites-available/{name}.conf",
                "enabled_link": f"/etc/nginx/sites-enabled/{name}.conf",
                "test_command": "nginx -t",
                "reload_command": "systemctl reload nginx",
            }
        )
    return planned


def security_scan():
    cfg = load_config()
    issues = []
    settings = cfg.get("settings", {})
    if settings.get("bind_host") not in ("127.0.0.1", "localhost"):
        issues.append({"level": "high", "check": "bind_host", "message": "Panel is configured for non-local binding."})
    if not cfg.get("panel", {}).get("api_token"):
        issues.append({"level": "high", "check": "api_token", "message": "API token has not been generated."})
    for domain, site in cfg.get("sites", {}).items():
        try:
            _safe_path(site.get("web_root", ""), CONFIG_DIR)
        except ValueError:
            issues.append({"level": "critical", "check": "site_root", "message": f"{domain} web root escapes config dir."})
    score = max(0, 100 - (20 * len([i for i in issues if i["level"] == "critical"])) - (10 * len([i for i in issues if i["level"] == "high"])))
    return {"score": score, "issues": issues, "checked_at": datetime.utcnow().isoformat() + "Z"}


def backup_create(name=None):
    ensure_dirs()
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_name = name or f"backup-{stamp}"
    archive_path = BACKUPS_DIR / f"{backup_name}.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        if CONFIG_FILE.exists():
            archive.write(CONFIG_FILE, "config.json")
        for site_root in WEBROOTS_DIR.glob("*"):
            if site_root.is_dir():
                for item in site_root.rglob("*"):
                    if item.is_file():
                        archive.write(item, item.relative_to(CONFIG_DIR))
    cfg = load_config()
    cfg.setdefault("backups", {})[backup_name] = {
        "name": backup_name,
        "path": str(archive_path),
        "size": archive_path.stat().st_size,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    save_config(cfg)
    audit_event("backup.create", "ok", {"name": backup_name, "path": str(archive_path)})
    return cfg["backups"][backup_name]


def backup_list():
    return load_config().get("backups", {})


def backup_restore(name):
    backups = backup_list()
    backup = backups.get(name)
    if not backup:
        raise ValueError(f"backup not found: {name}")
    archive_path = Path(backup["path"])
    if not archive_path.exists():
        raise ValueError(f"backup archive missing: {archive_path}")
    restore_dir = CACHE_DIR / f"restore-{name}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    restore_dir.mkdir(parents=True, exist_ok=True)
    extract_archive(archive_path, restore_dir)
    restored_config = restore_dir / "config.json"
    if restored_config.exists():
        shutil.copy2(restored_config, CONFIG_FILE)
    restored_webroots = restore_dir / "webroots"
    if restored_webroots.exists():
        if WEBROOTS_DIR.exists():
            shutil.rmtree(WEBROOTS_DIR)
        shutil.copytree(restored_webroots, WEBROOTS_DIR)
    audit_event("backup.restore", "ok", {"name": name})
    return {"name": name, "restored_from": str(archive_path), "staging_dir": str(restore_dir)}


def _site_root(domain):
    site = site_get(domain)
    if not site:
        raise ValueError(f"site not found: {domain}")
    root = Path(site["web_root"]).resolve()
    if not _is_within_directory(CONFIG_DIR, root):
        raise ValueError("site web root is outside Atulya config dir")
    return root


def _site_file_path(domain, relative_path="."):
    root = _site_root(domain)
    target = (root / relative_path).resolve()
    if not _is_within_directory(root, target):
        raise ValueError("path escapes site web root")
    return target


def file_list(domain, relative_path="."):
    target = _site_file_path(domain, relative_path)
    if not target.exists():
        raise ValueError("path not found")
    if target.is_file():
        return [{"name": target.name, "path": str(Path(relative_path)), "type": "file", "size": target.stat().st_size}]
    entries = []
    for item in sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
        entries.append(
            {
                "name": item.name,
                "path": str(item.relative_to(_site_root(domain))),
                "type": "directory" if item.is_dir() else "file",
                "size": item.stat().st_size if item.is_file() else None,
            }
        )
    return entries


def file_write(domain, relative_path, content):
    target = _site_file_path(domain, relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    audit_event("file.write", "ok", {"domain": domain, "path": relative_path})
    return {"path": str(target), "size": target.stat().st_size}


def file_mkdir(domain, relative_path):
    target = _site_file_path(domain, relative_path)
    target.mkdir(parents=True, exist_ok=True)
    audit_event("file.mkdir", "ok", {"domain": domain, "path": relative_path})
    return {"path": str(target)}


def file_delete(domain, relative_path):
    target = _site_file_path(domain, relative_path)
    if target == _site_root(domain):
        raise ValueError("refusing to delete site root")
    if target.is_dir():
        shutil.rmtree(target)
    elif target.exists():
        target.unlink()
    else:
        raise ValueError("path not found")
    audit_event("file.delete", "ok", {"domain": domain, "path": relative_path})
    return {"deleted": str(target)}


def dashboard_data():
    return {
        "status": system_status(),
        "sites": list(site_list().values()),
        "backups": list(backup_list().values()),
        "security": security_scan(),
        "audit": audit_list(20),
    }


def get_platform():
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform == "win32":
        return "windows"
    return sys.platform


def get_arch():
    machine = os.uname().machine if hasattr(os, "uname") else "x86_64"
    return machine


def get_python_cmd():
    if get_platform() == "win32":
        return [sys.executable, "-m"]
    return [sys.executable, "-m"]


def run_cmd(cmd, **kwargs):
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def package_name(tool_name):
    return tool_name.lower().replace("-", "_")


def is_installed_via_pip(tool_name):
    try:
        metadata.version(package_name(tool_name))
        return True
    except metadata.PackageNotFoundError:
        return False


def installed_pip_version(tool_name):
    try:
        return metadata.version(package_name(tool_name))
    except metadata.PackageNotFoundError:
        return None


def get_recorded_version(tool_name):
    cfg = get_installed_tools().get(tool_name, {})
    return cfg.get("version")


def get_installed_version(tool_name):
    return get_recorded_version(tool_name) or installed_pip_version(tool_name)


def is_installed(tool_name):
    if is_installed_via_pip(tool_name):
        return True
    if is_installed_via_local(tool_name):
        return True
    return False


def is_installed_via_local(tool_name):
    ensure_dirs()
    return (TOOLS_DIR / package_name(tool_name)).exists()


def get_installed_tools():
    cfg = load_config()
    return cfg.get("installed", {})


def get_github_releases(tool_name, max_per_page=10):
    url = f"https://api.github.com/repos/{ATULYA_ORG}/{tool_name}/releases?per_page={max_per_page}"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_latest_release(tool_name):
    url = f"https://api.github.com/repos/{ATULYA_ORG}/{tool_name}/releases/latest"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_release_assets(release):
    return release.get("assets", [])


def download_file(url, dest, desc=None):
    resp = requests.get(url, stream=True, timeout=60)
    resp.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    return dest


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_archive(archive_path, dest_dir):
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    if str(archive_path).endswith(".zip"):
        with zipfile.ZipFile(archive_path, "r") as zf:
            safe_extract_zip(zf, dest_dir)
    elif str(archive_path).endswith((".tar.gz", ".tgz")):
        with tarfile.open(archive_path, "r:gz") as tf:
            safe_extract_tar(tf, dest_dir)
    elif str(archive_path).endswith(".tar"):
        with tarfile.open(archive_path, "r:") as tf:
            safe_extract_tar(tf, dest_dir)
    else:
        shutil.copy2(archive_path, dest_dir)
    return dest_dir


def _is_within_directory(parent, child):
    parent = Path(parent).resolve()
    child = Path(child).resolve()
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def safe_extract_zip(archive, dest_dir):
    for member in archive.infolist():
        target = Path(dest_dir) / member.filename
        if not _is_within_directory(dest_dir, target):
            raise ValueError(f"Unsafe archive member path: {member.filename}")
    archive.extractall(dest_dir)


def safe_extract_tar(archive, dest_dir):
    for member in archive.getmembers():
        target = Path(dest_dir) / member.name
        if not _is_within_directory(dest_dir, target):
            raise ValueError(f"Unsafe archive member path: {member.name}")
    archive.extractall(dest_dir)


def install_from_pip(tool_name, version=None):
    pkg_name = package_name(tool_name)
    spec = f"{pkg_name}=={version}" if version else pkg_name
    result = run_cmd(get_python_cmd() + ["pip", "install", spec], check=False)
    return result.returncode == 0


def uninstall_pip(tool_name):
    pkg_name = package_name(tool_name)
    result = run_cmd(get_python_cmd() + ["pip", "uninstall", pkg_name, "-y"], check=False)
    return result.returncode == 0


def install_local(tool_name, source_dir):
    ensure_dirs()
    pkg_name = package_name(tool_name)
    dest = TOOLS_DIR / pkg_name
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(source_dir, dest)
    cfg = load_config()
    cfg.setdefault("installed", {})[tool_name] = {
        "version": "local",
        "source": str(Path(source_dir).resolve()),
    }
    save_config(cfg)
    return dest


def run_tool(tool_name, args=None):
    pkg_name = package_name(tool_name)
    cmd = [sys.executable, "-m", pkg_name] + (args or [])

    if is_installed_via_pip(tool_name):
        return subprocess.run(cmd, check=False).returncode

    local_path = TOOLS_DIR / pkg_name
    if local_path.exists():
        env = os.environ.copy()
        existing_pythonpath = env.get("PYTHONPATH")
        pythonpath_parts = [str(TOOLS_DIR)]
        if existing_pythonpath:
            pythonpath_parts.append(existing_pythonpath)
        env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
        return subprocess.run(cmd, check=False, env=env).returncode

    return 1


def check_update(tool_name):
    current = get_installed_version(tool_name)
    if not current:
        return None
    try:
        latest = get_latest_release(tool_name)
        latest_ver = latest.get("tag_name", "").lstrip("v")
        if latest_ver and latest_ver != current:
            return {"current": current, "latest": latest_ver, "release": latest}
    except Exception:
        pass
    return None


def get_tool_info(tool_name):
    parts = re.sub(r'([A-Z])', r' \1', tool_name.replace("Atulya-", "")).strip().split()
    descriptions = {
        "All": "Universal file format converter (40+ formats)",
        "Data": "Data cleaning, deduplication & scrubbing",
        "Office": "Office productivity: DOCX, PDF, spreadsheet tools",
        "Accounting": "Accounting & ERP for Indian businesses",
        "GST": "GST return filing & compliance suite",
        "HR": "HR management & payroll",
        "Automation": "Desktop automation & macro hub",
        "SAP": "SAP automation toolkit",
        "Launch": "Atulya tools launcher & auto-updater",
    }
    key = parts[0] if parts else tool_name
    desc = descriptions.get(key, "Atulya business tool")
    return {"name": tool_name, "package": package_name(tool_name), "description": desc}


def discover_all_tools():
    from . import ATULYA_TOOLS

    installed_cfg = get_installed_tools()
    tools = []
    for name in ATULYA_TOOLS:
        info = get_tool_info(name)
        info["installed"] = is_installed(name)
        if info["installed"]:
            info["version"] = installed_cfg.get(name, {}).get("version") or installed_pip_version(name) or "?"
        tools.append(info)
    return tools


def nginx_apply_and_reload(domain):
    site = site_get(domain)
    if not site:
        return {"ok": False, "error": f"site not found: {domain}"}
    nginx_plan = nginx_apply_plan(domain)
    if not nginx_plan:
        return {"ok": False, "error": "no plan generated"}
    item = nginx_plan[0]
    avail_target = Path(item["target"])
    enabled_link = Path(item["enabled_link"])
    source = Path(item["source"])
    if get_platform() != "linux":
        return {"ok": False, "error": "nginx apply only supported on Linux"}
    try:
        avail_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, avail_target)
        enabled_link.parent.mkdir(parents=True, exist_ok=True)
        if enabled_link.exists() or enabled_link.is_symlink():
            enabled_link.unlink()
        enabled_link.symlink_to(avail_target.resolve())
        test_result = subprocess.run(["nginx", "-t"], capture_output=True, text=True, check=False)
        if test_result.returncode != 0:
            return {"ok": False, "error": f"nginx -t failed: {test_result.stderr}"}
        reload_result = subprocess.run(["systemctl", "reload", "nginx"], capture_output=True, text=True, check=False)
        if reload_result.returncode != 0:
            return {"ok": False, "error": f"reload failed: {reload_result.stderr}"}
        audit_event("nginx.reload", "ok", {"domain": domain})
        return {"ok": True, "domain": domain}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def database_create(name, db_type="mysql"):
    if get_platform() != "linux":
        return {"ok": False, "error": "database provisioning only supported on Linux"}
    if db_type in ("mysql", "mariadb"):
        result = run_cmd(["mysql", "-e", f"CREATE DATABASE IF NOT EXISTS `{name}`;"], check=False)
    elif db_type == "postgresql":
        result = run_cmd(["sudo", "-u", "postgres", "createdb", name], check=False)
    else:
        return {"ok": False, "error": f"unsupported db type: {db_type}"}
    return {"ok": result.returncode == 0, "name": name, "type": db_type}


def database_drop(name, db_type="mysql"):
    if get_platform() != "linux":
        return {"ok": False, "error": "database operations only supported on Linux"}
    if db_type in ("mysql", "mariadb"):
        result = run_cmd(["mysql", "-e", f"DROP DATABASE IF EXISTS `{name}`;"], check=False)
    elif db_type == "postgresql":
        result = run_cmd(["sudo", "-u", "postgres", "dropdb", name], check=False)
    else:
        return {"ok": False, "error": f"unsupported db type: {db_type}"}
    return {"ok": result.returncode == 0, "name": name}


def database_backup(name, db_type="mysql"):
    ensure_dirs()
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUPS_DIR / f"db-{name}-{stamp}.sql.gz"
    if get_platform() != "linux":
        return {"ok": False, "error": "database backup only supported on Linux"}
    import gzip
    if db_type in ("mysql", "mariadb"):
        result = run_cmd(["mysqldump", "--single-transaction", name], check=False)
    elif db_type == "postgresql":
        result = run_cmd(["sudo", "-u", "postgres", "pg_dump", name], check=False)
    else:
        return {"ok": False, "error": f"unsupported db type: {db_type}"}
    if result.returncode != 0:
        return {"ok": False, "error": result.stderr}
    with gzip.open(backup_path, "wt", encoding="utf-8") as f:
        f.write(result.stdout)
    audit_event("database.backup", "ok", {"name": name, "path": str(backup_path)})
    return {"ok": True, "name": name, "path": str(backup_path), "size": backup_path.stat().st_size}


def ssl_issue_letsencrypt(domain):
    if get_platform() != "linux":
        return {"ok": False, "error": "SSL issuance only supported on Linux"}
    cert_dir = CONFIG_DIR / "ssl" / domain
    cert_dir.mkdir(parents=True, exist_ok=True)
    result = run_cmd([
        "certbot", "certonly", "--nginx", "-d", domain,
        "--non-interactive", "--agree-tos", "--email", f"admin@{domain}",
        "--cert-path", str(cert_dir / "fullchain.pem"),
        "--key-path", str(cert_dir / "privkey.pem"),
    ], check=False)
    if result.returncode != 0:
        result = run_cmd([
            "certbot", "certonly", "--standalone", "-d", domain,
            "--non-interactive", "--agree-tos", "--email", f"admin@{domain}",
        ], check=False)
    if result.returncode == 0:
        audit_event("ssl.issue", "ok", {"domain": domain})
        return {"ok": True, "domain": domain, "cert_path": str(cert_dir / "fullchain.pem"), "key_path": str(cert_dir / "privkey.pem"), "expires_at": None}
    return {"ok": False, "error": result.stderr}


def ssl_renew(domain):
    if get_platform() != "linux":
        return {"ok": False, "error": "SSL renewal only supported on Linux"}
    result = run_cmd(["certbot", "renew", "--cert-name", domain], check=False)
    if result.returncode == 0:
        audit_event("ssl.renew", "ok", {"domain": domain})
        return {"ok": True, "domain": domain}
    return {"ok": False, "error": result.stderr}


def firewall_status():
    if get_platform() != "linux" or not shutil.which("ufw"):
        return {"installed": False, "active": False}
    result = run_cmd(["ufw", "status"], check=False)
    active = "active" in result.stdout.lower()
    return {"installed": True, "active": active, "raw": result.stdout.strip()}


def firewall_list_rules():
    if get_platform() != "linux" or not shutil.which("ufw"):
        return []
    result = run_cmd(["ufw", "status", "numbered"], check=False)
    rules = []
    for line in result.stdout.strip().splitlines():
        if line.startswith("[") and "]" in line:
            rules.append(line)
    return rules


def firewall_enable():
    if get_platform() != "linux":
        return {"ok": False, "error": "firewall only supported on Linux"}
    result = run_cmd(["ufw", "--force", "enable"], check=False)
    return {"ok": result.returncode == 0}


def firewall_disable():
    if get_platform() != "linux":
        return {"ok": False, "error": "firewall only supported on Linux"}
    result = run_cmd(["ufw", "disable"], check=False)
    return {"ok": result.returncode == 0}


def firewall_allow(port, proto="tcp"):
    if get_platform() != "linux":
        return {"ok": False, "error": "firewall only supported on Linux"}
    result = run_cmd(["ufw", "allow", f"{port}/{proto}"], check=False)
    return {"ok": result.returncode == 0}


def firewall_deny(port, proto="tcp"):
    if get_platform() != "linux":
        return {"ok": False, "error": "firewall only supported on Linux"}
    result = run_cmd(["ufw", "deny", f"{port}/{proto}"], check=False)
    return {"ok": result.returncode == 0}


def fail2ban_status():
    if get_platform() != "linux":
        return {"installed": False, "active": False, "jails": []}
    result = run_cmd(["fail2ban-client", "status"], check=False)
    if result.returncode != 0:
        return {"installed": False, "active": False, "jails": []}
    jails = []
    for line in result.stdout.splitlines():
        if "Jail list" in line:
            jails = [j.strip() for j in line.split(":", 1)[1].split(",")]
    return {"installed": True, "active": True, "jails": jails}


def fail2ban_restart():
    if get_platform() != "linux":
        return {"ok": False, "error": "fail2ban only supported on Linux"}
    result = run_cmd(["systemctl", "restart", "fail2ban"], check=False)
    return {"ok": result.returncode == 0}


APP_CATALOG = {
    "wordpress": {"name": "WordPress", "description": "CMS and blogging platform", "requires": ["mysql", "php"]},
    "nextcloud": {"name": "Nextcloud", "description": "File sharing and collaboration", "requires": ["mysql", "php"]},
    "laravel": {"name": "Laravel", "description": "PHP web framework", "requires": ["mysql", "php"]},
    "ghost": {"name": "Ghost", "description": "Professional publishing platform", "requires": ["nodejs"]},
    "flask": {"name": "Flask App", "description": "Python web application", "requires": ["python"]},
    "django": {"name": "Django App", "description": "Python web framework", "requires": ["python", "postgresql"]},
}


def installed_apps():
    ensure_dirs()
    cfg = load_config()
    return cfg.get("installed_apps", {})


def available_apps():
    return APP_CATALOG


def app_install(app_name, domain):
    if app_name not in APP_CATALOG:
        return {"ok": False, "error": f"unknown app: {app_name}"}
    site = site_create(domain)
    cfg = load_config()
    cfg.setdefault("installed_apps", {})[app_name] = {
        "domain": domain,
        "installed_at": datetime.utcnow().isoformat() + "Z",
    }
    save_config(cfg)
    audit_event("app.install", "ok", {"app": app_name, "domain": domain})
    return {"ok": True, "app": app_name, "domain": domain}


def app_uninstall(app_name):
    cfg = load_config()
    apps = cfg.get("installed_apps", {})
    if app_name not in apps:
        return {"ok": False, "error": f"app not installed: {app_name}"}
    apps.pop(app_name)
    save_config(cfg)
    audit_event("app.uninstall", "ok", {"app": app_name})
    return {"ok": True, "app": app_name}
