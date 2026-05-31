"""Postfix/Dovecot mail server configuration and management."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from .. import utils
from ..web.database import connect, audit_log


POSTFIX_CONF = Path("/etc/postfix")
DOVECOT_CONF = Path("/etc/dovecot")
POSTFIX_TEMPLATES = Path(__file__).parent.parent.parent / "templates" / "postfix"
DOVECOT_TEMPLATES = Path(__file__).parent.parent.parent / "templates" / "dovecot"
DKIM_DIR = Path("/etc/opendkim")
DKIM_KEYS_DIR = DKIM_DIR / "keys"


def is_mail_available() -> bool:
    """Check if Postfix/Dovecot are installed."""
    return utils.is_linux() and (
        utils.run_command(["which", "postfix"], check=False).returncode == 0 or
        utils.run_command(["which", "postconf"], check=False).returncode == 0
    )


def get_mail_status() -> dict[str, Any]:
    """Get the current status of mail services."""
    postfix_active = utils.run_command(["systemctl", "is-active", "postfix"], check=False).returncode == 0
    dovecot_active = utils.run_command(["systemctl", "is-active", "dovecot"], check=False).returncode == 0
    return {
        "postfix_installed": utils.run_command(["which", "postfix"], check=False).returncode == 0,
        "dovecot_installed": utils.run_command(["which", "dovecot"], check=False).returncode == 0,
        "postfix_active": postfix_active,
        "dovecot_active": dovecot_active,
        "config_dir": str(POSTFIX_CONF),
    }


def verify_mail_services() -> dict[str, Any]:
    """Verify mail service health and return detailed status."""
    status = get_mail_status()
    checks = []

    if status["postfix_installed"]:
        result = utils.run_command(["postfix", "check"], check=False)
        checks.append({"service": "postfix", "check": "config_test", "ok": result.returncode == 0})
    if status["dovecot_installed"]:
        result = utils.run_command(["doveconf", "-n"], check=False)
        checks.append({"service": "dovecot", "check": "config_test", "ok": result.returncode == 0})

    status["health_checks"] = checks
    status["healthy"] = status["postfix_active"] and status["dovecot_active"]
    return status


def configure_postfix(domain: str, myhostname: str | None = None) -> dict[str, Any]:
    """Configure Postfix for a domain."""
    if not is_mail_available():
        return {"ok": False, "error": "Postfix is not installed"}

    myhostname = myhostname or f"mail.{domain}"
    config = f"""# Atulya Launch Postfix Configuration for {domain}
myhostname = {myhostname}
mydomain = {domain}
myorigin = $mydomain
inet_interfaces = all
inet_protocols = ipv4
mydestination = $myhostname, localhost.$mydomain, localhost
relay_domains =
mynetworks = 127.0.0.0/8 [::ffff:127.0.0.0]/104 [::1]/128

# Virtual mailbox support
virtual_mailbox_domains = {domain}
virtual_mailbox_base = /var/mail/vhosts
virtual_mailbox_maps = hash:/etc/postfix/vmailbox
virtual_minimum_uid = 1000
virtual_uid_maps = static:5000
virtual_gid_maps = static:5000

# Authentication
smtpd_sasl_auth_enable = yes
smtpd_sasl_type = dovecot
smtpd_sasl_path = private/auth
smtpd_sasl_security_options = noanonymous

# TLS
smtpd_tls_cert_file = /etc/letsencrypt/live/{domain}/fullchain.pem
smtpd_tls_key_file = /etc/letsencrypt/live/{domain}/privkey.pem
smtpd_tls_security_level = may
smtp_tls_security_level = may

# Limits
message_size_limit = 52428800
mailbox_size_limit = 0
"""
    if utils.is_linux():
        POSTFIX_CONF.mkdir(parents=True, exist_ok=True)
        (POSTFIX_CONF / "main.cf").write_text(config)
        utils.run_command(["postfix", "reload"], check=False)
    audit_event("mail.postfix_config", "ok", {"domain": domain})
    return {"ok": True, "domain": domain}


def configure_dovecot(domain: str) -> dict[str, Any]:
    """Configure Dovecot for a domain."""
    if not is_mail_available():
        return {"ok": False, "error": "Dovecot is not installed"}

    config = f"""# Atulya Launch Dovecot Configuration for {domain}
