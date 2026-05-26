import os
import sys
import yaml
import shutil
import json
import datetime
from pathlib import Path

from . import utils


NGINX_AVAILABLE = "/etc/nginx/sites-available"
NGINX_ENABLED = "/etc/nginx/sites-enabled"
APACHE_AVAILABLE = "/etc/apache2/sites-available"
APACHE_ENABLED = "/etc/apache2/sites-enabled"


def detect_web_server():
    if Path(NGINX_AVAILABLE).exists():
        return "nginx"
    if Path(APACHE_AVAILABLE).exists():
        return "apache"
    return None


def site_create(domain_name, web_root=None, server_type=None, php_enabled=False, extra_config=None):
    if server_type is None:
        server_type = detect_web_server() or "nginx"
    if web_root is None:
        web_root = f"/var/www/{domain_name}/public"
    Path(web_root).mkdir(parents=True, exist_ok=True)

    site_data = {
        "domain": domain_name,
        "web_root": web_root,
        "server_type": server_type,
        "php_enabled": php_enabled,
        "extra_config": extra_config or {},
        "enabled": True,
        "created_at": datetime.datetime.now().isoformat(),
    }

    config_content = _generate_server_config(domain_name, web_root, server_type, php_enabled, extra_config)
    available_dir = NGINX_AVAILABLE if server_type == "nginx" else APACHE_AVAILABLE
    enabled_dir = NGINX_ENABLED if server_type == "nginx" else APACHE_ENABLED

    config_path = Path(available_dir) / domain_name
    with open(config_path, "w") as file_handle:
        file_handle.write(config_content)

    symlink_path = Path(enabled_dir) / domain_name
    if not symlink_path.exists():
        symlink_path.symlink_to(config_path)

    sites_config = utils.load_config().get("sites", {})
    sites_config[domain_name] = site_data
    all_config = utils.load_config()
    all_config["sites"] = sites_config
    utils.save_config(all_config)

    if server_type == "nginx":
        utils.run_command(["nginx", "-t"], check=False)
        utils.service_action("reload", "nginx")
    else:
        utils.run_command(["apache2ctl", "configtest"], check=False)
        utils.service_action("reload", "apache2")

    return site_data


def _generate_server_config(domain_name, web_root, server_type, php_enabled, extra_config):
    if server_type == "nginx":
        return _generate_nginx_config(domain_name, web_root, php_enabled, extra_config)
    return _generate_apache_config(domain_name, web_root, php_enabled, extra_config)


def _generate_nginx_config(domain_name, web_root, php_enabled, extra_config):
    lines = [
        f"server {{",
        f"    listen 80;",
        f"    listen [::]:80;",
        f"    server_name {domain_name} www.{domain_name};",
        f"    root {web_root};",
        f"    index index.html index.htm index.nginx-debian.html;",
        f"",
        f"    location / {{",
        f"        try_files $uri $uri/ =404;",
        f"    }}",
    ]

    if php_enabled:
        lines.extend([
            f"",
            f"    location ~ \\.php$ {{",
            f"        include snippets/fastcgi-php.conf;",
            f"        fastcgi_pass unix:/var/run/php/php8.1-fpm.sock;",
            f"    }}",
        ])

    extra = extra_config or {}
    if extra.get("proxy_pass"):
        lines.extend([
            f"",
            f"    location / {{",
            f"        proxy_pass {extra['proxy_pass']};",
            f"        proxy_set_header Host $host;",
            f"        proxy_set_header X-Real-IP $remote_addr;",
            f"        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
            f"        proxy_set_header X-Forwarded-Proto $scheme;",
            f"    }}",
        ])

    lines.append(f"}}")
    return "\n".join(lines)


def _generate_apache_config(domain_name, web_root, php_enabled, extra_config):
    lines = [
        f"<VirtualHost *:80>",
        f"    ServerName {domain_name}",
        f"    ServerAlias www.{domain_name}",
        f"    DocumentRoot {web_root}",
        f"",
        f"    <Directory {web_root}>",
        f"        Options Indexes FollowSymLinks",
        f"        AllowOverride All",
        f"        Require all granted",
        f"    </Directory>",
    ]

    if php_enabled:
        lines.extend([
            f"",
            f"    <FilesMatch \\.php$>",
            f"        SetHandler application/x-httpd-php",
            f"    </FilesMatch>",
        ])

    extra = extra_config or {}
    if extra.get("proxy_pass"):
        lines.extend([
            f"",
            f"    ProxyPreserveHost On",
            f"    ProxyPass / {extra['proxy_pass']}",
            f"    ProxyPassReverse / {extra['proxy_pass']}",
        ])

    lines.append(f"</VirtualHost>")
    return "\n".join(lines)


