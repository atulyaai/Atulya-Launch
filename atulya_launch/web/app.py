"""
Atulya-Launch Web Application
FastAPI app for the lightweight cPanel alternative.
"""
import os
from pathlib import Path

from fastapi import FastAPI, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from atulya_launch import core, utils
from atulya_launch.web.auth import get_current_user, init_auth


def create_app() -> FastAPI:
    app = FastAPI(
        title="Atulya-Launch",
        description="Lightweight cPanel alternative — < 50MB RAM idle",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url=None,
    )

    static_dir = Path(__file__).parent / "static"

    # ── Initialise auth (ensure admin user exists) ──
    @app.on_event("startup")
    def startup():
        init_auth()

    # ── Mount routers ──────────────────────────────────────────────────
    from atulya_launch.web.auth import router as auth_router
    from atulya_launch.web.api.sites import router as sites_router
    from atulya_launch.web.api.dns import router as dns_router
    from atulya_launch.web.api.email import router as email_router
    from atulya_launch.web.api.db import router as db_router
    from atulya_launch.web.api.files import router as files_router
    from atulya_launch.web.api.ssl import router as ssl_router
    from atulya_launch.web.api.backup import router as backup_router
    from atulya_launch.web.api.monitor import router as monitor_router
    from atulya_launch.web.api.firewall import router as firewall_router
    from atulya_launch.web.api.cron import router as cron_router
    from atulya_launch.web.api.apps import router as apps_router
    from atulya_launch.web.api.system import router as system_router
    from atulya_launch.web.api.ssh import router as ssh_router
    from atulya_launch.web.api.subdomains import router as subdomains_router
    from atulya_launch.web.api.redirects import router as redirects_router
    from atulya_launch.web.api.php import router as php_router
    from atulya_launch.web.api.dkim import router as dkim_router
    from atulya_launch.web.api.twofa import router as twofa_router
    from atulya_launch.web.api.gitdeploy import router as gitdeploy_router
    from atulya_launch.web.api.staging import router as staging_router
    from atulya_launch.web.api.errorpages import router as errorpages_router
    from atulya_launch.web.api.quotas import router as quotas_router
    from atulya_launch.web.api.apitokens import router as apitokens_router
    from atulya_launch.web.api.backups3 import router as backups3_router
    from atulya_launch.web.api.statuspage import router as statuspage_router
    from atulya_launch.web.api.ftp import router as ftp_router
    from atulya_launch.web.api.webmail import router as webmail_router
    from atulya_launch.web.api.autoresponders import router as autoresponders_router
    from atulya_launch.web.api.spam import router as spam_router
    from atulya_launch.web.api.docker import router as docker_router
    from atulya_launch.web.api.nodeapps import router as nodeapps_router
    from atulya_launch.web.api.pythonapps import router as pythonapps_router
    from atulya_launch.web.api.audit import router as audit_router
    from atulya_launch.web.api.search import router as search_router
    from atulya_launch.web.api.sessions import router as sessions_router
    from atulya_launch.web.api.loginhistory import router as loginhistory_router
    from atulya_launch.web.api.wildcardssl import router as wildcardssl_router
    from atulya_launch.web.api.csr import router as csr_router
    from atulya_launch.web.api.mailinglists import router as mailinglists_router
    from atulya_launch.web.api.remotedb import router as remotedb_router
    from atulya_launch.web.api.phpmyadmin import router as phpmyadmin_router
    from atulya_launch.web.api.filecompress import router as filecompress_router
    from atulya_launch.web.api.fileshare import router as fileshare_router
    from atulya_launch.web.api.csrf import router as csrf_router
    from atulya_launch.web.api.passwordpolicy import router as passwordpolicy_router
    from atulya_launch.web.api.servercontrol import router as servercontrol_router
    from atulya_launch.web.api.timezone import router as timezone_router
    from atulya_launch.web.api.sshaccess import router as sshaccess_router
    from atulya_launch.web.api.ipaccess import router as ipaccess_router
    from atulya_launch.web.api.cronscheduler import router as cronscheduler_router
    from atulya_launch.web.api.dbusers import router as dbusers_router
    from atulya_launch.web.api.bandwidth import router as bandwidth_router
    from atulya_launch.web.api.resourcehistory import router as resourcehistory_router
    from atulya_launch.web.api.dnsimportexport import router as dnsimportexport_router
    from atulya_launch.web.api.backupencryption import router as backupencryption_router
    from atulya_launch.web.api.cloudbackup import router as cloudbackup_router
    from atulya_launch.web.api.notifications import router as notifications_router
    from atulya_launch.web.api.sftpisolation import router as sftpisolation_router
    from atulya_launch.web.api.errorlogs import router as errorlogs_router
    from atulya_launch.web.api.dbschedulebackup import router as dbschedulebackup_router
    from atulya_launch.web.api.ipv6 import router as ipv6_router
    from atulya_launch.web.api.networkstats import router as networkstats_router
    from atulya_launch.web.api.vpn import router as vpn_router
    from atulya_launch.web.api.fail2ban import router as fail2ban_router
    from atulya_launch.web.api.nginxproxy import router as nginxproxy_router
    from atulya_launch.web.api.opencache import router as opencache_router
    from atulya_launch.web.api.portscan import router as portscan_router
    from atulya_launch.web.api.letsencryptwildcard import router as letsencryptwildcard_router
    from atulya_launch.web.api.clouddns import router as clouddns_router
    from atulya_launch.web.api.emailalerts import router as emailalerts_router
    from atulya_launch.web.api.sslautorenew import router as sslautorenew_router
    from atulya_launch.web.api.modsecurity import router as modsecurity_router
    from atulya_launch.web.api.rediscache import router as rediscache_router
    from atulya_launch.web.api.nginxcache import router as nginxcache_router
    from atulya_launch.web.api.cloudflare import router as cloudflare_router
    from atulya_launch.web.api.sshterminal import router as sshterminal_router
    from atulya_launch.web.api.emailrouting import router as emailrouting_router
    from atulya_launch.web.api.hotlink import router as hotlink_router
    from atulya_launch.web.api.bandwidthlimit import router as bandwidthlimit_router
    from atulya_launch.web.api.dbimportexport import router as dbimportexport_router
    from atulya_launch.web.api.multiuser import router as multiuser_router
    from atulya_launch.web.api.plugin_system import router as plugins_router
    from atulya_launch.web.api.migration import router as migration_router
    from atulya_launch.web.api.emailforwarding import router as emailforwarding_router
    from atulya_launch.web.api.healthdashboard import router as healthdashboard_router
    from atulya_launch.web.api.ssldetails import router as ssldetails_router

    app.include_router(auth_router)
    app.include_router(sites_router)
    app.include_router(dns_router)
    app.include_router(email_router)
    app.include_router(db_router)
    app.include_router(files_router)
    app.include_router(ssl_router)
    app.include_router(backup_router)
    app.include_router(monitor_router)
    app.include_router(firewall_router)
    app.include_router(cron_router)
    app.include_router(apps_router)
    app.include_router(system_router)
    app.include_router(ssh_router)
    app.include_router(subdomains_router)
    app.include_router(redirects_router)
    app.include_router(php_router)
    app.include_router(dkim_router)
    app.include_router(twofa_router)
    app.include_router(gitdeploy_router)
    app.include_router(staging_router)
    app.include_router(errorpages_router)
    app.include_router(quotas_router)
    app.include_router(apitokens_router)
    app.include_router(backups3_router)
    app.include_router(statuspage_router)
    app.include_router(ftp_router)
    app.include_router(webmail_router)
    app.include_router(autoresponders_router)
    app.include_router(spam_router)
    app.include_router(docker_router)
    app.include_router(nodeapps_router)
    app.include_router(pythonapps_router)
    app.include_router(audit_router)
    app.include_router(search_router)
    app.include_router(sessions_router)
    app.include_router(loginhistory_router)
    app.include_router(wildcardssl_router)
    app.include_router(csr_router)
    app.include_router(mailinglists_router)
    app.include_router(remotedb_router)
    app.include_router(phpmyadmin_router)
    app.include_router(filecompress_router)
    app.include_router(fileshare_router)
    app.include_router(csrf_router)
    app.include_router(passwordpolicy_router)
    app.include_router(servercontrol_router)
    app.include_router(timezone_router)
    app.include_router(sshaccess_router)
    app.include_router(ipaccess_router)
    app.include_router(cronscheduler_router)
    app.include_router(dbusers_router)
    app.include_router(bandwidth_router)
    app.include_router(resourcehistory_router)
    app.include_router(emailalerts_router)
    app.include_router(sslautorenew_router)
    app.include_router(modsecurity_router)
    app.include_router(rediscache_router)
    app.include_router(nginxcache_router)
    app.include_router(cloudflare_router)
    app.include_router(sshterminal_router)
    app.include_router(emailrouting_router)
    app.include_router(hotlink_router)
    app.include_router(bandwidthlimit_router)
    app.include_router(dbimportexport_router)
    app.include_router(multiuser_router)
    app.include_router(plugins_router)
    app.include_router(migration_router)
    app.include_router(emailforwarding_router)
    app.include_router(healthdashboard_router)
    app.include_router(ssldetails_router)
    app.include_router(dnsimportexport_router)
    app.include_router(backupencryption_router)
    app.include_router(cloudbackup_router)
    app.include_router(notifications_router)
    app.include_router(sftpisolation_router)
    app.include_router(errorlogs_router)
    app.include_router(dbschedulebackup_router)
    app.include_router(ipv6_router)
    app.include_router(networkstats_router)
    app.include_router(vpn_router)
    app.include_router(fail2ban_router)
    app.include_router(nginxproxy_router)
    app.include_router(opencache_router)
    app.include_router(portscan_router)
    app.include_router(letsencryptwildcard_router)
    app.include_router(clouddns_router)

    # ── Plugins ────────────────────────────────────────────────────────
    from atulya_launch.web.api.plugins.cms_installer import router as cms_installer_router
    from atulya_launch.web.api.plugins.security_advisor import router as security_advisor_router
    from atulya_launch.web.api.plugins.webmail import router as webmail_plugin_router
    from atulya_launch.web.api.plugins.antivirus import router as antivirus_router
    from atulya_launch.web.api.plugins.reseller import router as reseller_router
    from atulya_launch.web.api.plugins.analytics import router as analytics_router

    app.include_router(cms_installer_router)
    app.include_router(security_advisor_router)
    app.include_router(webmail_plugin_router)
    app.include_router(antivirus_router)
    app.include_router(reseller_router)
    app.include_router(analytics_router)

    # ── Aggregated dashboard endpoint ──────────────────────────────────
    @app.get("/api/dashboard/stats")
    def dashboard_stats(user: dict = Depends(get_current_user)):
        sites = core.site_list()
        dbs = core.db_list()
        certs = core.ssl_list()
        backups = core.backup_list()
        try:
            status = core.monitor_status()
        except Exception:
            status = {}
        return {
            "sites_count": len(sites),
            "databases_count": len(dbs),
            "ssl_count": len(certs),
            "backups_count": len(backups),
            "cpu_percent": status.get("cpu", {}).get("percent", 0),
            "memory_percent": status.get("memory", {}).get("percent", 0),
            "disk_percent": status.get("disk", {}).get("percent", 0),
            "uptime_hours": status.get("uptime", {}).get("uptime_hours", 0),
        }

    # ── Settings endpoints ─────────────────────────────────────────────
    @app.get("/api/settings")
    def get_settings(user: dict = Depends(get_current_user)):
        return core.config_show()

    @app.post("/api/settings/password")
    def change_password(body: dict, user: dict = Depends(get_current_user)):
        from atulya_launch.web.auth import _verify_password, _hash_password
        config = utils.load_config()
        auth_cfg = config.get("web", {}).get("auth", {})
        admin_hash = auth_cfg.get("admin_password_hash", "")
        if not _verify_password(body.get("current_password", ""), admin_hash):
            return JSONResponse(status_code=400, content={"error": "Current password is incorrect"})
        auth_cfg["admin_password_hash"] = _hash_password(body.get("new_password", ""))
        web_cfg = config.get("web", {})
        web_cfg["auth"] = auth_cfg
        config["web"] = web_cfg
        utils.save_config(config)
        return {"status": "password changed"}

    # ── Kill process endpoint ──────────────────────────────────────────
    @app.post("/api/monitor/processes/{pid}/kill")
    def kill_process(pid: int, user: dict = Depends(get_current_user)):
        import signal
        try:
            os.kill(pid, signal.SIGTERM)
            return {"status": "killed", "pid": pid}
        except ProcessLookupError:
            return JSONResponse(status_code=404, content={"error": "Process not found"})
        except PermissionError:
            return JSONResponse(status_code=403, content={"error": "Permission denied"})

    # ── Health check ───────────────────────────────────────────────────
    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    # ── Serve SPA: all non-API routes return index.html ────────────────
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"error": "Not found"})
        file_path = static_dir / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(static_dir / "index.html"))

    return app
