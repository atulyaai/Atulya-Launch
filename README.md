# Atulya Launch

**Lightweight cPanel alternative — one-click server management with < 50MB RAM idle.**

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://python.org)

---

## Why Atulya Launch?

| Feature | cPanel | Atulya Launch |
|---------|--------|---------------|
| RAM idle | ~500MB+ | **< 50MB** |
| Install time | 30+ min | **< 2 min** |
| Price | $15-45/mo | **Free (MIT)** |
| Web dashboard | Yes | Yes (dark theme) |
| Website management | Yes | Yes |
| DNS management | Yes | Yes (BIND9) |
| Email | Yes | Yes (Postfix+Dovecot) |
| File manager | Yes | Yes |
| Databases | Yes | Yes (MySQL+PostgreSQL) |
| SSL/TLS | Yes | Yes (Let's Encrypt) |
| Backups | Yes | Yes (scheduled) |
| Firewall | Yes | Yes (UFW/iptables) |
| Cron jobs | Yes | Yes |
| App installer | Yes (Softaculous) | Yes (WordPress, etc) |
| System monitor | Yes | Yes (live WebSocket) |

## One-Click Install

```bash
curl -sSL https://raw.githubusercontent.com/atulyaai/Atulya-Launch/main/scripts/install.sh | bash
```

### Install Options

```bash
# Full install (everything)
curl -sSL https://get.atulya.dev | bash -s -- --full

# Minimal install (skip email/DNS)
curl -sSL https://get.atulya.dev | bash -s -- --minimal

# Custom port
curl -sSL https://get.atulya.dev | bash -s -- --port 9090
```

After install, access the panel at: **https://your-server:8443**

## Quick Start

### Web Panel (Recommended)

```bash
# Install with web dependencies
pip install atulya-launch[web]

# Start the panel
python -m atulya_launch --web --port 8443
```

### CLI Mode

```bash
pip install atulya-launch

# Initialize
atulya-launch init

# Manage sites
atulya-launch site create example.com
atulya-launch site list

# Manage databases
atulya-launch db create mydb --type mysql

# SSL certificates
atulya-launch ssl issue example.com --email admin@example.com

# System monitoring
atulya-launch monitor status
atulya-launch monitor processes
```

## Features

### Website Management
- Create/delete/enable/disable websites
- Nginx and Apache support
- PHP-FPM integration
- Reverse proxy support
- Auto-generated configs

### DNS Management (BIND9)
- DNS zone creation
- A/AAAA/CNAME/MX/TXT/NS records
- Zone reload

### Email (Postfix + Dovecot)
- Email account creation
- Aliases and forwarders
- Password management
- IMAP/POP3 support

### Database Management
- MySQL and PostgreSQL
- Auto-generated credentials
- Backup and restore
- phpMyAdmin integration

### SSL/TLS
- Let's Encrypt via Certbot
- Auto-renewal
- Custom certificate install
- Wildcard support

### File Manager
- Directory browsing
- File upload (drag & drop)
- Create/delete/rename
- Permission management
- Download files

### Backups
- Full system backup
- Database backup
- Scheduled backups (cron)
- Restore from backup

### Firewall
- UFW/iptables management
- Port allow/deny rules
- Rule CRUD

### Cron Jobs
- Add/edit/delete cron jobs
- Enable/disable jobs
- Standard cron syntax

### App Installer (One-Click)
- WordPress
- Nextcloud
- Gitea
- Ghost
- MinIO
- n8n
- Uptime Kuma
- Vaultwarden

### System Monitor
- CPU/RAM/Disk usage
- Process list with kill
- System log viewer
- Live WebSocket streaming

### Security
- JWT authentication
- bcrypt password hashing
- Fail2ban integration
- Rate limiting
- Security headers

## Architecture

```
atulya_launch/
  cli.py          - CLI (27 commands)
  core.py         - Business logic
  utils.py        - Utilities
  web/
    app.py        - FastAPI application
    auth.py       - JWT authentication
    api/          - 13 REST API modules
    static/       - SPA dashboard (HTML/JS/CSS)
  templates/      - Config templates (Nginx, BIND9, Postfix, etc.)
scripts/
  install.sh      - One-click installer (700 lines)
```

## Requirements

- Python 3.9+
- Linux (primary target)
- 512MB+ RAM
- 1GB+ disk space

### System Dependencies (auto-installed)

- Nginx or Apache
- BIND9 (DNS)
- MySQL/MariaDB or PostgreSQL
- Postfix + Dovecot (email)
- Certbot (SSL)
- UFW (firewall)
- Fail2ban (security)

## Development

```bash
git clone https://github.com/atulyaai/Atulya-Launch.git
cd Atulya-Launch
pip install -e ".[all,dev]"

# Run tests
pytest

# Start dev server
python -m atulya_launch --web --port 8080
```

## License

MIT License - see [LICENSE](LICENSE) for details.

## Credits

Built by [Atulya AI](https://github.com/atulyaai) — making server management accessible to everyone.
