#!/usr/bin/env bash
set -euo pipefail

# Atulya Launch - Production Server Installer for Ubuntu 22.04/24.04
# Installs: Nginx, MySQL, PHP-FPM, Certbot, UFW, Fail2Ban, Docker, Python 3.11+
# Usage: curl -sSL https://raw.githubusercontent.com/atulyaai/Atulya-Launch/main/scripts/install-server.sh | bash

PANEL_HOST="${PANEL_HOST:-127.0.0.1}"
PANEL_PORT="${PANEL_PORT:-8080}"
ADMIN_USER="${ADMIN_USER:-admin}"
ADMIN_PASS="${ADMIN_PASS:-}"
SKIP_DOCKER="${SKIP_DOCKER:-0}"

log() { echo -e "\033[1;32m[Atulya]\033[0m $*"; }
warn() { echo -e "\033[1;33m[Warning]\033[0m $*"; }
err() { echo -e "\033[1;31m[Error]\033[0m $*" >&2; exit 1; }

require_root() {
    if [ "$(id -u)" -ne 0 ]; then
        err "This script must be run as root. Use: sudo bash install-server.sh"
    fi
}

detect_os() {
    if ! grep -qiE "ubuntu (22|24)" /etc/os-release 2>/dev/null; then
        warn "This script is tested on Ubuntu 22.04/24.04. Proceed at your own risk."
    fi
}

install_system_deps() {
    log "Installing system dependencies..."
    apt-get update -qq
    apt-get install -y -qq \
        curl wget git unzip software-properties-common \
        apt-transport-https ca-certificates gnupg lsb-release \
        ufw fail2ban \
        > /dev/null 2>&1
    log "System dependencies installed."
}

install_python() {
    log "Installing Python 3.11+..."
    if command -v python3.11 &>/dev/null; then
        log "Python 3.11 already installed."
        return
    fi
    add-apt-repository -y ppa:deadsnakes/ppa > /dev/null 2>&1
    apt-get update -qq
    apt-get install -y -qq python3.11 python3.11-venv python3.11-dev python3-pip > /dev/null 2>&1
    log "Python 3.11 installed."
}

install_nginx() {
    log "Installing Nginx..."
    apt-get install -y -qq nginx > /dev/null 2>&1
    systemctl enable nginx > /dev/null 2>&1
    systemctl start nginx > /dev/null 2>&1
    log "Nginx installed and started."
}

install_mysql() {
    log "Installing MySQL..."
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq mysql-server > /dev/null 2>&1
    systemctl enable mysql > /dev/null 2>&1
    systemctl start mysql > /dev/null 2>&1
    log "MySQL installed and started."
}

install_php() {
    log "Installing PHP-FPM..."
    # Ubuntu 22.04 ships 8.1 in main; 8.2/8.3 require the ondrej/php PPA.
    # Try PPA first so 8.3 is available, fall back to whatever main provides.
    if ! apt-cache show php8.3-fpm > /dev/null 2>&1; then
        warn "PHP 8.3 not in main repos; adding ondrej/php PPA..."
        if ! apt-get install -y -qq software-properties-common ca-certificates apt-transport-https lsb-release > /dev/null 2>&1; then
            warn "apt-get install prerequisites for PPA failed; continuing with main repos"
        fi
        add-apt-repository -y ppa:ondrej/php > /dev/null 2>&1 || true
        apt-get update -qq || true
    fi
    local installed=""
    for ver in 8.3 8.2 8.1 8.0 7.4; do
        if apt-cache show "php${ver}-fpm" > /dev/null 2>&1; then
            log "  installing php${ver}-fpm + extensions"
            if DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
                "php${ver}-fpm" "php${ver}-mysql" "php${ver}-cli" "php${ver}-curl" \
                "php${ver}-gd" "php${ver}-mbstring" "php${ver}-xml" "php${ver}-zip" \
                > /tmp/atulya-php-install.log 2>&1; then
                installed="${ver} ${installed}"
            else
                warn "  php${ver}-fpm install failed; trying next version (see /tmp/atulya-php-install.log)"
            fi
        fi
    done
    installed="$(echo "${installed}" | xargs)"  # trim
    if [ -z "${installed}" ]; then
        err "No PHP-FPM version could be installed. Cannot continue."
    fi
    # Pick the highest installed version and enable/start it
    local primary
    primary="$(echo "${installed}" | tr ' ' '\n' | sort -V | tail -1)"
    log "Primary PHP-FPM: ${primary}"
    systemctl enable "php${primary}-fpm" > /dev/null 2>&1 || warn "could not enable php${primary}-fpm"
    systemctl restart "php${primary}-fpm" > /dev/null 2>&1 || warn "could not start php${primary}-fpm"
    log "PHP-FPM installed (${installed// /, })."
}

