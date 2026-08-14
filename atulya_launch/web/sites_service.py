"""SQLite-backed site management — replaces config.json for web routes."""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..web.database import connect, audit_log


def _validate_domain(domain: str) -> str:
    """Validate and normalize a domain name."""
    domain = domain.strip().lower()
    if not domain or ".." in domain:
        raise ValueError(f"invalid domain: {domain}")
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789.-")
    if not all(c in allowed for c in domain):
        raise ValueError(f"invalid domain characters: {domain}")
    return domain


def list_sites() -> dict[str, Any]:
    """Return all sites from SQLite."""
    with connect() as conn:
        rows = conn.execute("SELECT * FROM sites ORDER BY domain").fetchall()
    sites = {}
    for row in rows:
        site = dict(row)
        sites[site["domain"]] = {
            "domain": site["domain"],
            "web_root": site["web_root"],
            "proxy_pass": site["proxy_pass"],
            "php": bool(site["php"]),
            "php_version": site["php_version"],
            "enabled": bool(site["enabled"]),
            "nginx_config": site["nginx_config"],
            "created_at": site["created_at"],
        }
    return sites


def get_site(domain: str) -> dict[str, Any] | None:
    """Return a single site by domain."""
    domain = _validate_domain(domain)
    with connect() as conn:
        row = conn.execute("SELECT * FROM sites WHERE domain = ?", (domain,)).fetchone()
    if not row:
        return None
    site = dict(row)
    return {
        "domain": site["domain"],
        "web_root": site["web_root"],
        "proxy_pass": site["proxy_pass"],
        "php": bool(site["php"]),
        "php_version": site["php_version"],
        "enabled": bool(site["enabled"]),
        "nginx_config": site["nginx_config"],
        "created_at": site["created_at"],
    }


def create_site(domain: str, web_root: str | None = None, proxy_pass: str | None = None,
                php: bool = False, php_version: str | None = None) -> dict[str, Any]:
    """Create a new site in SQLite."""
    domain = _validate_domain(domain)
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"

    if web_root:
        root = Path(web_root)
    else:
        from .. import core
        root = core.WEBROOTS_DIR / domain / "public"

    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError:
        if web_root:
            raise
        root = Path(tempfile.gettempdir()) / "atulya-launch" / "webroots" / domain / "public"
        root.mkdir(parents=True, exist_ok=True)

    index_path = root / "index.html"
    if not index_path.exists():
        index_path.write_text(
            f"<!doctype html><title>{domain}</title><h1>{domain}</h1><p>Hosted by Atulya Launch.</p>\n",
            encoding="utf-8",
        )

    if php and not php_version:
        php_version = "8.3"

    from .. import core
    nginx_config = str(core.generate_nginx_config(domain, root, proxy_pass, php, php_version))

    with connect() as conn:
        existing = conn.execute("SELECT id FROM sites WHERE domain = ?", (domain,)).fetchone()
        if existing:
            raise ValueError(f"site already exists: {domain}")
        conn.execute(
            "INSERT INTO sites (domain, web_root, proxy_pass, php, php_version, enabled, nginx_config, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (domain, str(root), proxy_pass, int(php), php_version, 1, nginx_config, now, now),
        )

    # Apply via driver
    try:
        from ..drivers import get_platform_driver
        driver = get_platform_driver(dry_run=False)
        config_path = Path(nginx_config)
        if config_path.exists():
            driver.web.apply_site(domain, config_path.read_text(encoding="utf-8"))
            # Create symlink to sites-enabled
            enabled_link = Path(f"/etc/nginx/sites-enabled/{domain}.conf")
            if not enabled_link.exists():
                try:
                    enabled_link.symlink_to(config_path)
                except OSError:
                    pass
            driver.web.reload()
    except Exception:
        pass

    audit_log("system", "site.create", "ok", {"domain": domain})
    return get_site(domain)


