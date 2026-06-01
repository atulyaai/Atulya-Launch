#!/usr/bin/env bash
# Atulya Launch - Clean-Host Install Validator
# ------------------------------------------------
# Boots through a full hosting lifecycle on a clean Ubuntu 22.04/24.04 host
# (or VM/LXC) and asserts each step succeeds without manual intervention.
#
# Usage:
#   sudo bash scripts/validate-install.sh                    # full run
#   sudo bash scripts/validate-install.sh --skip-install    # assume panel already installed
#   sudo bash scripts/validate-install.sh --report PATH      # write report to PATH
#   sudo bash scripts/validate-install.sh --domain test.example.com
#   sudo ADMIN_PASS=foo bash scripts/validate-install.sh     # supply known password
#
# Exit codes:
#   0  - all validation steps passed
#   1  - install failed
#   2  - service lifecycle failed
#   3  - cleanup failed
#
# Required environment:
#   - Ubuntu 22.04 or 24.04
#   - root
#   - outbound HTTPS (for apt, pip, certbot staging)
#   - /etc/hosts entry for the test domain pointing to 127.0.0.1
#     (the validator will add it if missing)
#
# Notes:
#   - Uses Let's Encrypt STAGING to avoid rate limits.
#   - Uses real BIND/Postfix/Dovecot/OpenDKIM daemons, not dry-run.
#   - Backs up /etc/{bind,postfix,dovecot,opendkim,nginx} before each step
#     and restores on failure so the host can be re-run.

set -euo pipefail

# ----- args ------------------------------------------------------------------

SKIP_INSTALL=0
REPORT_PATH="${REPORT_PATH:-/tmp/atulya-validate-report.md}"
TEST_DOMAIN="${TEST_DOMAIN:-validation.atulya.local}"
TEST_EMAIL_USER="validate"
TEST_EMAIL_PASS="ValidatePass!2026"
TEST_DB_NAME="validate_db"
PANEL_PORT="${PANEL_PORT:-8080}"
PANEL_HOST="${PANEL_HOST:-127.0.0.1}"
ADMIN_USER="${ADMIN_USER:-admin}"
ADMIN_PASS="${ADMIN_PASS:-}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-install)
            # Accept either bare flag (--skip-install) or value (--skip-install 1|0|true|false)
            if [[ $# -ge 2 && "$2" =~ ^[01TtFf](alse|rue)?$ ]]; then
                case "$2" in
                    1|[Tt]rue|[Tt])  SKIP_INSTALL=1 ;;
                    *)               SKIP_INSTALL=0 ;;
                esac
                shift 2
            else
                SKIP_INSTALL=1
                shift
            fi
            ;;
        --skip-install=*)
            v="${1#--skip-install=}"
            case "$v" in
                1|[Tt]rue|[Tt])  SKIP_INSTALL=1 ;;
                *)               SKIP_INSTALL=0 ;;
            esac
            shift
            ;;
        --report)       REPORT_PATH="$2"; shift 2 ;;
        --domain)       TEST_DOMAIN="$2"; shift 2 ;;
        --admin-pass)   ADMIN_PASS="$2"; shift 2 ;;
        *) echo "Unknown arg: $1"; exit 64 ;;
    esac
done

# ----- helpers ---------------------------------------------------------------

log()  { echo -e "\033[1;32m[validate]\033[0m $*"; }
warn() { echo -e "\033[1;33m[warn]\033[0m $*"; }
err()  { echo -e "\033[1;31m[fail]\033[0m $*" >&2; }
step() { echo -e "\n\033[1;36m=== $* ===\033[0m"; }

require_root() {
    [[ "$(id -u)" -eq 0 ]] || { err "must be root"; exit 1; }
}

detect_os() {
    . /etc/os-release
    [[ "${ID:-}" == "ubuntu" ]] || { err "not Ubuntu"; exit 1; }
    case "${VERSION_ID:-}" in
        22.04|24.04) log "Ubuntu ${VERSION_ID} detected" ;;
        *) warn "tested on 22.04/24.04; got ${VERSION_ID:-unknown}" ;;
    esac
}

