# Atulya Launch Production Roadmap

Atulya Launch is moving toward a production cPanel/Plesk/HestiaCP/aaPanel
replacement. The feature set is largely in place; the remaining work is
host-level integration testing, security review, and packaging.

Detailed phase scaffolds live in [docs/production-plan](docs/production-plan/README.md).

## Current Truth (as of v1.1.1)

- **628 mounted routes** across 94 API modules and 27 page routers; OpenAPI 3.1
  spec at `/api/openapi.json`. All 152 tests passing.
- **AI**: predictive health engine (`/api/ai/predict`, `/api/ai/history`,
  `/api/ai/automate`) plus a natural-language command layer (`/api/ai/command`)
  that parses free-text ops ("create a WordPress site example.com with Redis
  cache and SSL") into an ordered, dry-runnable plan over the core APIs.
- **Auth**: PBKDF2-SHA256 (200k iter), session cookies, bearer tokens, 2FA (TOTP),
  rate limiting, account lockout, password policy, login history, IP allow/deny.
- **2FA**: single unified SQLite store (`web/twofa_store.py`) shared by the
  login challenge, settings page, and API.
- **Audit**: JSONL audit log + audit page; every write action recorded.
- **Driver layer**: `drivers/` exists with Linux/macOS/Windows shells plus
  `common.py` (apt/dnf/pacman/brew/choco, systemd/launchd/sc) and a real
  `mail_service.py` driver.
- **AI operations**: `ai/predictive.py` predictive-health engine with trend
  forecasting, risk scoring, and safe automated actions
  (`/api/ai/predict`, `/api/ai/history`, `/api/ai/automate`).
- **Service code (real, not planned)**:
  - Mail: `web/mail_service.py` + `drivers/mail_service.py` write Postfix
    `main.cf`, Dovecot `dovecot.conf`, vmailbox maps, passwd file, DKIM keys.
  - DNS: `web/dns_service.py` + BIND zone template + `BindDnsDriver`, plus
    DNSSEC management (`/api/dnssec`).
  - Sites: `web/sites_service.py` + `FileWebServerDriver` for Nginx vhosts;
    addon domains and site publisher on top.
  - Email auth: SPF/DMARC manager (`/api/email-auth`) with DNS TXT sync.
  - SSL: `web/api/letsencryptwildcard.py` (DNS-01) + standard certbot flow.
  - SSH terminal: `web/api/sshterminal.py` (asyncssh + WebSocket PTY).
- **Installer**: `scripts/install-server.sh` (272 lines) installs Python 3.11,
  Nginx, MySQL, PHP-FPM 8.1/8.2/8.3, Certbot, ModSecurity + OWASP CRS, UFW,
  Fail2Ban, Docker; creates systemd unit. Untested on a clean host.
- **Plugins shipped**: reseller (plans/limits/branding), webmail, antivirus,
  cms_installer, security_advisor, analytics.
- **WHM-style controls**: feature groups + per-user overrides and an IP pool
  (`/api/feature-manager`).
- **macOS/Windows drivers**: 1.4 KB dataclass shells only — not implemented.
- **Driver consolidation**: feature modules still call `utils.run_command`
  directly in places instead of going through the driver layer.

## Phase 1 - Clean-Host Install Validation  **(current focus)**

Goal: prove the installer + every Phase 3 service works end-to-end on a fresh
Ubuntu 22.04/24.04 VM with no manual intervention.

- Add `scripts/validate-install.sh` that boots a clean LXC/VM, runs
  `install-server.sh`, then exercises: create site → enable site → issue cert
  → create mailbox → create DB → write backup → restore backup → reload Nginx.
- Run the validation script in CI on every release tag.
- Capture logs and exit codes into a `validation-report.md`.
- Add an `INSTALL_VALIDATED.md` badge once a clean install passes twice in a row.

Exit criteria:

- `bash scripts/validate-install.sh` exits 0 on Ubuntu 22.04 and 24.04.
- All 9 validation steps pass without manual steps.
- Validation report is committed to the repo for each release.

## Phase 2 - Driver Layer Consolidation

Goal: stop the dual-track (planned driver ops vs real `*_service.py` code).

- Refactor `web/dns_service.py`, `web/sites_service.py`, `web/mail_service.py`
  to call `LinuxDriver.dns`, `LinuxDriver.web`, `LinuxDriver.mail` instead of
  `utils.run_command`.
- Move `drivers/mail_service.py` content into `LinuxDriver.mail` methods.
- Add `apply(plan)` and `rollback(plan)` on every driver with state tracking.
- Add driver tests for: dry-run plan output, idempotency, failed-reload
  rollback.
- Document the driver contract in `docs/production-plan/driver-contract.md`.

Exit criteria:

- No `subprocess.run`, `utils.run_command`, `os.system` outside `drivers/`.
- Each driver has a rollback test that restores previous config.
- Driver contract doc published.

## Phase 3 - macOS + Windows Drivers

Goal: make the panel installable on macOS (dev/Caddy) and Windows (winget/Caddy).

- macOS: `brew install nginx caddy postgresql redis` flow, `launchd` plist for
  the panel, AppleScript notifications.
- Windows: `winget install` flow, `sc.exe` service for the panel, NSSM wrapper
  for nginx/caddy.
- Docker fallback when native services are unavailable.
- Per-OS install scripts in `scripts/install-{macos,windows}.{sh,ps1}`.

Exit criteria:

- `scripts/install-macos.sh` brings up a working panel on macOS 14+.
- `scripts/install-windows.ps1` brings up a working panel on Windows 11.

## Phase 4 - Security + Release Hardening

Goal: ship signed releases and pass an external security review.

- Self-update with `minisign`/cosign signature verification.
- Security audit covering: CSRF, SSRF, command injection, file-manager
  traversal, backup archive extraction, migration imports, service privilege
  boundaries, default-cred rejection in production mode.
- `PANEL_PRODUCTION=1` mode that refuses to start with `admin/admin` and
  binds to 127.0.0.1 by default.
- SBOM (CycloneDX) + CVE scanning in CI.
- Threat model document in `docs/security/threat-model.md`.

Exit criteria:

- `make release` produces signed artifacts with SBOM.
- Security review checklist signed off.

## Phase 5 - Operator UX Polish

Goal: match or beat cPanel/Plesk click-counts for common workflows.

- Flash messages/toasts on every form.
- SSE or websocket live metrics (replace 30s polling).
- File manager: upload progress, in-browser editor, archive extract/compress,
  safe previews.
- Global command search (`/` to jump).
- Activity/audit feed with filters.
- Mobile nav polish + responsive tables.
- Dark/light mode toggle.

Exit criteria:

- Operator workflows (create site, issue cert, create mailbox, restore backup)
  take fewer clicks than cPanel equivalents.

## Phase 6 - Enterprise + Ecosystem

Goal: make this viable for hosting providers and integrators.

- Docker Compose production stack: panel + Postgres + optional service
  containers.
- Scoped API v1 tokens (`/api/v1/...`) with OpenAPI 3.1 spec.
- Notifications: email, webhook, Slack-compatible.
- Prometheus `/metrics` + health endpoints.
- Reseller billing hooks + plan enforcement.
- Migration guides + importers for cPanel, Plesk, HestiaCP, aaPanel (round-trip
  tested).
- Plugin registry + signed plugin manifests.

Exit criteria:

- Release artifacts install, update, roll back, recover on clean hosts.
- A second-host restore drill is documented and CI-runnable.

## Phase 7 - AI Operations ***(2 slices shipped in v1.1.0/v1.1.1)***

Goal: make the panel an "AI-native hosting control panel" that predicts and
self-heals, on top of the existing driver/audit/API foundations.

- [x] Predictive health engine (`ai/predictive.py`): sampling → history →
      linear-trend forecast → risk scoring → suggested + safe automated
      actions (`/api/ai/predict`, `/api/ai/history`, `/api/ai/automate`).
- [x] Natural-language command layer (`ai/nlcommand.py`): "create a WordPress
      site example.com with Redis caching and SSL" → parsed `Intent` →
      ordered auditable `Plan` → dry-run review → approved apply via
      `/api/ai/command`. Reuses the existing sites/rediscache/database/SSL
      core APIs. Optional Tantra-LLM enrichment; deterministic without it.
- [ ] Log-based diagnostics: feed `/api/logs` + `/api/errorlogs` into an
      LLM analysis to produce root cause + one-click fix.
- [ ] Auto-optimizer: nginx/php-fpm tuning proposals from `bandwidth` and
      `resourcehistory` trends.
- [ ] Learning backup scheduler: learn low-usage windows and propose/shift
      backup times from the `backup` event history.
- [ ] LLM provider abstraction (Tantra-LLM first, OpenAI-compatible fallback)
      with per-action approvals and full audit logging.

Exit criteria:

- Every AI action is auditable and reversible (rollback via driver layer).
- Destructive AI actions require operator approval; only safe automations
  (backup rotation/log cleanup) run unattended.
- AI endpoints continue to work with zero external AI dependencies installed.

## Priority Order (updated)

1. **Clean-host install validation** (Phase 1) — gate everything else.
2. Driver consolidation (Phase 2) — remove code-duplication risk.
3. Security review + signed releases (Phase 4) — needed before public launch.
4. Operator UX (Phase 5) — needed for daily-use credibility.
5. **AI Operations (Phase 7)** — differentiator; 2 slices already shipped.
6. macOS/Windows drivers (Phase 3) — nice-to-have, not blocker.
7. Enterprise + ecosystem (Phase 6) — post-launch.

## Never Claim Production Ready Until

- [ ] `scripts/validate-install.sh` passes on Ubuntu 22.04 + 24.04 clean VMs.
- [ ] Backup restore has been tested on a second clean host.
- [ ] DNS, mail, SSL, web, DB, SSH, and file manager flows are integration-tested.
- [ ] Default credentials are impossible in `PANEL_PRODUCTION=1` mode.
- [ ] All write actions are audited.
- [ ] Destructive operations have confirmation + dry-run + rollback.
- [ ] Security review checklist is signed off.
- [ ] Releases are signed and reproducible.