def delete_site(domain: str) -> bool:
    """Delete a site from SQLite."""
    domain = _validate_domain(domain)
    with connect() as conn:
        row = conn.execute("SELECT nginx_config, php, php_version FROM sites WHERE domain = ?", (domain,)).fetchone()
        if not row:
            return False
        conn.execute("DELETE FROM sites WHERE domain = ?", (domain,))

    # Remove nginx config file
    config_path = Path(row["nginx_config"]) if row["nginx_config"] else None
    if config_path and config_path.exists():
        config_path.unlink()

    # Apply via driver
    try:
        from .. import core
        from ..drivers import get_platform_driver
        driver = get_platform_driver(dry_run=False)
        driver.web.apply_site(domain, "")
        driver.web.reload()

        # Remove PHP-FPM pool if PHP was enabled
        if row["php"] and row["php_version"]:
            core.php_fpm_pool_remove(domain, row["php_version"])
    except Exception:
        pass

    audit_log("system", "site.delete", "ok", {"domain": domain})
    return True


def set_php_version(domain: str, php_version: str) -> dict[str, Any] | None:
    """Set PHP version for a site."""
    domain = _validate_domain(domain)
    from .. import core
    site = get_site(domain)
    if not site:
        raise ValueError(f"site not found: {domain}")

    nginx_config = str(core.generate_nginx_config(
        domain, Path(site["web_root"]), site.get("proxy_pass"), True, php_version
    ))

    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"
    with connect() as conn:
        conn.execute(
            "UPDATE sites SET php = 1, php_version = ?, nginx_config = ?, updated_at = ? WHERE domain = ?",
            (php_version, nginx_config, now, domain),
        )

    # Install PHP-FPM, create pool, and apply nginx config via driver
    try:
        core.php_fpm_install(domain, php_version)
        core.php_fpm_pool_create(domain, php_version)

        from ..drivers import get_platform_driver
        driver = get_platform_driver(dry_run=False)
        config_path = Path(nginx_config)
        if config_path.exists():
            driver.web.apply_site(domain, config_path.read_text(encoding="utf-8"))
            driver.web.reload()
    except Exception:
        pass

    audit_log("system", "site.php_version", "ok", {"domain": domain, "php_version": php_version})
    return get_site(domain)


def toggle_site(domain: str, enabled: bool) -> dict[str, Any] | None:
    """Enable or disable a site."""
    domain = _validate_domain(domain)
    site = get_site(domain)
    if not site:
        raise ValueError(f"site not found: {domain}")

    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"
    with connect() as conn:
        conn.execute(
            "UPDATE sites SET enabled = ?, updated_at = ? WHERE domain = ?",
            (int(enabled), now, domain),
        )

    # Enable/disable by linking/unlinking nginx config
    import os
    vhost = f"/etc/nginx/sites-enabled/{domain}.conf"
    if enabled:
        available = f"/etc/nginx/sites-available/{domain}.conf"
        if os.path.exists(available) and not os.path.exists(vhost):
            os.symlink(available, vhost)
    else:
        if os.path.exists(vhost) or os.path.islink(vhost):
            os.unlink(vhost)

    try:
        from ..drivers import get_platform_driver
        driver = get_platform_driver(dry_run=False)
        driver.web.reload()
    except Exception:
        pass

    audit_log("system", "site.toggle", "ok", {"domain": domain, "enabled": enabled})
    return get_site(domain)


def migrate_config_json_to_sqlite() -> int:
    """Migrate sites from config.json to SQLite. Returns count of migrated sites."""
    from .. import core
    cfg = core.load_config()
    sites = cfg.get("sites", {})
    count = 0
    for domain, site_data in sites.items():
        try:
            existing = get_site(domain)
            if existing:
                continue
            with connect() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO sites (domain, web_root, proxy_pass, php, php_version, enabled, nginx_config, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        domain,
                        site_data.get("web_root"),
                        site_data.get("proxy_pass"),
                        int(site_data.get("php", False)),
                        site_data.get("php_version"),
                        int(site_data.get("enabled", True)),
                        site_data.get("nginx_config"),
                        site_data.get("created_at", datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"),
                        datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z",
                    ),
                )
            count += 1
        except Exception:
            pass
    return count