def site_list():
    return utils.load_config().get("sites", {})


def site_delete(domain_name):
    sites_config = utils.load_config().get("sites", {})
    if domain_name not in sites_config:
        return False

    site_data = sites_config[domain_name]
    server_type = site_data.get("server_type", detect_web_server() or "nginx")
    available_dir = NGINX_AVAILABLE if server_type == "nginx" else APACHE_AVAILABLE
    enabled_dir = NGINX_ENABLED if server_type == "nginx" else APACHE_ENABLED

    config_path = Path(available_dir) / domain_name
    symlink_path = Path(enabled_dir) / domain_name

    if symlink_path.exists():
        symlink_path.unlink()
    if config_path.exists():
        config_path.unlink()

    del sites_config[domain_name]
    all_config = utils.load_config()
    all_config["sites"] = sites_config
    utils.save_config(all_config)

    if server_type == "nginx":
        utils.service_action("reload", "nginx")
    else:
        utils.service_action("reload", "apache2")
    return True


def site_toggle(domain_name, enable=True):
    sites_config = utils.load_config().get("sites", {})
    if domain_name not in sites_config:
        return False

    site_data = sites_config[domain_name]
    server_type = site_data.get("server_type", detect_web_server() or "nginx")
    available_dir = NGINX_AVAILABLE if server_type == "nginx" else APACHE_AVAILABLE
    enabled_dir = NGINX_ENABLED if server_type == "nginx" else APACHE_ENABLED

    config_path = Path(available_dir) / domain_name
    symlink_path = Path(enabled_dir) / domain_name

    if enable:
        if not symlink_path.exists():
            symlink_path.symlink_to(config_path)
        sites_config[domain_name]["enabled"] = True
    else:
        if symlink_path.exists():
            symlink_path.unlink()
        sites_config[domain_name]["enabled"] = False

    all_config = utils.load_config()
    all_config["sites"] = sites_config
    utils.save_config(all_config)

    if server_type == "nginx":
        utils.service_action("reload", "nginx")
    else:
        utils.service_action("reload", "apache2")
    return True


def ssl_issue(domain_name, email, web_root=None, use_staging=False):
    if not utils.is_linux():
        return {"error": "SSL certificate issuance is only supported on Linux"}
    if web_root is None:
        sites_config = utils.load_config().get("sites", {})
        if domain_name in sites_config:
            web_root = sites_config[domain_name].get("web_root", f"/var/www/{domain_name}/public")
        else:
            web_root = f"/var/www/{domain_name}/public"

    ssl_data = {
        "domain": domain_name,
        "email": email,
        "web_root": web_root,
        "issued_at": None,
        "expires_at": None,
        "staging": use_staging,
    }

    certbot_args = [
        "certbot", "certonly", "--webroot",
        "-w", web_root,
        "-d", domain_name,
        "--non-interactive",
        "--agree-tos",
        "-m", email,
    ]
    if use_staging:
        certbot_args.append("--staging")

    result = utils.run_command(certbot_args, check=False)
    if result and result.returncode == 0:
        ssl_data["issued_at"] = datetime.datetime.now().isoformat()
        ssl_data["expires_at"] = (datetime.datetime.now() + datetime.timedelta(days=90)).isoformat()
        ssl_data["cert_path"] = f"/etc/letsencrypt/live/{domain_name}/fullchain.pem"
        ssl_data["key_path"] = f"/etc/letsencrypt/live/{domain_name}/privkey.pem"

    ssl_config = utils.load_config().get("ssl", {})
    ssl_config[domain_name] = ssl_data
    all_config = utils.load_config()
    all_config["ssl"] = ssl_config
    utils.save_config(all_config)

    return ssl_data


def ssl_list():
    return utils.load_config().get("ssl", {})


