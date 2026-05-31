# Production Deployment Guide

## Requirements

- **OS**: Ubuntu 22.04 LTS or 24.04 LTS (recommended)
- **RAM**: 1 GB minimum, 2 GB+ recommended
- **Disk**: 10 GB+ for panel + web data
- **Python**: 3.10+ (3.11 recommended)
- **Root/Sudo**: Required for system service setup

## Quick Install

```bash
# Clone and run installer
git clone https://github.com/atulyaai/Atulya-Launch.git
cd Atulya-Launch
sudo bash scripts/install-server.sh

# The installer sets up: Nginx, MySQL, PHP 8.1/8.2/8.3, Certbot, UFW, Fail2Ban, Docker
# Then runs the panel on http://localhost:8080
```

## Manual Setup

```bash
# 1. Install system dependencies
sudo apt update
sudo apt install -y nginx mysql-server php8.1-fpm php8.2-fpm php8.3-fpm \
    certbot python3-certbot-nginx ufw fail2ban docker.io

# 2. Install panel
pip install atulya-launch[all]

# 3. Start panel
atulya-launch serve --host 0.0.0.0 --port 8080
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `PANEL_HOST` | `127.0.0.1` | Bind address |
| `PANEL_PORT` | `8080` | Bind port |
| `PANEL_WORKERS` | `2` | Number of uvicorn workers |
| `PANEL_HTTPS` | `false` | Enable HTTPS (`true`/`1`) |
| `PANEL_DEBUG` | `false` | Show full error details (`true`/`1`) |
| `PANEL_PASSWORD_MIN_LENGTH` | `8` | Minimum password length |
| `PANEL_MAX_SESSIONS` | `5` | Max concurrent sessions per user |
| `ADMIN_PASS` | `admin` | Default admin password (first run only) |

## Security Checklist

- [ ] Change default admin password immediately
- [ ] Set `PANEL_HTTPS=true` and configure SSL certificate
- [ ] Run built-in Security Audit (`/security` in panel)
- [ ] Configure UFW: `ufw allow 80,443/tcp; ufw enable`
- [ ] Enable Fail2Ban: `systemctl enable --now fail2ban`
- [ ] Set `PANEL_HOST=127.0.0.1` and reverse proxy via Nginx
- [ ] Regular backup schedule configured in panel
- [ ] Monitor audit logs at `/logs`

## Reverse Proxy Setup (Nginx)

```nginx
server {
    listen 443 ssl;
    server_name panel.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/panel.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/panel.yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /monitoring/ws {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

## Systemd Service

```ini
[Unit]
Description=Atulya Launch Hosting Panel
After=network.target mysql.service nginx.service

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/atulya-launch
ExecStart=/usr/local/bin/atulya-launch serve --host 127.0.0.1 --port 8080 --workers 2
Restart=always
RestartSec=5
Environment=PANEL_DEBUG=false
Environment=PANEL_HTTPS=false

[Install]
WantedBy=multi-user.target
```

## Database Backups

```bash
# Manual backup
atulya-launch backup create

# Or use the panel UI: Backups -> Schedule
```

## Upgrading

```bash
pip install --upgrade atulya-launch
systemctl restart atulya-launch
```

## Troubleshooting

| Issue | Check |
|---|---|
| Panel won't start | `journalctl -u atulya-launch -n 50` |
| Nginx not reloading | `nginx -t` to test config |
| MySQL connection failed | `systemctl status mysql` |
| PHP not working | `php -v` and `systemctl status php8.3-fpm` |
| WebSocket not connecting | Check proxy config has Upgrade headers |
| Permission errors | Ensure `www-data` owns `~/.atulya/` |