protocols = imap pop3
listen = *,::

# SSL
ssl = required
ssl_cert = </etc/letsencrypt/live/{domain}/fullchain.pem
ssl_key = </etc/letsencrypt/live/{domain}/privkey.pem
ssl_min_protocol = TLSv1.2

# Authentication
auth_mechanisms = plain login
disable_plaintext_auth = yes

passdb {{
  driver = passwd-file
  args = /etc/dovecot/passwd
}}

userdb {{
  driver = passwd-file
  args = /etc/dovecot/passwd
}}

# Mailbox
mail_location = maildir:/var/mail/vhosts/%d/%n/Maildir
namespace inbox {{
  inbox = yes
  mailbox Drafts {{
    special_use = \\Drafts
    auto = subscribe
  }}
  mailbox Junk {{
    special_use = \\Junk
    auto = subscribe
  }}
  mailbox Sent {{
    special_use = \\Sent
    auto = subscribe
  }}
  mailbox Trash {{
    special_use = \\Trash
    auto = subscribe
  }}
}}

# Service
service auth {{
  unix_listener /var/spool/postfix/private/auth {{
    mode = 0660
    user = postfix
    group = postfix
  }}
}}
"""
    if utils.is_linux():
        DOVECOT_CONF.mkdir(parents=True, exist_ok=True)
        (DOVECOT_CONF / "dovecot.conf").write_text(config)
        utils.run_command(["doveconf", "-n"], check=False)
        utils.run_command(["systemctl", "restart", "dovecot"], check=False)
    audit_event("mail.dovecot_config", "ok", {"domain": domain})
    return {"ok": True, "domain": domain}


def _hash_password_dovecot(password: str) -> str:
    """Hash a password for Dovecot passwd-file format using SHA512-CRYPT."""
    try:
        from passlib.hash import sha512_crypt
        hashed = sha512_crypt.using(rounds=5000).hash(password)
        return f"{{SHA512-CRYPT}}{hashed}"
    except ImportError:
        return password


def add_mailbox(domain: str, mailbox: str, password: str) -> dict[str, Any]:
    """Add a virtual mailbox with proper Dovecot passwd format."""
    if not is_mail_available():
        return {"ok": False, "error": "Mail server is not installed"}

    mailbox_line = f"{mailbox}@{domain} {domain}/{mailbox}/\n"
    hashed_password = _hash_password_dovecot(password)
    passwd_line = f"{mailbox}@{domain}:{hashed_password}:5000:5000::/var/mail/vhosts/{domain}/{mailbox}::\n"

    if utils.is_linux():
        vmailbox = POSTFIX_CONF / "vmailbox"
        with open(vmailbox, "a") as f:
            f.write(mailbox_line)
        utils.run_command(["postmap", str(vmailbox)], check=False)

        passwd = DOVECOT_CONF / "passwd"
        with open(passwd, "a") as f:
            f.write(passwd_line)

        vhost_dir = Path(f"/var/mail/vhosts/{domain}/{mailbox}")
        vhost_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chown(str(vhost_dir), 5000, 5000)
        except (OSError, PermissionError):
            pass

        utils.run_command(["postfix", "reload"], check=False)
        utils.run_command(["doveconf", "-n"], check=False)

    audit_event("mail.add_mailbox", "ok", {"domain": domain, "mailbox": mailbox})
    return {"ok": True, "domain": domain, "mailbox": mailbox}


def remove_mailbox(domain: str, mailbox: str) -> dict[str, Any]:
    """Remove a virtual mailbox."""
    if not is_mail_available():
        return {"ok": False, "error": "Mail server is not installed"}

    if utils.is_linux():
        vmailbox = POSTFIX_CONF / "vmailbox"
        if vmailbox.exists():
            content = vmailbox.read_text()
            line = f"{mailbox}@{domain} {domain}/{mailbox}/\n"
            content = content.replace(line, "")
            vmailbox.write_text(content)
            utils.run_command(["postmap", str(vmailbox)], check=False)

        passwd = DOVECOT_CONF / "passwd"
        if passwd.exists():
            content = passwd.read_text()
            lines = content.splitlines()
            lines = [l for l in lines if not l.startswith(f"{mailbox}@{domain}:")]
            passwd.write_text("\n".join(lines) + "\n")

        vhost_dir = Path(f"/var/mail/vhosts/{domain}/{mailbox}")
        if vhost_dir.exists():
            import shutil
            shutil.rmtree(vhost_dir)

        utils.run_command(["postfix", "reload"], check=False)

    audit_event("mail.remove_mailbox", "ok", {"domain": domain, "mailbox": mailbox})
    return {"ok": True, "domain": domain, "mailbox": mailbox}


def list_mailboxes(domain: str) -> list[dict[str, str]]:
    """List all mailboxes for a domain."""
    mailboxes = []
    if utils.is_linux():
        passwd = DOVECOT_CONF / "passwd"
        if passwd.exists():
            for line in passwd.read_text().splitlines():
                if line.startswith(f"{domain}"):
                    mailbox = line.split(":")[0].split("@")[0]
                    mailboxes.append({"mailbox": mailbox, "domain": domain})
    return mailboxes


def configure_dkim(domain: str, selector: str = "default") -> dict[str, Any]:
    """Configure OpenDKIM for a domain with DNS-01 support."""
    if not utils.is_linux():
        return {"ok": False, "error": "DKIM configuration only supported on Linux"}

    DKIM_KEYS_DIR.mkdir(parents=True, exist_ok=True)

    key_path = DKIM_KEYS_DIR / f"{selector}._domainkey.{domain}.private"
    txt_path = DKIM_KEYS_DIR / f"{selector}._domainkey.{domain}.txt"

    result = utils.run_command([
        "opendkim-genkey",
        "-b", "2048",
        "-d", domain,
        "-D", str(DKIM_KEYS_DIR),
        "-s", selector,
        "-v",
    ], check=False)

    if result and result.returncode != 0:
        return {"ok": False, "error": f"opendkim-genkey failed: {result.stderr if result else 'unknown error'}"}

    try:
        os.chown(str(key_path), 106, 106)
    except (OSError, PermissionError):
        pass

    dkim_config = f"""AutoRestart Yes
