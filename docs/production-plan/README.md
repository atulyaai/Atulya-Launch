# Production Plan Scaffold

This folder turns the roadmap into executable engineering phases. Each phase is
ordered from fastest/highest-leverage work to slower production integration.

## Phase Index

| Phase | Focus | Output |
| --- | --- | --- |
| [Phase 1](phase-1-foundation.md) | Reliability, auth, router wiring, SQLite cleanup | Stable panel base |
| [Phase 2](phase-2-platform-drivers.md) | Linux/macOS/Windows driver boundary | OS-safe integration layer |
| [Phase 3](phase-3-hosting-services.md) | DNS, mail, web, SSL, SSH, FTP/SFTP | Real hosting service control |
| [Phase 4](phase-4-operator-ux.md) | Feedback, live UI, file manager, search | Daily-use operator experience |
| [Phase 5](phase-5-enterprise-packaging.md) | Installers, Docker, API, metrics, billing | Shippable production product |

## Working Rule

Do phases sequentially unless a bug blocks users. Each phase should leave behind:

- Code behind a stable module boundary.
- Tests for the new boundary.
- Dry-run behavior for destructive or privileged operations.
- Clear UI/API errors for failed operations.
- Roadmap status updates when scope changes.

## Production Claim Rule

Do not label Atulya Launch production-ready until Phase 5 exit criteria pass on a
clean host and backup restore is verified on a second clean host.
