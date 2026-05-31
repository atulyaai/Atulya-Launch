# Phase 5 - Enterprise And Packaging

Goal: make Atulya Launch installable, maintainable, observable, and extensible.

## Scope

- One-command installers.
- Docker Compose production stack.
- Scoped API tokens.
- Reseller enforcement and billing hooks.
- Notifications.
- Prometheus metrics.
- Self-update.
- Migration importers.
- Security review.

## Scaffolded Work Items

| ID | Task | Size | Status |
| --- | --- | --- | --- |
| P5-01 | Linux/macOS/Windows installer dry-runs | Medium | Started |
| P5-02 | Installer rollback and uninstall plan | Large | Todo |
| P5-03 | Docker Compose production stack | Medium | Todo |
| P5-04 | Scoped API v1 tokens | Medium | Todo |
| P5-05 | Reseller limit enforcement across all resources | Large | Todo |
| P5-06 | Billing webhook hooks | Medium | Todo |
| P5-07 | Email/webhook/Slack-compatible notifications | Medium | Todo |
| P5-08 | Prometheus metrics endpoint | Medium | Todo |
| P5-09 | Self-update UI with signed releases | Large | Todo |
| P5-10 | cPanel migration importer | Large | Todo |
| P5-11 | Plesk migration importer | Large | Todo |
| P5-12 | HestiaCP migration importer | Medium | Todo |
| P5-13 | aaPanel migration importer | Medium | Todo |
| P5-14 | Full threat model and security audit | Large | Todo |

## Packaging Policy

- Installers must support dry-run.
- Installers must print generated credentials once and force rotation.
- Production install must not bind publicly unless explicitly requested.
- Updates must be reversible or at least backup-aware.

## Acceptance Criteria

- Clean install works on supported Linux target.
- macOS/Windows dev install works with Caddy fallback.
- Docker Compose stack starts from a clean checkout.
- Backup restore succeeds on a second clean host.
- Metrics, health checks, logs, and update status are visible.

## Test Hooks

- `tests/test_installer.py`
- Future installer smoke tests.
- Future Docker Compose smoke tests.
- Future migration fixture tests.