def ssl_renew():
    if not utils.is_linux():
        return {"error": "SSL renewal is only supported on Linux"}
    result = utils.run_command(["certbot", "renew", "--non-interactive"], check=False)
    if result and result.returncode == 0:
        cert_data = ssl_list()
        for domain_name in cert_data:
            cert_data[domain_name]["expires_at"] = (datetime.datetime.now() + datetime.timedelta(days=90)).isoformat()
        all_config = utils.load_config()
        all_config["ssl"] = cert_data
        utils.save_config(all_config)
        return {"status": "renewed", "domains": list(cert_data.keys())}
    return {"status": "failed"}


def db_create(db_name, db_user=None, db_password=None, db_type="mysql"):
    if not utils.is_linux():
        return {"error": f"Database creation is only supported on Linux"}
    if db_user is None:
        db_user = db_name
    if db_password is None:
        db_password = utils.generate_password()

    if db_type == "mysql":
        create_db_cmd = f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
        create_user_cmd = f"CREATE USER IF NOT EXISTS '{db_user}'@'localhost' IDENTIFIED BY '{db_password}';"
        grant_cmd = f"GRANT ALL PRIVILEGES ON `{db_name}`.* TO '{db_user}'@'localhost';"
        flush_cmd = "FLUSH PRIVILEGES;"
        full_sql = f"{create_db_cmd} {create_user_cmd} {grant_cmd} {flush_cmd}"
        result = utils.run_command(["mysql", "-e", full_sql], check=False)
    elif db_type == "postgresql":
        result = utils.run_command(
            ["sudo", "-u", "postgres", "psql", "-c", f"CREATE DATABASE {db_name};"],
            check=False,
        )
        if result and result.returncode == 0:
            utils.run_command(
                ["sudo", "-u", "postgres", "psql", "-c",
                 f"CREATE USER {db_user} WITH PASSWORD '{db_password}';"],
                check=False,
            )
            utils.run_command(
                ["sudo", "-u", "postgres", "psql", "-c",
                 f"GRANT ALL PRIVILEGES ON DATABASE {db_name} TO {db_user};"],
                check=False,
            )
    else:
        return {"error": f"Unsupported database type: {db_type}"}

    db_record = {
        "name": db_name,
        "user": db_user,
        "password": db_password,
        "type": db_type,
        "created_at": datetime.datetime.now().isoformat(),
    }

    dbs_config = utils.load_config().get("databases", {})
    dbs_config[db_name] = db_record
    all_config = utils.load_config()
    all_config["databases"] = dbs_config
    utils.save_config(all_config)

    return db_record


def db_list():
    return utils.load_config().get("databases", {})


