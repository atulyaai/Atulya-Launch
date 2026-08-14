# Changelog

## v1.1.0 (2026-08-15)

### Reliability & Cross-Platform Fixes
- `/api/health` no longer crashes on Windows: `os.getloadavg()` is guarded and
  service checks skip `systemctl` on non-Linux platforms.
- `PhpFpmDriver.status()` returns the service status instead of nothing;
  removed dead code left in `PlannedFirewallDriver.list_rules`.
- Replaced all ~85 `datetime.utcnow()` calls with
  `datetime.now(timezone.utc).replace(tzinfo=None)` (17 files) — zero
  deprecation warnings on 3.12+.

### Unified Two-Factor Authentication
- New `web/twofa_store.py` — a single SQLite-backed store for secrets, enabled
  state, pending setup, and backup codes.
- `core.twofa_*`, `web/auth`, and `web/api/twofa.py` all delegate to it,
  removing the previous divergence across `config.json`, `twofa.json`, and the
  per-module SQLite reads. Login challenge and settings/API now agree.

### New Feature Modules
- `web/api/dnssec.py` — enable/disable/resign DNSSEC, key tag + DS records.
- `web/api/addondomains.py` — addon domains with dedicated document root,
  site + DNS zone registration.
- `web/api/sitepublisher.py` — Coming Soon / Landing / Maintenance pages
  written to `index.html`.
- `web/api/emailauth.py` — SPF/DMARC defaults, upsert, and DNS TXT auto-sync.
- `web/api/featuremanager.py` — WHM-style feature groups, per-user overrides,
  and a dedicated IP pool.
- `web/api/v1.py` — versioned `/api/v1/meta` + `/api/v1/health`;
  OpenAPI 3.1 schema served at `/api/openapi.json`.
- New SQLite tables: `dnssec_zones`, `addon_domains`, `site_publisher`,
  `email_auth_records`, `feature_groups`, `ip_allocations`,
  `ai_metric_history`.

### AI Operations
- `atulya_launch/ai/predictive.py` — metric sampling, rolling SQLite history,
  linear-trend forecast, risk scoring, suggested + safe automated actions.
- `web/api/aipredict.py` — `/api/ai/predict`, `/api/ai/history`,
  `/api/ai/automate`. Optional Tantra-LLM enrichment when installed.

### Tests & Docs
- 16 new tests in `tests/test_new_features.py` covering AI prediction,
  DNSSEC, addon domains, site publisher, SPF/DMARC, feature manager, IP pool,
  unified 2FA, and the v1 API.
- **Total: 140 tests passing** (was 124).
- `README.md` refreshed: accurate route/test counts, new feature sections,
  updated architecture and test matrix.

## v1.0.1-validate (unreleased)

### Phase 2 - Driver Layer Consolidation
- Added `DatabaseDriver`, `SslDriver`, `FirewallDriver` protocols to `drivers/base.py`.
- Added `test_config()` and `detect()` to `WebServerDriver`.
- New implementations in `drivers/common.py`:
  - `PlannedDatabaseDriver` (mysql/postgres create/drop/backup)
  - `PlannedSslDriver` (certbot issue/renew with staging flag)
  - `PlannedFirewallDriver` (ufw status/enable/disable/allow/deny/list_rules)
- `LinuxDriver` now exposes `databases`, `ssl`, `firewall` alongside the existing drivers.
- `core.py` refactored: `nginx_apply_and_reload`, `database_create/drop/backup`,
  `ssl_issue_letsencrypt/renew`, `firewall_status/list_rules/enable/disable/allow/deny`,
  `fail2ban_restart`, `service_state`, `detect_web_server` now route through
  `get_platform_driver()` instead of calling `subprocess`/`run_command` directly.
  Public signatures are unchanged.
- `drivers/mail_service.py` (Postfix/Dovecot/DKIM) now uses
  `driver.services.reload/restart` for all systemd/launchd interactions.
- 15 new driver tests added (DB plans, SSL plans with/without staging,
  firewall allow/deny/enable, webserver `test_config`/`detect`).
- Total test count: 124 (was 109), all passing.

### Clean-Host Install Validator
- `scripts/validate-install.sh`: 380-line validator that runs on a clean Ubuntu
  host and exercises the full hosting lifecycle: site create -> DNS zone ->
  SSL cert (staging) -> mailbox -> database -> backup -> restore -> security
  audit -> SSH terminal. Writes a markdown report to `/tmp/atulya-validate-report.md`.
- Validated against the real FastAPI route surface; all 16 endpoints the
  validator calls are mounted.

### GitHub Actions
- `.github/workflows/ci.yml`: matrix CI on Ubuntu 22.04/24.04 x Python 3.11/3.12,
  runs lint + unit tests on every push and PR.
- `.github/workflows/validate-install.yml`: full clean-host install + lifecycle
  validator on `release: published`, weekly cron, and PRs touching install
  scripts. Uploads `validation-report.md` as artifact, comments back on
  release/PRs.

### Documentation
- `README.md` status block and v1.0.0 feature list updated to match the real
  state of the codebase (596 routes, 87 API modules, 109+ tests).
- `ROADMAP.md` rewritten with 6 phases matching actual gaps. Clean-host
  install validation is now Phase 1 (gate to everything else).

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
