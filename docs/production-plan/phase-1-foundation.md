# Phase 1 - Foundation

Goal: make the existing panel reliable, reachable, and safe enough to build on.

## Scope

- Router registration and import safety.
- Auth/session correctness.
- CSRF protection.
- Persistent rate limiting.
- Flash messages.
- SQLite as the primary source of truth.
- Default credential hardening.

## Scaffolded Work Items

| ID | Task | Size | Status |
| --- | --- | --- | --- |
| P1-01 | Register all import-safe `web/api` routers in `web/app.py` | Small | Done |
| P1-02 | Fix API import crashes such as stale password helper names | Small | Done |
| P1-03 | Add `/api/router-status` for registration visibility | Small | Done |
| P1-04 | Move rate limits from process memory to SQLite | Small | Done |
| P1-05 | Enforce CSRF for cookie-authenticated write requests | Small | Started |
| P1-06 | Add flash message helpers and template rendering | Medium | Todo |
| P1-07 | Convert remaining JSON-backed modules to SQLite | Medium | Started with DNS |
| P1-08 | Block default `admin/admin` in production mode | Medium | Todo |
| P1-09 | Add router smoke tests for 404/import regression | Medium | Todo |

## Implementation Notes

- Keep `web/database.py` as the SQLite migration boundary.
- Keep auth/session helpers in `web/auth.py`.
- Keep route mounting in `web/app.py`.
- For every JSON-backed API module, create a service module first, then move the
  route to that service. DNS uses `web/dns_service.py` as the pattern.

## Acceptance Criteria

- `python -m unittest discover -s tests` passes on Windows and Linux.
- App startup has zero router import errors.
- Login, logout, dashboard, site list, DNS list, and API token login work.
- No state-changing cookie-authenticated route accepts requests without CSRF.
- Production mode refuses default credentials.

## Test Hooks

- `tests/test_web.py`
- `tests/test_auth.py`
- `tests/test_database.py`
- Future: `tests/test_router_status.py`
- Future: `tests/test_flash_messages.py`