def db_backup(db_name, output_path=None):
    dbs_config = utils.load_config().get("databases", {})
    if db_name not in dbs_config:
        return {"error": f"Database '{db_name}' not found in configuration"}
    db_record = dbs_config[db_name]
    db_type = db_record.get("type", "mysql")

    if output_path is None:
        backup_dir = utils.CONFIG_DIR / "backups"
        backup_dir.mkdir(exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = str(backup_dir / f"{db_name}_{timestamp}.sql.gz")

    if db_type == "mysql":
        result = utils.run_command(
            f"mysqldump {db_name} | gzip > {output_path}",
            check=False,
        )
    elif db_type == "postgresql":
        result = utils.run_command(
            f"pg_dump {db_name} | gzip > {output_path}",
            check=False,
        )
    else:
        return {"error": f"Unsupported database type: {db_type}"}

    if result and result.returncode == 0:
        return {"path": output_path, "size": Path(output_path).stat().st_size}
    return {"error": f"Backup failed for database '{db_name}'"}


def db_restore(db_name, backup_path, db_type="mysql"):
    if not Path(backup_path).exists():
        return {"error": f"Backup file not found: {backup_path}"}

    if db_type == "mysql":
        result = utils.run_command(
            f"gunzip < {backup_path} | mysql {db_name}",
            check=False,
        )
    elif db_type == "postgresql":
        result = utils.run_command(
            f"gunzip < {backup_path} | psql {db_name}",
            check=False,
        )
    else:
        return {"error": f"Unsupported database type: {db_type}"}

    if result and result.returncode == 0:
        return {"status": "restored", "database": db_name}
    return {"error": f"Restore failed for database '{db_name}'"}


def user_add(username, password=None, shell="/bin/bash", create_home=True, add_to_groups=None):
    if not utils.is_linux():
        return {"error": "User management is only supported on Linux"}

    if password is None:
        password = utils.generate_password()

    useradd_args = ["useradd"]
    if create_home:
        useradd_args.append("-m")
    useradd_args.extend(["-s", shell])
    useradd_args.append(username)

    result = utils.run_command(useradd_args, check=False)
    if result and result.returncode != 0:
        return {"error": f"Failed to create user '{username}'"}

    passwd_result = utils.run_command(
        f"echo '{username}:{password}' | chpasswd",
        check=False,
    )

    groups_added = []
    if add_to_groups:
        for group in add_to_groups:
            group_result = utils.run_command(
                ["usermod", "-aG", group, username],
                check=False,
            )
            if group_result and group_result.returncode == 0:
                groups_added.append(group)

    ftp_dir = f"/home/{username}/ftp"
    Path(ftp_dir).mkdir(parents=True, exist_ok=True)
    utils.run_command(["chown", f"{username}:{username}", ftp_dir], check=False)

    user_record = {
        "username": username,
        "shell": shell,
        "home": f"/home/{username}",
        "ftp_dir": ftp_dir,
        "groups": groups_added,
        "created_at": datetime.datetime.now().isoformat(),
    }

    users_config = utils.load_config().get("users", {})
    users_config[username] = user_record
    all_config = utils.load_config()
    all_config["users"] = users_config
    utils.save_config(all_config)

    user_record["password"] = password
    return user_record


def user_list():
    return utils.load_config().get("users", {})


def user_delete(username, remove_home=True):
    if not utils.is_linux():
        return {"error": "User management is only supported on Linux"}
    users_config = utils.load_config().get("users", {})
    if username not in users_config:
        return {"error": f"User '{username}' not found"}

    userdel_args = ["userdel"]
    if remove_home:
        userdel_args.append("-r")
    userdel_args.append(username)

    result = utils.run_command(userdel_args, check=False)
    if result and result.returncode != 0:
        return {"error": f"Failed to delete user '{username}'"}

    del users_config[username]
    all_config = utils.load_config()
    all_config["users"] = users_config
    utils.save_config(all_config)
    return {"status": "deleted", "username": username}


def backup_create(name=None, include_databases=True, include_sites=True, include_config=True, destination=None):
    if name is None:
        name = f"backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"

    backup_dir = utils.CONFIG_DIR / "backups" / name
    backup_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "name": name,
        "created_at": datetime.datetime.now().isoformat(),
        "includes": {},
    }

    if include_config:
        config_backup = backup_dir / "config.yaml"
        shutil.copy2(str(utils.CONFIG_FILE), str(config_backup))
        manifest["includes"]["config"] = True

    if include_sites:
        sites_backup = backup_dir / "sites"
        sites_backup.mkdir(exist_ok=True)
        sites_config = utils.load_config().get("sites", {})
        for domain_name in sites_config:
            site_dir = sites_backup / domain_name
            site_dir.mkdir(exist_ok=True)
            site_data = sites_config[domain_name]
            data_file = site_dir / "data.json"
            with open(data_file, "w") as file_handle:
                json.dump(site_data, file_handle, indent=2)
        manifest["includes"]["sites"] = list(sites_config.keys())

    if include_databases:
        db_backup_dir = backup_dir / "databases"
        db_backup_dir.mkdir(exist_ok=True)
        dbs_config = utils.load_config().get("databases", {})
        for db_name in dbs_config:
            db_backup(db_name, str(db_backup_dir / f"{db_name}.sql.gz"))
        manifest["includes"]["databases"] = list(dbs_config.keys())

    manifest_path = backup_dir / "manifest.json"
    with open(manifest_path, "w") as file_handle:
        json.dump(manifest, file_handle, indent=2)

    archive_path = None
    if destination:
        archive_name = f"{name}.tar.gz"
        archive_path = str(Path(destination) / archive_name)
        utils.run_command(
            f"tar -czf {archive_path} -C {str(backup_dir.parent)} {name}",
            check=False,
        )

    return {
        "name": name,
        "path": str(backup_dir),
        "archive": archive_path,
        "manifest": manifest,
    }