AutoRestartRate 10/1M
Background Yes
Canonicalization relaxed/simple
ExternalIgnoreList refile:/etc/opendkim/TrustedHosts
InternalHosts refile:/etc/opendkim/TrustedHosts
KeyTable refile:/etc/opendkim/KeyTable
SigningTable refile:/etc/opendkim/SigningTable
LogWhy Yes
Mode sv
PidFile /run/opendkim/opendkim.pid
SignatureAlgorithm rsa-sha256
Socket inet:8891@localhost
SyslogSuccess Yes
TemporaryDirectory /var/tmp
UMask 007
UserID opendkim:opendkim
"""
    config_path = DKIM_DIR / "opendkim.conf"
    config_path.write_text(dkim_config)

    trusted_hosts = DKIM_DIR / "TrustedHosts"
    trusted_hosts.write_text(f"127.0.0.1\n::1\nlocalhost\n{domain}\n")

    key_table = DKIM_DIR / "KeyTable"
    key_table.write_text(f"{selector}._domainkey.{domain} {domain}:{selector}:{key_path}\n")

    signing_table = DKIM_DIR / "SigningTable"
    signing_table.write_text(f"*@{domain} {selector}._domainkey.{domain}\n")

    utils.run_command(["systemctl", "restart", "opendkim"], check=False)
    utils.run_command(["postfix", "reload"], check=False)

    txt_record = ""
    if txt_path.exists():
        txt_record = txt_path.read_text().strip()

    audit_event("mail.dkim_config", "ok", {"domain": domain, "selector": selector})
    return {"ok": True, "domain": domain, "selector": selector, "txt_record": txt_record}