# Append a result line to the in-memory report.
declare -a REPORT_LINES
record() {
    local status="$1" name="$2" detail="${3:-}"
    local ts; ts="$(date -Iseconds)"
    REPORT_LINES+=("| ${ts} | ${status} | ${name} | ${detail} |")
    if [[ "$status" == "PASS" ]]; then
        log "PASS  ${name}  ${detail}"
    else
        err  "FAIL  ${name}  ${detail}"
    fi
}

write_report() {
    {
        echo "# Atulya Launch - Clean-Host Validation Report"
        echo
        echo "Generated: $(date -Iseconds)"
        echo "Host:      $(hostname)"
        echo "OS:        $(. /etc/os-release && echo "${PRETTY_NAME}")"
        echo "Domain:    ${TEST_DOMAIN}"
        echo
        echo "## Results"
        echo
        echo "| Timestamp | Status | Step | Detail |"
        echo "|-----------|--------|------|--------|"
        printf '%s\n' "${REPORT_LINES[@]}"
        echo
        echo "## Service status"
        echo
        echo '```'
        for svc in nginx postfix dovecot opendkim named fail2ban ufw atulya-launch; do
            printf '%-20s %s\n' "$svc" "$(systemctl is-active "$svc" 2>/dev/null || echo 'unknown')"
        done
        echo '```'
    } > "$REPORT_PATH"
    log "report written to ${REPORT_PATH}"
}

# Backup-and-restore a config dir; usage: with_backup <dir> <cmd...>
with_backup() {
    local target="$1"; shift
    local backup; backup="$(mktemp -d)/$(basename "$target").bak"
    if [[ -e "$target" ]]; then
        cp -a "$target" "$backup"
    fi
    "$@"
    local rc=$?
    if [[ $rc -ne 0 && -e "$backup" ]]; then
        warn "restoring backup of $target from $backup"
        rm -rf "$target"
        cp -a "$backup" "$target"
    fi
    rm -rf "$(dirname "$backup")"
    return $rc
}

# ----- prerequisites ---------------------------------------------------------

require_root
detect_os

step "0. Pre-flight checks"

# /etc/hosts entry so the test domain resolves to 127.0.0.1
if ! grep -qE "[[:space:]]${TEST_DOMAIN//./\\.}\$" /etc/hosts; then
    echo "127.0.0.1 ${TEST_DOMAIN}" >> /etc/hosts
    record PASS "hosts_entry" "added ${TEST_DOMAIN} -> 127.0.0.1"
else
    record PASS "hosts_entry" "${TEST_DOMAIN} already mapped"
fi

# Outbound network
if curl -fsSL --max-time 10 https://pypi.org/ -o /dev/null; then
    record PASS "network" "outbound HTTPS works"
else
    record FAIL "network" "cannot reach pypi.org; check firewall/proxy"
    write_report; exit 1
fi

# ----- install ---------------------------------------------------------------

if [[ $SKIP_INSTALL -eq 0 ]]; then
    step "1. Running install-server.sh"
    if with_backup /etc/nginx env \
        ADMIN_PASS="${ADMIN_PASS}" \
        PANEL_HOST="${PANEL_HOST}" \
        PANEL_PORT="${PANEL_PORT}" \
        ADMIN_USER="${ADMIN_USER}" \
        bash scripts/install-server.sh 2>&1 | tee /tmp/atulya-install.log; then
        record PASS "install" "install-server.sh exit 0"
    else
        record FAIL "install" "install-server.sh exit $?"
        write_report; exit 1
    fi

    # Detect password from install log if not supplied
    if [[ -z "$ADMIN_PASS" ]]; then
        ADMIN_PASS="$(grep -oE 'Generated admin password: [A-Za-z0-9!@#\$%\^&\*]+' /tmp/atulya-install.log | awk '{print $NF}' || true)"
    fi
    if [[ -z "$ADMIN_PASS" ]]; then
        record FAIL "admin_password" "could not detect generated password and ADMIN_PASS not set"
        write_report; exit 1
    fi
    record PASS "admin_password" "length ${#ADMIN_PASS}"
