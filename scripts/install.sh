#!/usr/bin/env bash
# Atulya-Launch One-Click Installer
# Lightweight cPanel alternative — < 50MB RAM idle
# Usage: curl -sSL https://raw.githubusercontent.com/atulyaai/Atulya-Launch/main/scripts/install.sh | bash
set -euo pipefail

# ── Colors & Helpers ─────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }
fatal()   { error "$*"; exit 1; }
step()    { echo -e "\n${CYAN}${BOLD}==> $*${NC}"; }

# ── Globals ──────────────────────────────────────────────────────────────────
INSTALL_DIR="/opt/atulya-launch"
CONFIG_DIR="/etc/atulya-launch"
DATA_DIR="/var/lib/atulya-launch"
LOG_DIR="/var/log/atulya-launch"
CERT_DIR="/etc/atulya-launch/ssl"
SERVICE_NAME="atulya-launch"
PANEL_PORT=8443
MINIMAL=false
FULL=false
UNINSTALL=false
UPDATE=false
ROLLBACK_STEPS=()
INSTALLED_PACKAGES=()
ADMIN_USER="admin"
ADMIN_PASSWORD=""
SERVER_IP=""
OS_FAMILY=""
PKG_MANAGER=""

# ── Argument Parsing ─────────────────────────────────────────────────────────
parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --minimal)   MINIMAL=true; shift ;;
            --full)      FULL=true; shift ;;
            --uninstall) UNINSTALL=true; shift ;;
            --update)    UPDATE=true; shift ;;
            --port)      PANEL_PORT="$2"; shift 2 ;;
            --help|-h)
                echo "Atulya-Launch Installer"
                echo ""
                echo "Usage: bash install.sh [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  --minimal       Skip email (Postfix/Dovecot) and DNS (BIND9)"
                echo "  --full          Install all components (default)"
                echo "  --port PORT     Panel port (default: 8443)"
                echo "  --update        Update existing installation"
                echo "  --uninstall     Remove Atulya-Launch completely"
                echo "  -h, --help      Show this help"
                exit 0
                ;;
            *) fatal "Unknown option: $1" ;;
        esac
    done
}

# ── Pre-flight Checks ───────────────────────────────────────────────────────
check_root() {
    if [[ $EUID -ne 0 ]]; then
        fatal "This installer must be run as root. Use: sudo bash install.sh"
    fi
}

detect_os() {
    step "Detecting operating system"
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        DISTRO="${ID,,}"
        VERSION="${VERSION_ID}"
    else
        fatal "Cannot detect OS. Only Linux is supported."
    fi

    case "$DISTRO" in
        ubuntu|debian)
            OS_FAMILY="debian"
            PKG_MANAGER="apt"
            ;;
        centos|rhel|fedora|almalinux|rocky)
            OS_FAMILY="rhel"
            PKG_MANAGER="yum"
            [[ "$DISTRO" == "fedora" ]] && PKG_MANAGER="dnf"
            ;;
        *)
            fatal "Unsupported distribution: $DISTRO $VERSION"
            ;;
    esac

    success "Detected $PRETTY_NAME ($OS_FAMILY)"
}

check_system() {
    step "Checking system requirements"
    local ram_mb
    ram_mb=$(free -m | awk '/^Mem:/{print $2}')
    local disk_gb
    disk_gb=$(df -BG / | awk 'NR==2{print $4}' | tr -d 'G')

    info "RAM: ${ram_mb}MB | Available disk: ${disk_gb}GB"

    if [[ $ram_mb -lt 512 ]]; then
        warn "Low memory detected (${ram_mb}MB). Recommended: 1GB+"
    fi
    if [[ $disk_gb -lt 2 ]]; then
        fatal "Insufficient disk space. Need at least 2GB free."
    fi

    success "System check passed"
}

get_server_ip() {
    SERVER_IP=$(curl -s --connect-timeout 5 https://ifconfig.me 2>/dev/null || \
                curl -s --connect-timeout 5 https://api.ipify.org 2>/dev/null || \
                hostname -I 2>/dev/null | awk '{print $1}' || \
                echo "127.0.0.1")
    info "Server IP: $SERVER_IP"
}

