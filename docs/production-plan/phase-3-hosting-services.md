# Phase 3 - Production Hosting Services

Goal: turn the panel from configuration UI into a real hosting control plane.

## Scope

- BIND DNS apply.
- Nginx/Caddy webserver apply.
- PHP-FPM version switching.
- Postfix/Dovecot mailboxes.
- DKIM and webmail.
- Wildcard SSL and renewals.
- SSH terminal.
- FTP/SFTP.

## Scaffolded Work Items

| ID | Task | Size | Status |
| --- | --- | --- | --- |
| P3-01 | DNS SQLite service and driver apply plan | Small | Done |
| P3-02 | BIND named config writer and `rndc reload` integration | Medium | Todo |
| P3-03 | Nginx config test/apply/reload with rollback | Medium | Todo |
| P3-04 | Caddy config writer for macOS/Windows | Medium | Todo |
| P3-05 | PHP-FPM version detection and site switching | Medium | Todo |
| P3-06 | Postfix virtual mailbox map writer | Large | Todo |
| P3-07 | Dovecot mailbox/auth config writer | Large | Todo |
| P3-08 | DKIM key generation and DNS TXT apply | Medium | Todo |
| P3-09 | Webmail router backed by real mail domains | Medium | Todo |
| P3-10 | Wildcard SSL DNS-01 issue/renew/install flow | Large | Todo |
| P3-11 | SSH terminal backend with session audit | Large | Todo |
| P3-12 | xterm.js frontend terminal | Medium | Todo |
| P3-13 | SFTP-first account isolation | Large | Todo |

## Service Safety Rules

- Validate config before reload.
- Write new config beside old config first.
- Keep rollback path for each service.
- Audit every write/reload action.
- Return actionable UI/API errors.

## Acceptance Criteria

- A clean Ubuntu host can serve one domain with DNS, web, PHP, SSL, database,
  mail, backup, and restore.
- Failed service reloads keep the previous working configuration.
- SSH terminal sessions are authenticated, audited, and permission-scoped.

## Test Hooks

- Future integration tests with dry-run drivers.
- Future clean-host smoke script.
- Future service fixture tests for BIND, Nginx, Postfix, Dovecot, Caddy.