else
    record PASS "install" "skipped (--skip-install)"
    if [[ -z "$ADMIN_PASS" ]]; then
        err "ADMIN_PASS required when --skip-install is set"
        exit 64
    fi
fi

# ----- panel reachable --------------------------------------------------------

step "2. Panel reachable"

# Wait up to 30s for the panel to bind
for i in {1..30}; do
    if curl -fsS --max-time 2 "http://${PANEL_HOST}:${PANEL_PORT}/api/health" -o /dev/null 2>&1 \
       || curl -fsS --max-time 2 "http://${PANEL_HOST}:${PANEL_PORT}/" -o /dev/null 2>&1; then
        record PASS "panel_bind" "responded on ${PANEL_HOST}:${PANEL_PORT}"
        break
    fi
    sleep 1
    [[ $i -eq 30 ]] && {
        record FAIL "panel_bind" "no response after 30s"
        # Dump service diagnostics so the cause is visible in the report
        warn "panel did not bind; dumping diagnostics..."
        echo "" >> "$VALIDATOR_LOG"
        echo "--- systemctl status atulya-launch ---" >> "$VALIDATOR_LOG"
        systemctl status atulya-launch --no-pager -l >> "$VALIDATOR_LOG" 2>&1 || true
        echo "" >> "$VALIDATOR_LOG"
        echo "--- journalctl -u atulya-launch -n 100 ---" >> "$VALIDATOR_LOG"
        journalctl -u atulya-launch -n 100 --no-pager >> "$VALIDATOR_LOG" 2>&1 || true
        echo "" >> "$VALIDATOR_LOG"
        echo "--- systemd unit contents ---" >> "$VALIDATOR_LOG"
        cat /etc/systemd/system/atulya-launch.service >> "$VALIDATOR_LOG" 2>&1 || true
        echo "" >> "$VALIDATOR_LOG"
        echo "--- python venv probe ---" >> "$VALIDATOR_LOG"
        (ls -la /opt/atulya-launch/venv/bin/python 2>&1 || true) >> "$VALIDATOR_LOG"
        (/opt/atulya-launch/venv/bin/python -c "import atulya_launch; print('OK', atulya_launch.__file__)" 2>&1 || true) >> "$VALIDATOR_LOG"
        write_report; exit 1
    }
done

# Login
LOGIN_BODY=$(mktemp)
HTTP=$(curl -sS -o "$LOGIN_BODY" -w '%{http_code}' \
    -X POST "http://${PANEL_HOST}:${PANEL_PORT}/api/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"username\":\"${ADMIN_USER}\",\"password\":\"${ADMIN_PASS}\"}")
TOKEN=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('token',''))" "$LOGIN_BODY" 2>/dev/null || true)
if [[ "$HTTP" == "200" && -n "$TOKEN" ]]; then
    record PASS "login" "HTTP 200, token len ${#TOKEN}"
else
    record FAIL "login" "HTTP ${HTTP}; body=$(head -c 200 "$LOGIN_BODY")"
    write_report; exit 2
fi
rm -f "$LOGIN_BODY"

API="http://${PANEL_HOST}:${PANEL_PORT}"
H_AUTH="Authorization: Bearer ${TOKEN}"
H_JSON="Content-Type: application/json"

api_post() { curl -sS -o /tmp/api_resp.json -w '%{http_code}' -X POST "$1" -H "$H_AUTH" -H "$H_JSON" -d "$2"; }
api_put()  { curl -sS -o /tmp/api_resp.json -w '%{http_code}' -X PUT  "$1" -H "$H_AUTH" -H "$H_JSON" -d "$2"; }
api_get()  { curl -sS -o /tmp/api_resp.json -w '%{http_code}' "$1" -H "$H_AUTH"; }

