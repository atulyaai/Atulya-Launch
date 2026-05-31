# Phase 2 - Platform Drivers

Goal: make Linux, macOS, and Windows support real by moving privileged operations
behind a driver layer.

## Scope

- Service manager abstraction.
- Package manager abstraction.
- Webserver abstraction.
- DNS backend abstraction.
- Mail backend abstraction.
- Dry-run plans for privileged writes.

## Scaffolded Modules

| Module | Purpose | Status |
| --- | --- | --- |
| `atulya_launch/drivers/base.py` | Protocols and result types | Done |
| `atulya_launch/drivers/common.py` | Shared dry-run command/file drivers | Done |
| `atulya_launch/drivers/linux.py` | systemd, apt, Nginx, BIND, Postfix, Dovecot | Scaffolded |
| `atulya_launch/drivers/macos.py` | launchd, Homebrew, Caddy | Scaffolded |
| `atulya_launch/drivers/windows.py` | Windows services, winget, Caddy | Scaffolded |
| `atulya_launch/drivers/registry.py` | Select driver by OS | Done |

## Scaffolded Work Items

| ID | Task | Size | Status |
| --- | --- | --- | --- |
| P2-01 | Add driver contracts and registry | Small | Done |
| P2-02 | Add Linux dry-run plans | Small | Done |
| P2-03 | Add macOS dry-run plans | Small | Done |
| P2-04 | Add Windows dry-run plans | Small | Done |
| P2-05 | Replace raw DNS reload with DNS driver | Small | Done |
| P2-06 | Replace raw Nginx writes/reloads with web driver | Medium | Todo |
| P2-07 | Replace raw mail writes/reloads with mail driver | Medium | Todo |
| P2-08 | Add Docker fallback driver for non-native services | Large | Todo |
| P2-09 | Add rollback plan objects for destructive changes | Large | Todo |

## Driver Policy

- Feature modules should not call `systemctl`, `launchctl`, `sc.exe`, `rndc`,
  or write `/etc/*` directly.
- Production writes must support dry-run first.
- A driver result must report files, commands, changed state, and failure message.

## Acceptance Criteria

- DNS, webserver, mail, SSL, and service-control modules call drivers only.
- Dry-run output is visible from API responses or logs.
- Linux/macOS/Windows driver tests pass without requiring elevated privileges.

## Test Hooks

- `tests/test_drivers.py`
- `tests/test_dns_service.py`
- Future: `tests/test_webserver_driver.py`
- Future: `tests/test_mail_driver.py`