def backup_list():
    backup_dir = utils.CONFIG_DIR / "backups"
    if not backup_dir.exists():
        return {}
    backups = {}
    for item in backup_dir.iterdir():
        if item.is_dir():
            manifest_path = item / "manifest.json"
            if manifest_path.exists():
                with open(manifest_path, "r") as file_handle:
                    backups[item.name] = json.load(file_handle)
            else:
                backups[item.name] = {
                    "name": item.name,
                    "created_at": datetime.datetime.fromtimestamp(item.stat().st_mtime).isoformat(),
                }
    return backups


def backup_restore(name, restore_databases=True, restore_sites=True, restore_config=True):
    backup_dir = utils.CONFIG_DIR / "backups" / name
    if not backup_dir.exists():
        return {"error": f"Backup '{name}' not found"}

    manifest_path = backup_dir / "manifest.json"
    if manifest_path.exists():
        with open(manifest_path, "r") as file_handle:
            manifest = json.load(file_handle)
    else:
        manifest = {}

    if restore_config:
        config_backup = backup_dir / "config.yaml"
        if config_backup.exists():
            shutil.copy2(str(config_backup), str(utils.CONFIG_FILE))

    if restore_sites:
        sites_backup = backup_dir / "sites"
        if sites_backup.exists():
            for site_dir in sites_backup.iterdir():
                if site_dir.is_dir():
                    data_file = site_dir / "data.json"
                    if data_file.exists():
                        with open(data_file, "r") as file_handle:
                            site_data = json.load(file_handle)
                        domain_name = site_data.get("domain", site_dir.name)
                        site_create(
                            domain_name=domain_name,
                            web_root=site_data.get("web_root"),
                            server_type=site_data.get("server_type"),
                            php_enabled=site_data.get("php_enabled", False),
                            extra_config=site_data.get("extra_config"),
                        )

    if restore_databases:
        db_backup_dir = backup_dir / "databases"
        if db_backup_dir.exists():
            dbs_config = utils.load_config().get("databases", {})
            for db_file in db_backup_dir.glob("*.sql.gz"):
                db_name = db_file.stem.replace(".sql", "")
                db_type = "mysql"
                if db_name in dbs_config:
                    db_type = dbs_config[db_name].get("type", "mysql")
                db_restore(db_name, str(db_file), db_type)

    return {"status": "restored", "backup": name}


def backup_schedule(interval, time_str, enabled=True, keep_days=30):
    if not utils.is_linux():
        return {"error": "Backup scheduling via cron is only supported on Linux"}

    backup_script = str(utils.CONFIG_DIR / "scripts" / "scheduled_backup.sh")
    scripts_dir = Path(backup_script).parent
    scripts_dir.mkdir(exist_ok=True)

    with open(backup_script, "w") as file_handle:
        file_handle.write("#!/bin/bash\n")
        file_handle.write(f"cd {utils.CONFIG_DIR}\n")
        file_handle.write(f"{sys.executable} -m atulya_launch.cli backup create\n")

    Path(backup_script).chmod(0o755)

    cron_map = {
        "daily": f"{time_str} * * *",
        "weekly": f"{time_str} * * 0",
        "monthly": f"{time_str} 1 * *",
        "hourly": f"{time_str} * * * *",
    }
    cron_time = cron_map.get(interval, f"{time_str} * * *")

    cron_job = f"{cron_time} {backup_script}"
    temp_cron = utils.CONFIG_DIR / "temp_cron"
    utils.run_command(f"crontab -l > {temp_cron} 2>/dev/null; echo '{cron_job}' >> {temp_cron}; crontab {temp_cron}", check=False)

    schedule_record = {
        "interval": interval,
        "time": time_str,
        "enabled": enabled,
        "keep_days": keep_days,
        "script": backup_script,
    }

    all_config = utils.load_config()
    all_config["backup_schedule"] = schedule_record
    utils.save_config(all_config)

    return schedule_record


def monitor_status():
    import psutil
    cpu_percent = psutil.cpu_percent(interval=1)
    cpu_count = psutil.cpu_count()
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    net = psutil.net_io_counters()
    boot_time = datetime.datetime.fromtimestamp(psutil.boot_time())
    uptime_delta = datetime.datetime.now() - boot_time
    uptime_hours = uptime_delta.total_seconds() / 3600

    return {
        "cpu": {
            "percent": cpu_percent,
            "count": cpu_count,
        },
        "memory": {
            "total": memory.total,
            "available": memory.available,
            "percent": memory.percent,
            "used": memory.used,
            "free": memory.free,
        },
        "disk": {
            "total": disk.total,
            "used": disk.used,
            "free": disk.free,
            "percent": disk.percent,
        },
        "network": {
            "bytes_sent": net.bytes_sent,
            "bytes_recv": net.bytes_recv,
            "packets_sent": net.packets_sent,
            "packets_recv": net.packets_recv,
        },
        "uptime": {
            "boot_time": boot_time.isoformat(),
            "uptime_hours": round(uptime_hours, 2),
        },
    }