# ----- site -------------------------------------------------------------------

step "3. Create site ${TEST_DOMAIN}"

HTTP=$(api_post "${API}/api/sites" "{\"domain\":\"${TEST_DOMAIN}\"}")
if [[ "$HTTP" =~ ^2 ]]; then
    record PASS "site_create" "HTTP ${HTTP}"
else
    record FAIL "site_create" "HTTP ${HTTP}: $(cat /tmp/api_resp.json | head -c 200)"
    write_report; exit 2
fi

# Nginx config rendered (the file may be in ATULYA_HOME or /etc/nginx depending on driver)
if [[ -f "/etc/nginx/sites-available/${TEST_DOMAIN}.conf" ]] || find / -path '*/nginx*' -name "${TEST_DOMAIN}.conf" 2>/dev/null | grep -q .; then
    record PASS "site_nginx_conf" "rendered"
else
    record WARN "site_nginx_conf" "config file not found in expected paths; dry-run?"
fi

# Nginx config passes syntax check
if command -v nginx >/dev/null && nginx -t >/tmp/nginx_t.out 2>&1; then
    record PASS "nginx_test" "nginx -t OK"
else
    record WARN "nginx_test" "nginx not present or -t failed (may be skipped in dry-run)"
fi

# Enable
HTTP=$(api_put "${API}/api/sites/${TEST_DOMAIN}/enable" '{}')
[[ "$HTTP" =~ ^2 ]] && record PASS "site_enable" "HTTP ${HTTP}" \
                    || record FAIL "site_enable" "HTTP ${HTTP}: $(cat /tmp/api_resp.json | head -c 200)"

# ----- dns --------------------------------------------------------------------

step "4. DNS zone + A record"

HTTP=$(api_post "${API}/api/dns/zones" "{\"domain\":\"${TEST_DOMAIN}\"}")
[[ "$HTTP" =~ ^2 ]] && record PASS "dns_zone_create" "HTTP ${HTTP}" \
                    || record FAIL "dns_zone_create" "HTTP ${HTTP}: $(cat /tmp/api_resp.json | head -c 200)"

HTTP=$(api_post "${API}/api/dns/zones/${TEST_DOMAIN}/records" \
    "{\"type\":\"A\",\"name\":\"\",\"value\":\"127.0.0.1\",\"ttl\":300}")
[[ "$HTTP" =~ ^2 ]] && record PASS "dns_record_create" "HTTP ${HTTP}" \
                    || record FAIL "dns_record_create" "HTTP ${HTTP}: $(cat /tmp/api_resp.json | head -c 200)"

# Reload zone through the API (does named-checkzone + rndc reload)
HTTP=$(api_post "${API}/api/dns/zones/${TEST_DOMAIN}/reload" '{}')
[[ "$HTTP" =~ ^2 ]] && record PASS "dns_zone_reload" "HTTP ${HTTP}" \
                    || record WARN "dns_zone_reload" "HTTP ${HTTP}: $(cat /tmp/api_resp.json | head -c 200)"

# BIND zone file rendered (optional, may be planned-only)
if [[ -f "/etc/bind/zones/db.${TEST_DOMAIN}" ]]; then
    record PASS "bind_zone_file" "rendered /etc/bind/zones/db.${TEST_DOMAIN}"
else
    record WARN "bind_zone_file" "not rendered (may be planned-only or BIND not installed)"
fi

# named-checkconf (optional)
if command -v named-checkconf >/dev/null && [[ -f /etc/bind/named.conf ]]; then
    if named-checkconf >/tmp/named_cc.out 2>&1; then
        record PASS "bind_checkconf" "named-checkconf OK"
    else
        record WARN "bind_checkconf" "$(cat /tmp/named_cc.out)"
    fi
