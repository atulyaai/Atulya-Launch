# Changelog

## v1.0.0 (2026-05-31)

### Production Hardening
- Rate limiter on login (5 attempts/5min per IP, 429 response).
- Account lockout (10 failed attempts/15min per username).
- Password policy enforcement (min 8 chars, uppercase+lowercase+digit).
- Max 5 concurrent sessions per user (oldest evicted).
- Session cleanup on page load.
- Global exception handler (no stack traces, `PANEL_DEBUG` env var).
- `safe_write()` with umask 022 and chmod on Linux.
- Database schema versioning (`schema_version` table, `SCHEMA_VERSION=2`).
- `sanitize_filename()` with path traversal prevention.
- Secure cookie attributes (httponly, samesite=lax, secure with `PANEL_HTTPS`).
- Graceful CLI serve with `--workers`, `--https`, `--log-level`, `proxy_headers=True`, `server_header=False`.
- `PANEL_HOST`, `PANEL_PORT`, `PANEL_WORKERS`, `PANEL_HTTPS`, `PANEL_DEBUG`, `ADMIN_PASS` env vars.

### v0.3.0 Features
- cPanel/Plesk/HestiaCP migration import via file upload.
- Reseller plans with site/disk/DB/email/bandwidth limits.
- Plan assignment to users with limit enforcement.
- WordPress one-click installer with optional DB auto-creation.
- Panel branding (custom name, primary color) stored in DB.

### v0.4.0 Features
- Node.js/Python app deployment with Nginx reverse proxy.
- Process start/stop management.
- Cron job CRUD with toggle enable/disable.

### v1.0.0 Features
- Comprehensive security audit (firewall, Fail2Ban, Nginx, default users, bind address).
- Load testing tool with concurrent request execution.
- Multi-server management via SSH (password/key auth).
- Remote command execution.
- Log viewer with source selection, line count, grep filtering.
- Branding/white-label (panel name, color) persisted in settings.

### Infrastructure
- Extended SQLite schema: plans, user_plans, cron_jobs, migrations, node_apps, servers, branding tables.
- 28 new tests covering all new features (96 total, all passing).
- All new modules registered in FastAPI app with API endpoints.

## v0.2.0 (2026-05-31)

### Web Panel
- Added FastAPI-based web dashboard with login/session auth.
- Added dark-themed responsive UI with sidebar navigation.
- Added bearer token API authentication.
- Added protected GET endpoints (all pages require login).

### Website Management
- Added Nginx config apply/test/reload workflow (Linux).
- Added reverse proxy and PHP-FPM support.

### DNS Management
- Added DNS zone create/delete.
- Added DNS record management (A, AAAA, CNAME, MX, TXT, NS, SRV).

### Email Management
- Added email account create/delete with password hashing.
- Added quota management.

### Database Management
- Added MySQL/MariaDB/PostgreSQL create/drop/backup via CLI and web.
- Added database tracking in SQLite.

### SSL/TLS
- Added Let's Encrypt certificate issuance via Certbot.
- Added certificate renewal and tracking.

### File Manager
- Added web-based file browser with upload, mkdir, delete.
- Added breadcrumb navigation.

### Backup System
- Added zip archive creation with config + webroots.
- Added backup restore from web UI.

### Monitoring
- Added live CPU/RAM/disk/network metrics.
- Added top processes view.
- Added service status display.
- Added 30-second auto-refresh.

### Firewall & Security
- Added UFW enable/disable/allow/deny.
- Added Fail2Ban status and restart.
- Added security scan with scoring.

### Docker Management
- Added one-click container deployment (10 apps).
- Added container start/stop/remove.
- Added image listing.

### App Installer
- Added WordPress, Nextcloud, Laravel, Ghost, Flask, Django templates.

### Multi-User / RBAC
- Added user creation with admin/user roles.
- Added password change with verification.
- Added admin-only user management.

### CLI
- Added `database create/drop/backup` commands.
- Added `ssl issue/renew` commands.
- Added `firewall status/ufw-enable/ufw-disable/allow/deny` commands.

### Production Installer
- Added `scripts/install-server.sh` for clean Ubuntu servers.
- Installs Python 3.11, Nginx, MySQL, PHP-FPM, Certbot, UFW, Fail2Ban, Docker.
- Creates systemd service for auto-start.

### Testing
- Added 59 tests (up from 10).
- Added auth, database, web, and extended core tests.

## v0.1.0 (2026-05-27)

- Initial alpha launcher CLI.
- Added `atulya-launch` console entry point and `python -m atulya_launch` module entry point.
- Added tool catalog commands for listing supported Atulya tools and showing individual tool information.
- Added pip-based install, uninstall, self-update, and GitHub release checks.
- Added local checkout install support for Atulya tools.
- Added hosting-panel MVP commands for panel initialization, system status, site records, Nginx config previews, backup archives, and security checks.
- Added a local stdlib dashboard/API server with bearer-token protected write endpoints.
- Added unittest coverage for panel initialization, site creation, backup creation, and security scanning.
