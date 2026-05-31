"""Cron job templates API."""

import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/cron", tags=["cron-templates"])

CRON_TEMPLATES = [
    {
        "id": "daily_backup",
        "name": "Daily Backup",
        "description": "Run full system backup every day at 2 AM",
        "schedule": "0 2 * * *",
        "command": "atulya-launch backup create --name daily_$(date +\\%Y\\%m\\%d)",
        "category": "backup",
        "icon": "database",
    },
    {
        "id": "logrotate",
        "name": "Log Rotation",
        "description": "Rotate and compress log files daily",
        "schedule": "0 0 * * *",
        "command": "/usr/sbin/logrotate -f /etc/logrotate.conf",
        "category": "maintenance",
        "icon": "refresh-cw",
    },
    {
        "id": "ssl_renew",
        "name": "SSL Certificate Renewal",
        "description": "Attempt SSL certificate renewal twice daily",
        "schedule": "0 3,15 * * *",
        "command": "certbot renew --non-interactive --quiet",
        "category": "ssl",
        "icon": "shield",
    },
    {
        "id": "health_check",
        "name": "Server Health Check",
        "description": "Check server health and send alerts if issues found",
        "schedule": "*/5 * * * *",
        "command": "atulya-launch monitor check --alert",
        "category": "monitoring",
        "icon": "activity",
    },
    {
        "id": "db_backup_mysql",
        "name": "MySQL Database Backup",
        "description": "Backup all MySQL databases",
        "schedule": "0 1 * * *",
        "command": "for db in $(mysql -N -e 'SHOW DATABASES' | grep -v 'information_schema\\|performance_schema\\|mysql'); do mysqldump $db | gzip > /var/backups/mysql/${db}_$(date +\\%Y\\%m\\%d).sql.gz; done",
        "category": "backup",
        "icon": "database",
    },
    {
        "id": "db_backup_postgres",
        "name": "PostgreSQL Database Backup",
        "description": "Backup all PostgreSQL databases",
        "schedule": "0 1 * * *",
        "command": "for db in $(sudo -u postgres psql -t -c \"SELECT datname FROM pg_database WHERE datistemplate = false;\"); do sudo -u postgres pg_dump $db | gzip > /var/backups/postgres/${db}_$(date +\\%Y\\%m\\%d).sql.gz; done",
        "category": "backup",
        "icon": "database",
    },
    {
        "id": "disk_usage_alert",
        "name": "Disk Usage Alert",
        "description": "Alert when disk usage exceeds 85%",
        "schedule": "0 */6 * * *",
        "command": "df -h / | awk 'NR==2{print $5}' | sed 's/%//' | xargs -I{} test {} -ge 85 && echo 'Disk usage critical' | mail -s 'Disk Alert' admin@localhost",
        "category": "monitoring",
        "icon": "alert-triangle",
    },
    {
        "id": "tmp_cleanup",
        "name": "Temp Directory Cleanup",
        "description": "Clean files older than 7 days from /tmp",
        "schedule": "0 3 * * 0",
        "command": "find /tmp -type f -atime +7 -delete 2>/dev/null; find /tmp -type d -empty -delete 2>/dev/null",
        "category": "maintenance",
        "icon": "trash-2",
    },
    {
        "id": "security_updates",
        "name": "Security Updates Check",
        "description": "Check for and install security updates weekly",
        "schedule": "0 4 * * 1",
        "command": "apt-get update -qq && apt-get upgrade -y -qq --only-upgrade $(apt-get -s upgrade 2>/dev/null | grep -i security | awk '{print $2}')",
        "category": "security",
        "icon": "shield",
    },
    {
        "id": "bandwidth_report",
        "name": "Bandwidth Report",
        "description": "Generate daily bandwidth usage report",
        "schedule": "0 0 * * *",
        "command": "vnstat --daily > /var/log/bandwidth_$(date +\\%Y\\%m\\%d).log 2>/dev/null || ifconfig > /var/log/bandwidth_$(date +\\%Y\\%m\\%d).log",
        "category": "monitoring",
        "icon": "bar-chart",
    },
    {
        "id": "fail2ban_unban",
        "name": "Fail2Ban Cleanup",
        "description": "Unban IPs banned more than 24 hours ago",
        "schedule": "0 */6 * * *",
        "command": "fail2ban-client set sshd unbanip $(fail2ban-client status sshd | grep 'Banned IP' | awk '{print $NF}') 2>/dev/null || true",
        "category": "security",
        "icon": "shield",
    },
    {
        "id": "nginx_cache_purge",
        "name": "Nginx Cache Purge",
        "description": "Purge nginx cache weekly",
        "schedule": "0 5 * * 0",
        "command": "rm -rf /var/cache/nginx/* && systemctl reload nginx",
        "category": "maintenance",
        "icon": "refresh-cw",
    },
]


class CronTemplateJob(BaseModel):
    template_id: str
    custom_schedule: Optional[str] = None
    custom_command: Optional[str] = None
    comment: Optional[str] = None


@router.get("/templates")
def list_cron_templates(category: Optional[str] = None, user: dict = Depends(get_current_user)):
    templates = CRON_TEMPLATES
    if category:
        templates = [t for t in templates if t["category"] == category]
    return {"templates": templates}


@router.get("/templates/{template_id}")
def get_cron_template(template_id: str, user: dict = Depends(get_current_user)):
    for template in CRON_TEMPLATES:
        if template["id"] == template_id:
            return {"template": template}
    raise HTTPException(status_code=404, detail="Template not found")


@router.post("/from-template")
def create_cron_from_template(body: CronTemplateJob, user: dict = Depends(get_current_user)):
    template = None
    for t in CRON_TEMPLATES:
        if t["id"] == body.template_id:
            template = t
            break

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    schedule = body.custom_schedule or template["schedule"]
    command = body.custom_command or template["command"]
    comment = body.comment or template["name"]

    comment_line = f"# {comment}\n"
    new_line = f"{comment_line}{schedule} {command}\n"

    current_cron = ""
    result = utils.run_command(["crontab", "-l"], check=False)
    if result and result.returncode == 0:
        current_cron = result.stdout

    import tempfile
    import os
    with tempfile.NamedTemporaryFile(mode="w", suffix=".cron", delete=False) as f:
        f.write(current_cron.rstrip() + "\n" + new_line)
        tmp = f.name

    try:
        utils.run_command(["crontab", tmp], check=False)
    finally:
        os.unlink(tmp)

    return {
        "status": "created",
        "template": body.template_id,
        "schedule": schedule,
        "command": command,
    }
