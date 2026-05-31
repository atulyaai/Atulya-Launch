# Atulya Launch Production Roadmap

Atulya Launch is moving from a wired control-panel prototype toward a production
cPanel/Plesk/HestiaCP/aaPanel replacement. The fastest work is intentionally
front-loaded; heavier daemon integrations and enterprise packaging come later.

## Current Truth

- The FastAPI panel, auth, sessions, audit log, templates, CLI, installer, and
  many feature APIs exist.
- The app currently registers the API router surface successfully.
- The most important missing work is production integration: writing service
  configs, reloading daemons, consolidating JSON-backed modules into SQLite, and
  hardening installers.
- Production-ready status must wait until clean-server installs, service reloads,
  migration restore, SSL, DNS, mail, and backup recovery are tested end to end.

## Phase 1 - Fast Fixes And Wiring

Goal: make the existing code reliable and reachable.

- Keep all `web/api` routers import-safe and mounted.
- Fix import crashes, route conflicts, and signature mismatches.
- Move login rate limiting to persistent SQLite storage.
- Add CSRF enforcement for cookie-authenticated write requests.
- Add flash message storage and render messages in all form templates.
- Remove default-admin assumptions from production paths.
- Add tests for every mounted router returning either success, auth failure, or a
  typed validation error instead of 404/import failure.

Exit criteria:

- Full test suite passes on Windows and Linux.
- App startup reports zero router import errors.
- Basic site, database, DNS, email, SSL, backup, and login flows work locally.

## Phase 2 - Platform Driver Layer

Goal: stop spreading Linux/macOS/Windows decisions across feature modules.

- Use `atulya_launch.drivers` as the single OS integration boundary.
- Linux driver: systemd, apt, Nginx, BIND, Postfix, Dovecot.
- macOS driver: launchd, Homebrew, Caddy-first web serving.
- Windows driver: Windows services, winget, Caddy-first web serving.
- Add dry-run plans for package install, service reload, web config, DNS zone
  apply, and mail map apply.
- Add Docker fallback for services that are not native on macOS/Windows.

Exit criteria:

- Feature code calls drivers, not raw `/etc/*`, `systemctl`, `launchctl`, or
  `sc.exe` directly.
- Dry-run output explains exactly what would be changed.
- Driver tests cover Linux, macOS, and Windows plans.

## Phase 3 - Production Hosting Services

Goal: make the panel actually operate hosting services.

- DNS: render BIND zone files, update named config, run `rndc reload`, validate
  serial handling, and expose apply status in the UI.
- Mail: render Postfix virtual maps, Dovecot mailbox config, DKIM keys, webmail
  config, and safe reload/restart operations.
- Web: finalize Nginx Linux driver, Caddy macOS/Windows driver, Apache-compatible
  import/migration mode, PHP-FPM version switching, and config test before reload.
- SSH terminal: implement async backend plus xterm.js frontend with session
  auditing and permission checks.
- SSL: production wildcard DNS-01 flow, renewal scheduler, install tracking, and
  reload hooks.
- FTP/SFTP: integrate real daemon config or explicit SFTP-only mode.

Exit criteria:

- A clean Ubuntu server can host a domain with DNS, web, SSL, mail, database,
  backup, and restore from the panel.
- Failed daemon operations return clear UI/API errors and leave old configs intact.

## Phase 4 - Operator UX

Goal: make the panel feel trustworthy for daily operations.

- Add flash messages/toasts for every form and long-running action.
- Add SSE or polling-backed live dashboard metrics.
- Improve file manager ergonomics: upload progress, editor, permissions, archive
  extract/compress, and safe previews.
- Add global command search.
- Add mobile navigation polish and responsive table handling.
- Add activity/audit feed with filters.
- Add dark/light mode only after the core screens are consistent.

Exit criteria:

- Operators can understand success/failure without reading logs.
- Common hosting workflows take fewer clicks than cPanel/Plesk equivalents.

## Phase 5 - Enterprise And Packaging

Goal: ship and maintain this as a real production product.

- Linux/macOS/Windows one-command installers with dry-run and rollback.
- Docker Compose production stack for panel + database + optional service
  containers.
- Scoped API v1 tokens for automation and integrations.
- Reseller billing hooks and plan enforcement across sites, DBs, mailboxes,
  storage, and bandwidth.
- Notifications: email, webhook, Slack-compatible webhook.
- Prometheus metrics and health endpoints.
- Self-update UI with signed release verification.
- Migration guides and importers for cPanel, Plesk, HestiaCP, and aaPanel.

Exit criteria:

- Release artifacts can install, update, roll back, and recover on clean hosts.
- Security review covers auth, CSRF, SSRF, command execution, file manager,
  backup/restore, migration imports, and service privilege boundaries.

## Priority Order

1. Router health, CSRF, flash messages, default-credential hardening.
2. SQLite consolidation for JSON-backed feature modules.
3. Driver layer adoption in DNS, web, mail, SSL, and service-control modules.
4. SSH terminal.
5. BIND and Nginx production apply with rollback.
6. Postfix/Dovecot/DKIM/webmail production apply.
7. Wildcard SSL and renewals.
8. Installer hardening and Docker Compose production stack.
9. Enterprise APIs, metrics, billing hooks, notifications, self-update.

## Never Claim Production Ready Until

- Clean Ubuntu install succeeds without manual fixes.
- Backup restore has been tested on a second clean host.
- DNS, mail, SSL, web, DB, SSH, and file manager flows are all integration-tested.
- Default credentials are impossible in production mode.
- All write actions are audited.
- Destructive operations have confirmation, rollback, or dry-run plans.