def monitor_processes(sort_by="cpu", limit=20):
    import psutil
    processes = []
    for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status", "username"]):
        try:
            processes.append(proc.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    if sort_by == "cpu":
        processes.sort(key=lambda p: p.get("cpu_percent", 0) or 0, reverse=True)
    elif sort_by == "memory":
        processes.sort(key=lambda p: p.get("memory_percent", 0) or 0, reverse=True)

    return processes[:limit]


def monitor_logs(log_type="system", lines=50):
    if not utils.is_linux():
        return {"error": "Log viewing is only supported on Linux"}

    log_paths = {
        "system": "/var/log/syslog",
        "auth": "/var/log/auth.log",
        "nginx": "/var/log/nginx/error.log",
        "apache": "/var/log/apache2/error.log",
        "mysql": "/var/log/mysql/error.log",
    }

    log_file = log_paths.get(log_type, log_paths["system"])
    if not Path(log_file).exists():
        return {"error": f"Log file not found: {log_file}"}

    result = utils.run_command(["tail", "-n", str(lines), log_file], check=False)
    if result and result.returncode == 0:
        return {"log_type": log_type, "lines": result.stdout.splitlines()}
    return {"error": f"Could not read log file: {log_file}"}


def monitor_alerts():
    status_data = monitor_status()
    alerts = []

    if status_data["cpu"]["percent"] > 90:
        alerts.append({
            "level": "critical",
            "source": "cpu",
            "message": f"CPU usage at {status_data['cpu']['percent']}%",
            "timestamp": datetime.datetime.now().isoformat(),
        })
    elif status_data["cpu"]["percent"] > 75:
        alerts.append({
            "level": "warning",
            "source": "cpu",
            "message": f"CPU usage at {status_data['cpu']['percent']}%",
            "timestamp": datetime.datetime.now().isoformat(),
        })

    if status_data["memory"]["percent"] > 90:
        alerts.append({
            "level": "critical",
            "source": "memory",
            "message": f"Memory usage at {status_data['memory']['percent']}%",
            "timestamp": datetime.datetime.now().isoformat(),
        })
    elif status_data["memory"]["percent"] > 75:
        alerts.append({
            "level": "warning",
            "source": "memory",
            "message": f"Memory usage at {status_data['memory']['percent']}%",
            "timestamp": datetime.datetime.now().isoformat(),
        })

    if status_data["disk"]["percent"] > 90:
        alerts.append({
            "level": "critical",
            "source": "disk",
            "message": f"Disk usage at {status_data['disk']['percent']}%",
            "timestamp": datetime.datetime.now().isoformat(),
        })
    elif status_data["disk"]["percent"] > 80:
        alerts.append({
            "level": "warning",
            "source": "disk",
            "message": f"Disk usage at {status_data['disk']['percent']}%",
            "timestamp": datetime.datetime.now().isoformat(),
        })

    return alerts


def ai_deploy(model_name, model_path, port=8000, workers=1, python_version="3.10"):
    if not utils.is_linux():
        return {"error": "AI model deployment is only supported on Linux"}

    ai_models_dir = utils.CONFIG_DIR / "ai-models" / model_name
    ai_models_dir.mkdir(parents=True, exist_ok=True)

    api_script = ai_models_dir / "app.py"
    api_content = [
        "import json",
        "from http.server import HTTPServer, BaseHTTPRequestHandler",
        "",
        f"MODEL_PATH = r'{model_path}'",
        "",
        "",
        "class ModelHandler(BaseHTTPRequestHandler):",
        "",
        "    def do_POST(self):",
        "        content_length = int(self.headers.get('Content-Length', 0))",
        "        body = self.rfile.read(content_length)",
        "        try:",
        "            data = json.loads(body)",
        "            result = {'status': 'ok', 'model': MODEL_PATH, 'input': data}",
        "        except Exception as error:",
        "            result = {'status': 'error', 'message': str(error)}",
        "        self.send_response(200)",
        "        self.send_header('Content-Type', 'application/json')",
        "        self.end_headers()",
        "        self.wfile.write(json.dumps(result).encode())",
        "",
        "    def do_GET(self):",
        "        self.send_response(200)",
        "        self.send_header('Content-Type', 'application/json')",
        "        self.end_headers()",
        "        info = {'model': MODEL_NAME, 'status': 'running', 'port': PORT}",
        "        self.wfile.write(json.dumps(info).encode())",
        "",
        "",
        'if __name__ == "__main__":',
        f"    MODEL_NAME = {repr(model_name)}",
        f"    PORT = {port}",
        "    server = HTTPServer(('0.0.0.0', PORT), ModelHandler)",
        f"    print(f'Model {MODEL_NAME} listening on port {{PORT}}')",
        "    server.serve_forever()",
    ]

    with open(api_script, "w") as file_handle:
        file_handle.write("\n".join(api_content))

    service_name = f"atulya-ai-{model_name}"
    service_content = [
        "[Unit]",
        f"Description=Atulya AI Model - {model_name}",
        "After=network.target",
        "",
        "[Service]",
        f"WorkingDirectory={ai_models_dir}",
        f"ExecStart={sys.executable} {api_script}",
        f"User={os.environ.get('USER', 'root')}",
        "Restart=always",
        f"RestartSec={5}",
        "",
        "[Install]",
        "WantedBy=multi-user.target",
    ]

    if utils.is_linux():
        service_path = Path(f"/etc/systemd/system/{service_name}.service")
        if service_path.parent.exists():
            with open(service_path, "w") as file_handle:
                file_handle.write("\n".join(service_content))
            utils.run_command(["systemctl", "daemon-reload"], check=False)
            utils.run_command(["systemctl", "enable", service_name], check=False)
            utils.run_command(["systemctl", "start", service_name], check=False)

    ai_record = {
        "name": model_name,
        "model_path": model_path,
        "port": port,
        "workers": workers,
        "service_name": service_name,
        "api_script": str(api_script),
        "status": "deployed",
        "deployed_at": datetime.datetime.now().isoformat(),
    }

    ai_config = utils.load_config().get("ai_models", {})
    ai_config[model_name] = ai_record
    all_config = utils.load_config()
    all_config["ai_models"] = ai_config
    utils.save_config(all_config)

    return ai_record


def ai_list():
    return utils.load_config().get("ai_models", {})


def ai_logs(model_name, lines=50):
    ai_config = utils.load_config().get("ai_models", {})
    if model_name not in ai_config:
        return {"error": f"AI model '{model_name}' not found"}
    ai_record = ai_config[model_name]

    if utils.is_linux():
        service_name = ai_record.get("service_name", f"atulya-ai-{model_name}")
        result = utils.run_command(
            ["journalctl", "-u", service_name, "-n", str(lines), "--no-pager"],
            check=False,
        )
        if result and result.returncode == 0:
            return {"model": model_name, "lines": result.stdout.splitlines()}

    log_file = Path(ai_record.get("api_script", "")).parent / "logs"
    if log_file.exists():
        with open(log_file, "r") as file_handle:
            content = file_handle.readlines()
            return {"model": model_name, "lines": content[-lines:]}

    return {"error": f"No logs found for model '{model_name}'"}


def config_show():
    return utils.load_config()


def config_set(key_path, value):
    utils.set_config_value(key_path, value)
    return {key_path: value}


def config_export(output_path=None):
    if output_path is None:
        backup_dir = utils.CONFIG_DIR / "backups"
        backup_dir.mkdir(exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = str(backup_dir / f"config_export_{timestamp}.yaml")
    config_data = utils.load_config()
    with open(output_path, "w") as file_handle:
        yaml.dump(config_data, file_handle, default_flow_style=False)
    return {"path": output_path}


def config_import(input_path):
    if not Path(input_path).exists():
        return {"error": f"File not found: {input_path}"}
    with open(input_path, "r") as file_handle:
        config_data = yaml.safe_load(file_handle)
    if config_data:
        utils.save_config(config_data)
        return {"status": "imported", "path": input_path}
    return {"error": "Invalid configuration file"}
