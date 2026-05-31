# Roadmap

## v0.2.0

- Add privileged production Ubuntu service installer with dry-run and rollback modes.
- Add real Nginx apply/test/reload workflow from generated config previews.
- Add Let's Encrypt HTTP-01 certificate issue and renewal.
- Add audit logging for every write action.

## v0.3.0

- Add database create/user/backup/restore for MySQL or PostgreSQL.
- Add scheduled backups and restore verification.
- Add browser file manager with strict path-safety tests.
- Add basic user/session authentication for the dashboard.

## v0.4.0

- Add firewall and fail2ban controls.
- Add WordPress/Nextcloud static installer workflows.
- Add Node/Python app deployment using supervised local services.
- Add role-based access control.

## v1.0.0

- Harden command execution and least-privilege service isolation.
- Complete security review and threat model.
- Publish migration guides from cPanel/Plesk/HestiaCP/aaPanel.
- Mark as production-ready only after clean-server install, backup restore,
  auth, SSL, and service management are fully tested.
