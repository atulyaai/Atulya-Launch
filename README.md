# Atulya Launch

![Atulya Launch Banner](assets/atulya-hero.png)

Atulya Launch is an early alpha server-management panel and CLI for self-hosted
websites, APIs, applications, and automation tools. The current product direction
is a lightweight cPanel-style alternative with a Python CLI, optional web API,
and Linux-first server operations.

The project is moving quickly. Treat this repository as alpha software until the
installer, web API, security model, and backup/restore flows have been verified
on clean systems.

## Current Position

| Area | Status | Notes |
| --- | --- | --- |
| Python package | Alpha | Package metadata targets Python 3.9+ and exposes `atulya-launch`. |
| CLI entry point | Available | Run `atulya-launch --help` or `python -m atulya_launch --help`. |
| Server panel direction | In progress | The roadmap targets website, DNS, email, database, SSL, backup, and monitoring workflows. |
| Web/API modules | In progress | FastAPI/web extras are declared as optional dependencies. Verify routes before advertising counts. |
| Install scripts | Planned/experimental | Run installers only on disposable test servers until security review is complete. |
| Security posture | Pre-review | Do not expose publicly without authentication, TLS, backups, least privilege, and audit logging. |

## What It Aims To Manage

- Websites, domains, redirects, reverse proxy configuration, and app deployment.
- DNS zones and DNS records.
- Email accounts, aliases, routing, and webmail integration.
- Databases, users, imports, exports, and scheduled backups.
- SSL/TLS certificates and renewal workflows.
- File management, archives, and basic editing workflows.
- Firewall, fail2ban, SSH policy, antivirus, and security-advisor checks.
- System services, logs, process monitoring, bandwidth, and health metrics.
- Plugin-based extensions such as CMS install, analytics, reseller tools, and automation helpers.

## Install

For local development:

```bash
git clone https://github.com/atulyaai/Atulya-Launch.git
cd Atulya-Launch
python -m pip install -e .
```

With optional web dependencies:

```bash
python -m pip install -e ".[web]"
```

With all declared extras:

```bash
python -m pip install -e ".[all,dev]"
```

## Basic Usage

Show CLI commands:

```bash
atulya-launch --help
```

Run through Python:

```bash
python -m atulya_launch --help
```

Run tests when available:

```bash
pytest tests/ -v
```

Start the web API when the web package is present:

```bash
python -m atulya_launch.web.app
```

Then open the API docs if the server starts successfully:

```text
http://localhost:8080/api/docs
```

## Configuration

Use environment-specific configuration for development and production. Keep
secrets out of git.

Common local files that should remain private:

- `.env`
- `config.local.yaml`
- SSL keys and certificate requests
- database files
- backup archives

## Verification Checklist

Before calling a release production-ready, verify these on a clean machine:

1. Fresh install from git and from packaged artifacts.
2. `atulya-launch --help` exits successfully.
3. Optional web install starts without missing imports.
4. Authentication cannot be bypassed.
5. Default credentials must be rotated on first use.
6. TLS is configured before exposing the panel outside localhost.
7. File manager paths cannot escape allowed directories.
8. Archive extraction blocks path traversal.
9. Backup and restore are tested with real data.
10. Service actions run with least privilege.
11. Logs do not expose secrets.
12. Dangerous operations require confirmation and audit logging.

## Known Gaps To Check

- README route/module counts should be generated from tests or source inspection before being used as release claims.
- Installer commands should be reviewed on fresh Linux, macOS, and Windows/WSL machines.
- Public-facing deployments need a documented threat model.
- Security-sensitive features need tests for path traversal, command injection, secret leakage, auth bypass, CSRF, SSRF, and privilege escalation.
- Optional dependencies and package extras should stay aligned with imports used by the web app and plugins.

## Security And Bug Bounty

Atulya Launch welcomes responsible security reports. This repository does not
currently publish a guaranteed paid bounty table, so rewards are not guaranteed
unless Atulya AI announces a separate paid program.

### In Scope

- Authentication or authorization bypass.
- Remote code execution.
- Command injection.
- Path traversal or arbitrary file read/write.
- Privilege escalation.
- Secret leakage.
- Backup, restore, archive, or file-manager vulnerabilities.
- SSRF, CSRF, XSS, SQL injection, and template injection.
- Insecure default configuration that exposes the panel or credentials.

### Out Of Scope

- Denial-of-service tests against public infrastructure.
- Social engineering, phishing, or physical attacks.
- Automated scanner output without a working exploit or clear impact.
- Reports requiring compromised admin credentials without a privilege boundary impact.
- Issues in third-party services unless Atulya Launch directly causes the vulnerability.

### Reporting

For sensitive reports, use GitHub private vulnerability reporting if it is
enabled for this repository. If that is unavailable, contact the maintainers
through the repository issue tracker with a non-sensitive summary and request a
private disclosure channel.

Please include:

- Affected version or commit.
- Environment and install method.
- Clear reproduction steps.
- Impact and affected security boundary.
- Suggested fix, if known.

Do not publish exploit details until maintainers have had reasonable time to
triage and patch.

## Development Notes

Suggested local checks:

```bash
python -m compileall atulya_launch
python -m atulya_launch --help
pytest tests/ -v
```

Use focused pull requests and include test evidence for security-sensitive
changes.

## License

MIT License. See [LICENSE](LICENSE).