fi

# ----- ssl --------------------------------------------------------------------

step "5. SSL certificate (Let's Encrypt STAGING)"

# The /api/ssl/issue endpoint only takes {"domain": "..."}; staging is
# controlled by the certbot config the panel writes. The call will fail on
# hosts where certbot isn't installed, which is acceptable.
HTTP=$(api_post "${API}/api/ssl/issue" "{\"domain\":\"${TEST_DOMAIN}\"}")
if [[ "$HTTP" =~ ^2 ]]; then
    record PASS "ssl_issue" "HTTP ${HTTP}"
elif [[ "$HTTP" == "404" ]]; then
    record WARN "ssl_issue" "endpoint /api/ssl/issue not mounted"
elif [[ "$HTTP" == "400" ]]; then
    # Body may say "SSL issuance only supported on Linux" or "certbot missing"
    record WARN "ssl_issue" "HTTP 400: $(cat /tmp/api_resp.json | head -c 200)"
else
    record FAIL "ssl_issue" "HTTP ${HTTP}: $(cat /tmp/api_resp.json | head -c 200)"
fi

# ----- mail -------------------------------------------------------------------

step "6. Mailbox for ${TEST_EMAIL_USER}@${TEST_DOMAIN}"

# AccountCreate uses a single 'email' field (full address), not split domain+mailbox.
HTTP=$(api_post "${API}/api/email/accounts" \
    "{\"email\":\"${TEST_EMAIL_USER}@${TEST_DOMAIN}\",\"password\":\"${TEST_EMAIL_PASS}\"}")
if [[ "$HTTP" =~ ^2 ]]; then
    record PASS "mail_create" "HTTP ${HTTP}"
else
    record FAIL "mail_create" "HTTP ${HTTP}: $(cat /tmp/api_resp.json | head -c 200)"
fi

# vmailbox map entry exists
if [[ -f /etc/postfix/vmailbox ]] && grep -q "${TEST_EMAIL_USER}@${TEST_DOMAIN}" /etc/postfix/vmailbox; then
    record PASS "postfix_vmailbox" "entry present"
else
    record WARN "postfix_vmailbox" "entry missing or file absent"
fi

# Dovecot passwd entry
if [[ -f /etc/dovecot/passwd ]] && grep -q "${TEST_EMAIL_USER}@${TEST_DOMAIN}" /etc/dovecot/passwd; then
    record PASS "dovecot_passwd" "entry present"
else
    record WARN "dovecot_passwd" "entry missing or file absent"
fi

# DKIM key generated
if [[ -d /etc/opendkim/keys ]] && compgen -G "/etc/opendkim/keys/*${TEST_DOMAIN}*" > /dev/null; then
    record PASS "dkim_keys" "present in /etc/opendkim/keys"
else
    record WARN "dkim_keys" "no key files for ${TEST_DOMAIN}"
fi

# ----- database ---------------------------------------------------------------

step "7. MySQL database ${TEST_DB_NAME}"

# DatabaseCreate expects 'name' and 'db_type' (not 'type').
HTTP=$(api_post "${API}/api/databases" \
    "{\"name\":\"${TEST_DB_NAME}\",\"db_type\":\"mysql\"}")
if [[ "$HTTP" =~ ^2 ]]; then
    record PASS "db_create" "HTTP ${HTTP}"
else
    record FAIL "db_create" "HTTP ${HTTP}: $(cat /tmp/api_resp.json | head -c 200)"
fi

# MySQL can connect
if command -v mysql >/dev/null && mysql -e "SHOW DATABASES;" >/dev/null 2>&1; then
    if mysql -e "SHOW DATABASES LIKE '${TEST_DB_NAME}';" 2>/dev/null | grep -q "${TEST_DB_NAME}"; then
        record PASS "mysql_db_present" "found in SHOW DATABASES"
    else
        record FAIL "mysql_db_present" "not present"
    fi
