# Atulya Launch

Lightweight hosting control panel for websites, APIs and AI apps — low memory, one-click everything.

## Features

- One-click domain setup with SSL (Let's Encrypt)
- Apache/Nginx reverse proxy management
- PHP, Node.js, Python, static site support
- MySQL/PostgreSQL database management
- FTP/SFTP user management
- Auto-backup to local/cloud
- Server resource monitoring
- One-click AI model deployment
- REST API for automation

## Quick Start

```bash
pip install atulya-launch
sudo atulya-launch init
atulya-launch site create --domain mysite.com --type python
atulya-launch ssl issue --domain mysite.com
```

## Commands

| Command | Description |
|---------|-------------|
| `init` | Initialize control panel |
| `site create` | Create a new website |
| `ssl issue` | Issue Let's Encrypt SSL |
| `db create` | Create a database |
| `user add` | Add FTP/SFTP user |
| `backup` | Run backup |
| `monitor` | Show server stats |

## Requirements

- Linux (Ubuntu 22.04+ / Debian 12+)
- Python 3.10+
- 256MB RAM minimum

## License

MIT