install_modsecurity() {
    log "Installing ModSecurity WAF..."
    apt-get install -y libmodsecurity3 libmodsecurity-dev modsecurity-crs 2>/dev/null || apt-get install -y libmodsecurity3 libmodsecurity-dev 2>/dev/null || true

    # Download OWASP CRS if not present
    if [ ! -d /etc/modsecurity/crs ]; then
        mkdir -p /etc/modsecurity/crs
        wget -qO /tmp/crs.tar.gz https://github.com/coreruleset/coreruleset/archive/v4.0.0.tar.gz 2>/dev/null || true
        if [ -f /tmp/crs.tar.gz ]; then
            tar -xzf /tmp/crs.tar.gz -C /etc/modsecurity/crs --strip-components=1 2>/dev/null || true
            rm -f /tmp/crs.tar.gz
        fi
    fi

    # Create ModSecurity directories
    mkdir -p /etc/nginx/modsec /etc/nginx/modsec/owasp-crs

    # Enable ModSecurity in Nginx
    cat > /etc/nginx/modsec/main.conf << 'MODSEF'
# ModSecurity configuration
SecRuleEngine DetectionOnly
Include /etc/nginx/modsec/modsecurity.conf
Include /etc/nginx/modsec/owasp-crs/crs-setup.conf.example
Include /etc/nginx/modsec/owasp-crs/rules/*.conf
MODSEF

    # Create basic modsecurity config
    cat > /etc/nginx/modsec/modsecurity.conf << 'MODSEF2'
SecRuleEngine DetectionOnly
SecRequestBodyAccess On
SecResponseBodyAccess On
SecDataDir /tmp/modsecurity
MODSEF2

    # Load Nginx ModSecurity module if available
    if [ -f /usr/lib/nginx/modules/ngx_http_modsecurity_module.so ]; then
        if ! grep -q "ngx_http_modsecurity_module" /etc/nginx/nginx.conf 2>/dev/null; then
            sed -i '1iload_module modules/ngx_http_modsecurity_module.so;' /etc/nginx/nginx.conf
            log "Nginx ModSecurity module loaded."
        fi
    else
        warn "ngx_http_modsecurity_module.so not found — Nginx must be compiled with --with-compat or --add-module for ModSecurity support."
    fi

    # Test and reload Nginx
    nginx -t 2>/dev/null && systemctl reload nginx 2>/dev/null || true

    echo "ModSecurity WAF installed (DetectionOnly mode)."
}

install_certbot() {
    log "Installing Certbot..."
    apt-get install -y -qq certbot python3-certbot-nginx > /dev/null 2>&1
    log "Certbot installed."
}

install_mail_stack() {
    log "Installing mail stack (postfix, dovecot, opendkim, bind9)..."
    # Postfix: non-interactive install with "Internet Site" config.
    debconf-set-selections <<EOF
postfix postfix/main_mailer_type string 'Internet Site'
postfix postfix/mailname string '${TEST_DOMAIN:-localhost.localdomain}'
postfix postfix/destinations string '${TEST_DOMAIN:-localhost.localdomain}, localhost'
EOF
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq postfix > /tmp/atulya-postfix.log 2>&1 \
        || warn "postfix install failed; see /tmp/atulya-postfix.log"
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq dovecot-core dovecot-imapd dovecot-pop3d dovecot-lmtpd > /tmp/atulya-dovecot.log 2>&1 \
        || warn "dovecot install failed; see /tmp/atulya-dovecot.log"
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq opendkim opendkim-tools > /tmp/atulya-opendkim.log 2>&1 \
        || warn "opendkim install failed; see /tmp/atulya-opendkim.log"
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq bind9 bind9utils bind9-doc > /tmp/atulya-bind.log 2>&1 \
        || warn "bind9 install failed; see /tmp/atulya-bind.log"

    # Enable & start (idempotent; ignore if service not present)
    for svc in postfix dovecot opendkim bind9 named; do
        if systemctl list-unit-files "${svc}.service" 2>/dev/null | grep -q "${svc}.service"; then
            systemctl enable "${svc}" > /dev/null 2>&1 || true
            systemctl restart "${svc}" > /dev/null 2>&1 || true
        fi
    done
    # `named` is the legacy service name on older Ubuntu; bind9 is the new one.
    if systemctl list-unit-files named.service 2>/dev/null | grep -q named.service; then
        systemctl enable named > /dev/null 2>&1 || true
        systemctl restart named > /dev/null 2>&1 || true
    fi
    log "Mail stack install step complete (services may be inactive if installs failed; see /tmp/atulya-*.log)."
}

install_docker() {
    if [ "$SKIP_DOCKER" = "1" ]; then
        log "Skipping Docker installation."
        return
    fi
    log "Installing Docker..."
    if command -v docker &>/dev/null; then
        log "Docker already installed."
        return
    fi
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /usr/share/keyrings/docker.gpg > /dev/null 2>&1
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" > /etc/apt/sources.list.d/docker.list
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin > /dev/null 2>&1
    systemctl enable docker > /dev/null 2>&1
    systemctl start docker > /dev/null 2>&1
    log "Docker installed."
}

configure_firewall() {
    log "Configuring UFW firewall..."
    ufw default deny incoming > /dev/null 2>&1
    ufw default allow outgoing > /dev/null 2>&1
    ufw allow 22/tcp > /dev/null 2>&1
    ufw allow 80/tcp > /dev/null 2>&1
    ufw allow 443/tcp > /dev/null 2>&1
    ufw allow "$PANEL_PORT/tcp" > /dev/null 2>&1
    echo "y" | ufw enable > /dev/null 2>&1
    log "UFW configured. SSH/HTTP/HTTPS/Panel allowed."
}

configure_fail2ban() {
    log "Configuring Fail2Ban..."
    cat > /etc/fail2ban/jail.local <<'EOF'
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 5
backend = systemd

[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
EOF
    systemctl enable fail2ban > /dev/null 2>&1
    systemctl restart fail2ban > /dev/null 2>&1
    log "Fail2Ban configured."
}

install_panel() {
    log "Installing Atulya Launch panel..."
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    if [ -f "$SCRIPT_DIR/install.py" ]; then
        bash "$SCRIPT_DIR/install.sh" --local --all --admin "$ADMIN_USER" --host "$PANEL_HOST" --port "$PANEL_PORT" ${ADMIN_PASS:+--password "$ADMIN_PASS"}
    else
        curl -sSL https://raw.githubusercontent.com/atulyaai/Atulya-Launch/main/scripts/install.sh | bash -s -- --all --admin "$ADMIN_USER" --host "$PANEL_HOST" --port "$PANEL_PORT" ${ADMIN_PASS:+--password "$ADMIN_PASS"}
    fi
    log "Atulya Launch installed."
}

create_systemd_service() {
    # The systemd unit is created by install.py:setup_systemd() (which knows
    # the correct venv path). Here we only need to ensure systemd is aware
    # of the unit and that the service is running.
    log "Activating Atulya Launch service..."
    systemctl daemon-reload
    systemctl enable atulya-launch > /dev/null 2>&1 || true
    systemctl restart atulya-launch > /dev/null 2>&1 || warn "could not start atulya-launch; check 'journalctl -u atulya-launch'"
    log "Atulya Launch service activated."
}

print_summary() {
    echo ""
    echo "============================================="
    echo "  Atulya Launch - Installation Complete"
    echo "============================================="
    echo ""
    echo "  Dashboard:  http://$PANEL_HOST:$PANEL_PORT"
    echo "  Login:      $ADMIN_USER / ${ADMIN_PASS:-<generated>}"
    echo ""
    echo "  Services:"
    echo "    Nginx:      $(systemctl is-active nginx 2>/dev/null || echo 'inactive')"
    echo "    MySQL:      $(systemctl is-active mysql 2>/dev/null || echo 'inactive')"
    echo "    Fail2Ban:   $(systemctl is-active fail2ban 2>/dev/null || echo 'inactive')"
    echo "    UFW:        $(ufw status 2>/dev/null | head -1 || echo 'unknown')"
    if [ "$SKIP_DOCKER" != "1" ]; then
    echo "    Docker:     $(systemctl is-active docker 2>/dev/null || echo 'inactive')"
    fi
    echo ""
    echo "  Commands:"
    echo "    atulya-launch system        # System status"
    echo "    atulya-launch security-scan # Security check"
    echo "    atulya-launch site create   # Create website"
    echo "    systemctl status atulya-launch"
    echo ""
    echo "  IMPORTANT: Change the default admin password in the panel!"
    echo "============================================="
}

main() {
    require_root
    detect_os
    log "Starting Atulya Launch server installation..."
    install_system_deps
    install_python
    install_nginx
    install_mysql
    install_php
    install_modsecurity
    install_certbot
    install_mail_stack
    install_docker
    configure_firewall
    configure_fail2ban
    install_panel
    create_systemd_service
    print_summary
}

main "$@"