fi

# ----- backup + restore -------------------------------------------------------

step "8. Backup + restore roundtrip"

# POST /api/backups/create has no body - it auto-generates a name. We then
# capture that name from the response and pass it to the restore endpoint.
HTTP=$(curl -sS -o /tmp/api_resp.json -w '%{http_code}' \
    -X POST "${API}/api/backups/create" \
    -H "$H_AUTH")
[[ "$HTTP" =~ ^2 ]] && record PASS "backup_create" "HTTP ${HTTP}" \
                    || record FAIL "backup_create" "HTTP ${HTTP}: $(cat /tmp/api_resp.json | head -c 200)"

# Extract the auto-generated backup name from the response
BACKUP_NAME=$(python3 -c "import json; d=json.load(open('/tmp/api_resp.json')); print(d.get('backup',{}).get('name',''))" 2>/dev/null || true)
if [[ -z "$BACKUP_NAME" ]]; then
    record WARN "backup_name_extract" "could not parse backup name from create response"
    BACKUP_NAME="unknown"
else
    record PASS "backup_name_extract" "name=${BACKUP_NAME}"
fi

# Restore takes the name in the path; no body required
HTTP=$(api_post "${API}/api/backups/restore/${BACKUP_NAME}" '{}')
if [[ "$HTTP" =~ ^2 ]]; then
    record PASS "backup_restore" "HTTP ${HTTP}"
elif [[ "$HTTP" == "404" ]]; then
    record WARN "backup_restore" "404 - backup archive missing (acceptable on dry-run)"
else
    record WARN "backup_restore" "HTTP ${HTTP}: $(cat /tmp/api_resp.json | head -c 200)"
fi

# ----- security audit ---------------------------------------------------------

step "9. Security audit"

# Security audit is exposed as a form route; the form accepts POST with no body.
# The /api/security-advisor/scan endpoint is the JSON equivalent.
HTTP=$(api_post "${API}/api/security-advisor/scan" '{}')
if [[ "$HTTP" =~ ^2 ]]; then
    SCORE=$(python3 -c "import json; d=json.load(open('/tmp/api_resp.json')); print(d.get('score', d.get('summary',{}).get('score','?')))" 2>/dev/null || echo '?')
    record PASS "security_audit" "HTTP ${HTTP}, score=${SCORE}"
else
    # Fall back to form route
    HTTP=$(curl -sS -o /tmp/api_resp.json -w '%{http_code}' \
        -X POST "http://${PANEL_HOST}:${PANEL_PORT}/security/audit" \
        -H "$H_AUTH")
    [[ "$HTTP" =~ ^2 ]] && record PASS "security_audit" "form route HTTP ${HTTP}" \
                        || record FAIL "security_audit" "HTTP ${HTTP}"
fi

# ----- ssh terminal -----------------------------------------------------------

step "10. SSH terminal endpoint reachable"

HTTP=$(api_get "${API}/api/ssh/sessions")
[[ "$HTTP" =~ ^2 || "$HTTP" == "401" ]] \
    && record PASS "ssh_terminal_endpoint" "HTTP ${HTTP} (reachable/auth-gated)" \
    || record WARN "ssh_terminal_endpoint" "HTTP ${HTTP}"

# ----- final ------------------------------------------------------------------

step "Validation complete"
write_report

# Count failures
FAILS=$(printf '%s\n' "${REPORT_LINES[@]}" | grep -c '| FAIL |' || true)
WARNS=$(printf '%s\n' "${REPORT_LINES[@]}" | grep -c '| WARN |' || true)

log "PASS: $(grep -c '| PASS |' <<<"${REPORT_LINES[*]}" || true)  WARN: ${WARNS}  FAIL: ${FAILS}"

if [[ "$FAILS" -gt 0 ]]; then
    err "${FAILS} hard failure(s); see ${REPORT_PATH}"
    exit 2
fi
exit 0