# ── Rollback Support ─────────────────────────────────────────────────────────
add_rollback() {
    ROLLBACK_STEPS+=("$1")
}

rollback() {
    if [[ ${#ROLLBACK_STEPS[@]} -eq 0 ]]; then
        return
    fi
    warn "Rolling back changes..."
    for ((i=${#ROLLBACK_STEPS[@]}-1; i>=0; i--)); do
        eval "${ROLLBACK_STEPS[$i]}" || true
    done
    error "Installation failed. Changes have been rolled back."
}

trap rollback ERR

# ── Package Management ───────────────────────────────────────────────────────
pkg_update() {
    if [[ "$PKG_MANAGER" == "apt" ]]; then
        apt-get update -qq
    else
        $PKG_MANAGER makecache -q 2>/dev/null || true
    fi
}

pkg_install() {
    local packages=("$@")
    for pkg in "${packages[@]}"; do
        if dpkg -s "$pkg" &>/dev/null 2>&1 || rpm -q "$pkg" &>/dev/null 2>&1; then
            continue
        fi
        INSTALLED_PACKAGES+=("$pkg")
    done

    if [[ ${#INSTALLED_PACKAGES[@]} -eq 0 ]]; then
        return
    fi

    if [[ "$PKG_MANAGER" == "apt" ]]; then
        DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${INSTALLED_PACKAGES[@]}"
    else
        $PKG_MANAGER install -y -q "${INSTALLED_PACKAGES[@]}"
    fi
}

# ── Install System Dependencies ──────────────────────────────────────────────
install_deps() {
    step "Installing system dependencies"
    pkg_update

    local base_pkgs=(
        python3 python3-pip python3-venv python3-dev
        nginx
        certbot python3-certbot-nginx
        ufw
        fail2ban
        git curl wget
        sqlite3
        openssl
    )

    if [[ "$FULL" == true ]] || [[ "$MINIMAL" == false ]]; then
        base_pkgs+=(
            bind9 bind9utils
            postfix dovecot-imapd dovecot-pop3d
            mariadb-server mariadb-client
            postgresql postgresql-client
        )
        if [[ "$OS_FAMILY" == "debian" ]]; then
            base_pkgs+=(bind9-host)
        fi
    fi

    if [[ "$OS_FAMILY" == "rhel" ]]; then
        base_pkgs=(python3 python3-pip nginx certbot python3-certbot-nginx
                   git curl wget sqlite openssl)
        if [[ "$FULL" == true ]] || [[ "$MINIMAL" == false ]]; then
            base_pkgs+=(bind bind-utils postfix dovecot mariadb-server postgresql-server)
        fi
    fi

    pkg_install "${base_pkgs[@]}"
    success "Dependencies installed"
}

# ── Create System User ───────────────────────────────────────────────────────
create_user() {
    step "Creating atulya-launch system user"
    if id "atulya-launch" &>/dev/null; then
        info "User atulya-launch already exists"
    else
        useradd --system --no-create-home --shell /usr/sbin/nologin atulya-launch 2>/dev/null || \
        useradd -r -s /sbin/nologin atulya-launch 2>/dev/null || true
        add_rollback "userdel -r atulya-launch 2>/dev/null || true"
        success "Created user: atulya-launch"
    fi
}

# ── Install Atulya-Launch Package ────────────────────────────────────────────
install_package() {
    step "Installing atulya-launch Python package"

    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    local project_root
    project_root="$(dirname "$script_dir")"

    if [[ -f "$project_root/pyproject.toml" ]]; then
        info "Installing from local source: $project_root"
        pip3 install --break-system-packages "$project_root" 2>/dev/null || \
        pip3 install "$project_root"
    else
        info "Installing from PyPI"
        pip3 install --break-system-packages atulya-launch 2>/dev/null || \
        pip3 install atulya-launch
    fi

    add_rollback "pip3 uninstall -y atulya-launch 2>/dev/null || true"
    success "atulya-launch installed"
}

# ── Directory Structure ──────────────────────────────────────────────────────
create_dirs() {
    step "Creating directory structure"
    mkdir -p "$INSTALL_DIR" "$CONFIG_DIR" "$DATA_DIR" "$LOG_DIR" "$CERT_DIR"
    mkdir -p "$CONFIG_DIR/nginx" "$CONFIG_DIR/bind" "$CONFIG_DIR/postfix"
    mkdir -p "$CONFIG_DIR/dovecot" "$CONFIG_DIR/fail2ban" "$CONFIG_DIR/ufw"
    mkdir -p /var/www
    chown -R atulya-launch:atulya-launch "$DATA_DIR" "$LOG_DIR"
    chmod 750 "$CONFIG_DIR" "$CERT_DIR"
    add_rollback "rm -rf $INSTALL_DIR $CONFIG_DIR $DATA_DIR $LOG_DIR $CERT_DIR"
    success "Directories created"
}

# ── SSL Certificate ──────────────────────────────────────────────────────────
generate_ssl() {
    step "Generating self-signed SSL certificate"
    if [[ -f "$CERT_DIR/panel.crt" ]] && [[ -f "$CERT_DIR/panel.key" ]]; then
        info "SSL certificate already exists"
    else
        openssl req -x509 -nodes -days 3650 \
            -newkey rsa:2048 \
            -keyout "$CERT_DIR/panel.key" \
            -out "$CERT_DIR/panel.crt" \
            -subj "/C=US/ST=Local/L=Local/O=Atulya-Launch/CN=atulya-panel" \
            2>/dev/null

        chmod 600 "$CERT_DIR/panel.key"
        chmod 644 "$CERT_DIR/panel.crt"
        add_rollback "rm -f $CERT_DIR/panel.crt $CERT_DIR/panel.key"
        success "SSL certificate generated (valid 10 years)"
    fi
}

# ── Nginx Configuration ─────────────────────────────────────────────────────
configure_nginx() {
    step "Configuring Nginx"

    local template_dir
    template_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../atulya_launch/templates/nginx" && pwd 2>/dev/null || echo "")"

    if [[ -f "$template_dir/panel.conf" ]]; then
        cp "$template_dir/panel.conf" /etc/nginx/sites-available/atulya-panel.conf
    else
        cat > /etc/nginx/sites-available/atulya-panel.conf << 'NGINX_CONF'
# Rate limiting zone
limit_req_zone $binary_remote_addr zone=atulya_panel:10m rate=10r/s;

server {
    listen 8443 ssl http2;
    listen [::]:8443 ssl http2;
    server_name _;

    ssl_certificate     /etc/atulya-launch/ssl/panel.crt;
    ssl_certificate_key /etc/atulya-launch/ssl/panel.key;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache   shared:SSL:10m;
    ssl_session_timeout 10m;

    client_max_body_size 100M;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Rate limiting
    limit_req zone=atulya_panel burst=20 nodelay;

    location / {
        proxy_pass http://127.0.0.1:8443;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /ws {
        proxy_pass http://127.0.0.1:8443;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;
    }
}
NGINX_CONF
    fi

    ln -sf /etc/nginx/sites-available/atulya-panel.conf /etc/nginx/sites-enabled/atulya-panel.conf
    rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true

    nginx -t 2>/dev/null && systemctl reload nginx 2>/dev/null || true
    success "Nginx configured"
}

# ── BIND9 Configuration ──────────────────────────────────────────────────────
configure_bind() {
    if [[ "$MINIMAL" == true ]]; then
        info "Skipping BIND9 (minimal mode)"
        return
    fi

    step "Configuring BIND9 DNS"
    local template_dir
    template_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../atulya_launch/templates/bind" && pwd 2>/dev/null || echo "")"

    if [[ -f "$template_dir/named.conf.local" ]]; then
        cp "$template_dir/named.conf.local" /etc/bind/named.conf.local 2>/dev/null || true
    fi

    mkdir -p /etc/bind/zones
    systemctl enable named 2>/dev/null || systemctl enable bind9 2>/dev/null || true
    systemctl start named 2>/dev/null || systemctl start bind9 2>/dev/null || true
    success "BIND9 configured"
}

# ── Postfix Configuration ────────────────────────────────────────────────────
configure_postfix() {
    if [[ "$MINIMAL" == true ]]; then
        info "Skipping Postfix (minimal mode)"
        return
    fi

    step "Configuring Postfix mail server"
    local template_dir
    template_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../atulya_launch/templates/postfix" && pwd 2>/dev/null || echo "")"

    if [[ -f "$template_dir/main.cf" ]]; then
        cp "$template_dir/main.cf" /etc/postfix/main.cf
    fi

    systemctl enable postfix 2>/dev/null || true
    systemctl restart postfix 2>/dev/null || true
    success "Postfix configured"
}

# ── Dovecot Configuration ────────────────────────────────────────────────────
configure_dovecot() {
    if [[ "$MINIMAL" == true ]]; then
        info "Skipping Dovecot (minimal mode)"
        return
    fi

    step "Configuring Dovecot IMAP/POP3"
    local template_dir
    template_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../atulya_launch/templates/dovecot" && pwd 2>/dev/null || echo "")"

    if [[ -f "$template_dir/dovecot.conf" ]]; then
        cp "$template_dir/dovecot.conf" /etc/dovecot/dovecot.conf
    fi

    systemctl enable dovecot 2>/dev/null || true
    systemctl restart dovecot 2>/dev/null || true
    success "Dovecot configured"
}

# ── Database Initialization ──────────────────────────────────────────────────
configure_databases() {
    if [[ "$MINIMAL" == true ]]; then
        info "Skipping database setup (minimal mode)"
        return
    fi

    step "Initializing databases"

    # MariaDB/MySQL
    if systemctl is-active --quiet mariadb 2>/dev/null || systemctl is-active --quiet mysql 2>/dev/null; then
        mysql -e "CREATE DATABASE IF NOT EXISTS atulya_launch CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;" 2>/dev/null || true
        local db_pass
        db_pass=$(openssl rand -hex 16)
        mysql -e "CREATE USER IF NOT EXISTS 'atulya'@'localhost' IDENTIFIED BY '$db_pass';" 2>/dev/null || true
        mysql -e "GRANT ALL PRIVILEGES ON atulya_launch.* TO 'atulya'@'localhost';" 2>/dev/null || true
        mysql -e "FLUSH PRIVILEGES;" 2>/dev/null || true
        echo "mysql:$db_pass" > "$CONFIG_DIR/.db-credentials"
        chmod 600 "$CONFIG_DIR/.db-credentials"
        success "MariaDB/MySQL initialized"
    else
        info "MariaDB/MySQL not running, skipping"
    fi

    # PostgreSQL
    if systemctl is-active --quiet postgresql 2>/dev/null; then
        sudo -u postgres psql -c "CREATE DATABASE atulya_launch;" 2>/dev/null || true
        sudo -u postgres psql -c "CREATE USER atulya WITH PASSWORD '$(openssl rand -hex 16)';" 2>/dev/null || true
        sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE atulya_launch TO atulya;" 2>/dev/null || true
        success "PostgreSQL initialized"
    else
        info "PostgreSQL not running, skipping"
    fi
}

# ── Fail2ban Configuration ───────────────────────────────────────────────────
configure_fail2ban() {
    step "Configuring Fail2ban"
    local template_dir
    template_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../atulya_launch/templates/fail2ban" && pwd 2>/dev/null || echo "")"

    if [[ -f "$template_dir/jail.local" ]]; then
        cp "$template_dir/jail.local" /etc/fail2ban/jail.local
    fi

    systemctl enable fail2ban 2>/dev/null || true
    systemctl restart fail2ban 2>/dev/null || true
    success "Fail2ban configured"
}

# ── UFW Firewall ─────────────────────────────────────────────────────────────
configure_ufw() {
    step "Configuring UFW firewall"
    ufw --force reset >/dev/null 2>&1 || true
    ufw default deny incoming >/dev/null 2>&1
    ufw default allow outgoing >/dev/null 2>&1
    ufw allow 22/tcp >/dev/null 2>&1
    ufw allow 80/tcp >/dev/null 2>&1
    ufw allow 443/tcp >/dev/null 2>&1
    ufw allow "${PANEL_PORT}/tcp" >/dev/null 2>&1

    if [[ "$MINIMAL" == false ]]; then
        ufw allow 53/tcp >/dev/null 2>&1
        ufw allow 53/udp >/dev/null 2>&1
        ufw allow 25/tcp >/dev/null 2>&1
        ufw allow 143/tcp >/dev/null 2>&1
        ufw allow 993/tcp >/dev/null 2>&1
        ufw allow 110/tcp >/dev/null 2>&1
        ufw allow 995/tcp >/dev/null 2>&1
    fi

    ufw --force enable >/dev/null 2>&1
    success "UFW configured"
}

# ── Systemd Service ──────────────────────────────────────────────────────────
install_service() {
    step "Installing systemd service"
    local template_dir
    template_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../atulya_launch/templates/systemd" && pwd 2>/dev/null || echo "")"

    if [[ -f "$template_dir/atulya-launch.service" ]]; then
        cp "$template_dir/atulya-launch.service" /etc/systemd/system/${SERVICE_NAME}.service
    else
        cat > /etc/systemd/system/${SERVICE_NAME}.service << SERVICE_EOF
[Unit]
Description=Atulya-Launch Control Panel
After=network.target nginx.service mariadb.service postgresql.service
Wants=nginx.service

[Service]
Type=simple
User=atulya-launch
Group=atulya-launch
WorkingDirectory=/var/lib/atulya-launch
ExecStart=$(which python3 2>/dev/null || echo /usr/bin/python3) -m atulya_launch --web --port ${PANEL_PORT}
Restart=on-failure
RestartSec=5
StartLimitBurst=3
StartLimitIntervalSec=60

# Security hardening
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/lib/atulya-launch /var/log/atulya-launch /etc/atulya-launch
PrivateTmp=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes

# Resource limits (enforce < 50MB RAM)
MemoryMax=64M
MemoryHigh=48M
CPUQuota=10%

# Environment
Environment=ATULYA_CONFIG_DIR=/etc/atulya-launch
Environment=ATULYA_DATA_DIR=/var/lib/atulya-launch
Environment=ATULYA_LOG_DIR=/var/log/atulya-launch

[Install]
WantedBy=multi-user.target
SERVICE_EOF
    fi

    systemctl daemon-reload
    systemctl enable ${SERVICE_NAME} 2>/dev/null || true
    add_rollback "systemctl disable ${SERVICE_NAME} 2>/dev/null || true; rm -f /etc/systemd/system/${SERVICE_NAME}.service; systemctl daemon-reload"
    success "Systemd service installed"
}

# ── Admin Password Generation ────────────────────────────────────────────────
generate_admin_password() {
    step "Generating admin credentials"
    ADMIN_PASSWORD=$(openssl rand -base64 24 | tr -d '/+=' | head -c 24)
    echo "admin:${ADMIN_PASSWORD}" > "$CONFIG_DIR/.admin-credentials"
    chmod 600 "$CONFIG_DIR/.admin-credentials"
    success "Admin credentials generated"
}

# ── Initialize Panel Config ──────────────────────────────────────────────────
init_panel_config() {
    step "Initializing panel configuration"
    cat > "$CONFIG_DIR/config.yaml" << CONFIG_EOF
panel:
  name: Atulya Launch
  version: 0.1.0
  port: ${PANEL_PORT}
  host: 0.0.0.0

server:
  web_server: nginx
  php_enabled: false

ssl:
  cert: ${CERT_DIR}/panel.crt
  key: ${CERT_DIR}/panel.key

database:
  engine: sqlite
  path: ${DATA_DIR}/atulya.db

backup:
  keep_days: 30

monitoring:
  enabled: true
  interval_seconds: 60
CONFIG_EOF
    chown atulya-launch:atulya-launch "$CONFIG_DIR/config.yaml"
    success "Panel configuration initialized"
}

# ── Uninstall ────────────────────────────────────────────────────────────────
do_uninstall() {
    step "Uninstalling Atulya-Launch"
    systemctl stop ${SERVICE_NAME} 2>/dev/null || true
    systemctl disable ${SERVICE_NAME} 2>/dev/null || true
    rm -f /etc/systemd/system/${SERVICE_NAME}.service
    systemctl daemon-reload 2>/dev/null || true

    rm -f /etc/nginx/sites-available/atulya-panel.conf
    rm -f /etc/nginx/sites-enabled/atulya-panel.conf
    systemctl reload nginx 2>/dev/null || true

    pip3 uninstall -y atulya-launch 2>/dev/null || true

    rm -rf "$INSTALL_DIR" "$CONFIG_DIR" "$DATA_DIR" "$LOG_DIR" "$CERT_DIR"
    userdel atulya-launch 2>/dev/null || true

    success "Atulya-Launch has been removed"
    exit 0
}

# ── Update ───────────────────────────────────────────────────────────────────
do_update() {
    step "Updating Atulya-Launch"
    pip3 install --break-system-packages --upgrade atulya-launch 2>/dev/null || \
    pip3 install --upgrade atulya-launch
    systemctl restart ${SERVICE_NAME} 2>/dev/null || true
    success "Atulya-Launch updated"
    exit 0
}

# ── Summary ──────────────────────────────────────────────────────────────────
print_summary() {
    echo ""
    echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}${BOLD}║          Atulya-Launch Installation Complete!               ║${NC}"
    echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${BOLD}Panel URL:${NC}      https://${SERVER_IP}:${PANEL_PORT}"
    echo -e "  ${BOLD}Admin User:${NC}     ${ADMIN_USER}"
    echo -e "  ${BOLD}Admin Password:${NC} ${ADMIN_PASSWORD}"
    echo ""
    echo -e "  ${BOLD}First Login Steps:${NC}"
    echo -e "    1. Open https://${SERVER_IP}:${PANEL_PORT} in your browser"
    echo -e "    2. Accept the self-signed certificate warning"
    echo -e "    3. Login with the admin credentials above"
    echo -e "    4. Change the admin password immediately"
    echo ""
    echo -e "  ${BOLD}Service Management:${NC}"
    echo -e "    Start:   systemctl start ${SERVICE_NAME}"
    echo -e "    Stop:    systemctl stop ${SERVICE_NAME}"
    echo -e "    Status:  systemctl status ${SERVICE_NAME}"
    echo -e "    Logs:    journalctl -u ${SERVICE_NAME} -f"
    echo ""
    echo -e "  ${BOLD}Config:${NC}         ${CONFIG_DIR}/config.yaml"
    echo -e "  ${BOLD}Credentials:${NC}    ${CONFIG_DIR}/.admin-credentials"
    echo ""
    if [[ "$MINIMAL" == false ]]; then
        echo -e "  ${BOLD}Services Installed:${NC}"
        echo -e "    - Nginx (Web Server)"
        echo -e "    - BIND9 (DNS)"
        echo -e "    - Postfix + Dovecot (Email)"
        echo -e "    - MariaDB/PostgreSQL (Databases)"
        echo -e "    - Fail2ban (Security)"
        echo -e "    - UFW (Firewall)"
        echo -e "    - Certbot (SSL)"
    else
        echo -e "  ${BOLD}Minimal mode:${NC} Email and DNS services skipped"
    fi
    echo ""
    echo -e "${CYAN}  Documentation: https://github.com/atulyaai/Atulya-Launch${NC}"
    echo -e "${CYAN}  Issues:        https://github.com/atulyaai/Atulya-Launch/issues${NC}"
    echo ""
}

# ── Main ─────────────────────────────────────────────────────────────────────
main() {
    parse_args "$@"

    echo -e "${CYAN}${BOLD}"
    echo "  ╔═══════════════════════════════════════╗"
    echo "  ║     Atulya-Launch Installer v0.1     ║"
    echo "  ║   Lightweight cPanel Alternative     ║"
    echo "  ╚═══════════════════════════════════════╝"
    echo -e "${NC}"

    [[ "$UNINSTALL" == true ]] && do_uninstall
    [[ "$UPDATE" == true ]] && do_update

    check_root
    detect_os
    check_system
    get_server_ip
    install_deps
    create_user
    create_dirs
    generate_ssl
    configure_nginx
    configure_bind
    configure_postfix
    configure_dovecot
    configure_databases
    configure_fail2ban
    configure_ufw
    install_package
    install_service
    generate_admin_password
    init_panel_config

    # Start services
    systemctl start ${SERVICE_NAME} 2>/dev/null || true
    systemctl start nginx 2>/dev/null || true

    print_summary
}

main "$@"
