import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from . import __version__, core, utils

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="atulya-launch")
@click.pass_context
def cli(context):
    context.ensure_object(dict)


@cli.command()
@click.pass_context
def init(context):
    platform_name = utils.get_platform()
    config_dir = utils.ensure_config_dir()
    config_path = utils.CONFIG_FILE

    default_config = {
        "panel": {
            "name": "Atulya Launch",
            "version": __version__,
            "platform": platform_name,
            "data_dir": str(config_dir),
        },
        "server": {
            "web_server": core.detect_web_server() or "nginx",
            "php_enabled": False,
        },
        "backup": {
            "keep_days": 30,
        },
        "monitoring": {
            "enabled": True,
            "interval_seconds": 60,
        },
    }

    if not config_path.exists():
        utils.save_config(default_config)
        console.print(f"[green]Initialized Atulya Launch v{__version__} on {platform_name}[/green]")
        console.print(f"[blue]Config directory: {config_dir}[/blue]")
    else:
        console.print("[yellow]Configuration already exists. Run 'config show' to view.[/yellow]")

    if utils.is_linux():
        console.print("[green]Linux platform detected - all features available[/green]")
    elif utils.is_macos():
        console.print("[yellow]macOS platform - some features limited (site/ssl/db/user)[/yellow]")
    elif utils.is_windows():
        console.print("[yellow]Windows platform - management client mode[/yellow]")
        console.print("[yellow]Server features (site/ssl/db/user) require SSH to a Linux host[/yellow]")


@cli.group()
def site():
    pass


@site.command()
@click.argument("domain")
@click.option("--web-root", "-w", default=None, help="Document root path")
@click.option("--server", "-s", type=click.Choice(["nginx", "apache"]), default=None, help="Web server type")
@click.option("--php", is_flag=True, help="Enable PHP support")
@click.option("--proxy-pass", default=None, help="Proxy pass URL (e.g. http://localhost:3000)")
def create(domain, web_root, server, php, proxy_pass):
    if not utils.is_linux():
        console.print("[red]Site management is only supported on Linux[/red]")
        sys.exit(1)
    extra_config = {}
    if proxy_pass:
        extra_config["proxy_pass"] = proxy_pass
    result = core.site_create(domain, web_root, server, php, extra_config)
    console.print(f"[green]Site created: {domain}[/green]")
    console.print(f"  Web root: {result.get('web_root')}")
    console.print(f"  Server: {result.get('server_type')}")


@site.command()
def list():
    sites = core.site_list()
    if not sites:
        console.print("[yellow]No sites configured[/yellow]")
        return
    table = Table(title="Sites")
    table.add_column("Domain", style="cyan")
    table.add_column("Web Root", style="white")
    table.add_column("Server", style="blue")
    table.add_column("Status", style="green")
    for domain_name, site_data in sites.items():
        status = "[green]Enabled[/green]" if site_data.get("enabled") else "[red]Disabled[/red]"
        table.add_row(
            domain_name,
            site_data.get("web_root", "-"),
            site_data.get("server_type", "-"),
            status,
        )
    console.print(table)


@site.command()
@click.argument("domain")
def delete(domain):
    if core.site_delete(domain):
        console.print(f"[green]Site deleted: {domain}[/green]")
    else:
        console.print(f"[red]Site not found: {domain}[/red]")
        sys.exit(1)


@site.command()
@click.argument("domain")
def enable(domain):
    if core.site_toggle(domain, enable=True):
        console.print(f"[green]Site enabled: {domain}[/green]")
    else:
        console.print(f"[red]Site not found: {domain}[/red]")
        sys.exit(1)


@site.command()
@click.argument("domain")
def disable(domain):
    if core.site_toggle(domain, enable=False):
        console.print(f"[green]Site disabled: {domain}[/green]")
    else:
        console.print(f"[red]Site not found: {domain}[/red]")
        sys.exit(1)


@cli.group()
def ssl():
    pass


@ssl.command()
@click.argument("domain")
@click.option("--email", "-e", required=True, help="Email for Let's Encrypt")
@click.option("--web-root", "-w", default=None, help="Web root for verification")
@click.option("--staging", is_flag=True, help="Use staging environment")
def issue(domain, email, web_root, staging):
    result = core.ssl_issue(domain, email, web_root, staging)
    if "error" in result:
        console.print(f"[red]{result['error']}[/red]")
        sys.exit(1)
    console.print(f"[green]SSL certificate issued for {domain}[/green]")
    if result.get("cert_path"):
        console.print(f"  cert: {result['cert_path']}")
        console.print(f"  key:  {result['key_path']}")


@ssl.command()
def list():
    certs = core.ssl_list()
    if not certs:
        console.print("[yellow]No SSL certificates configured[/yellow]")
        return
    table = Table(title="SSL Certificates")
    table.add_column("Domain", style="cyan")
    table.add_column("Issued", style="white")
    table.add_column("Expires", style="yellow")
    table.add_column("Staging", style="blue")
    for domain_name, cert_data in certs.items():
        table.add_row(
            domain_name,
            cert_data.get("issued_at", "-"),
            cert_data.get("expires_at", "-"),
            "[green]Yes[/green]" if cert_data.get("staging") else "[red]No[/red]",
        )
    console.print(table)


@ssl.command()
def renew():
    result = core.ssl_renew()
    if "error" in result:
        console.print(f"[red]{result['error']}[/red]")
        sys.exit(1)
    if result.get("status") == "renewed":
        domains = result.get("domains", [])
        console.print(f"[green]Renewed SSL for {len(domains)} domain(s)[/green]")
        for domain_name in domains:
            console.print(f"  - {domain_name}")
    else:
        console.print("[yellow]No certificates needed renewal[/yellow]")


@cli.group()
def db():
    pass


@db.command()
@click.argument("db_name")
@click.option("--user", "-u", default=None, help="Database user")
@click.option("--password", "-p", default=None, help="Database password (auto-generated if omitted)")
@click.option("--type", "-t", "db_type", type=click.Choice(["mysql", "postgresql"]), default="mysql", help="Database type")
def create(db_name, user, password, db_type):
    result = core.db_create(db_name, user, password, db_type)
    if "error" in result:
        console.print(f"[red]{result['error']}[/red]")
        sys.exit(1)
    console.print(f"[green]Database created: {db_name}[/green]")
    console.print(f"  User:     {result.get('user')}")
    console.print(f"  Password: {result.get('password')}")
    console.print(f"  Type:     {result.get('type')}")


@db.command()
def list():
    databases = core.db_list()
    if not databases:
        console.print("[yellow]No databases configured[/yellow]")
        return
    table = Table(title="Databases")
    table.add_column("Name", style="cyan")
    table.add_column("User", style="white")
    table.add_column("Type", style="blue")
    table.add_column("Created", style="green")
    for db_name, db_data in databases.items():
        table.add_row(
            db_name,
            db_data.get("user", "-"),
            db_data.get("type", "mysql"),
            db_data.get("created_at", "-"),
        )
    console.print(table)


@db.command()
@click.argument("db_name")
@click.option("--output", "-o", default=None, help="Output file path")
def backup(db_name, output):
    result = core.db_backup(db_name, output)
    if "error" in result:
        console.print(f"[red]{result['error']}[/red]")
        sys.exit(1)
    console.print(f"[green]Database backed up: {db_name}[/green]")
    console.print(f"  Path: {result.get('path')}")
    size_kb = result.get("size", 0) / 1024
    console.print(f"  Size: {size_kb:.1f} KB")


@db.command()
@click.argument("db_name")
@click.argument("backup_path")
@click.option("--type", "-t", "db_type", type=click.Choice(["mysql", "postgresql"]), default="mysql", help="Database type")
def restore(db_name, backup_path, db_type):
    result = core.db_restore(db_name, backup_path, db_type)
    if "error" in result:
        console.print(f"[red]{result['error']}[/red]")
        sys.exit(1)
    console.print(f"[green]Database restored: {db_name}[/green]")


@cli.group()
def user():
    pass


@user.command()
@click.argument("username")
@click.option("--password", "-p", default=None, help="User password (auto-generated if omitted)")
@click.option("--shell", "-s", default="/bin/bash", help="Login shell")
@click.option("--no-home", is_flag=True, help="Do not create home directory")
@click.option("--groups", "-g", default=None, help="Comma-separated supplementary groups")
def add(username, password, shell, no_home, groups):
    group_list = groups.split(",") if groups else None
    result = core.user_add(username, password, shell, not no_home, group_list)
    if "error" in result:
        console.print(f"[red]{result['error']}[/red]")
        sys.exit(1)
    console.print(f"[green]User created: {username}[/green]")
    console.print(f"  Password: {result.get('password')}")
    console.print(f"  Shell:    {result.get('shell')}")
    console.print(f"  Home:     {result.get('home')}")


@user.command()
def list():
    users = core.user_list()
    if not users:
        console.print("[yellow]No users configured[/yellow]")
        return
    table = Table(title="Users")
    table.add_column("Username", style="cyan")
    table.add_column("Shell", style="white")
    table.add_column("Home", style="blue")
    table.add_column("Groups", style="green")
    table.add_column("Created", style="yellow")
    for username, user_data in users.items():
        groups_str = ", ".join(user_data.get("groups", [])) or "-"
        table.add_row(
            username,
            user_data.get("shell", "-"),
            user_data.get("home", "-"),
            groups_str,
            user_data.get("created_at", "-"),
        )
    console.print(table)


@user.command()
@click.argument("username")
@click.option("--keep-home", is_flag=True, help="Keep home directory")
def delete(username, keep_home):
    result = core.user_delete(username, not keep_home)
    if "error" in result:
        console.print(f"[red]{result['error']}[/red]")
        sys.exit(1)
    console.print(f"[green]User deleted: {username}[/green]")


@cli.group()
def backup():
    pass


@backup.command()
@click.option("--name", "-n", default=None, help="Backup name")
@click.option("--no-db", is_flag=True, help="Exclude databases")
@click.option("--no-sites", is_flag=True, help="Exclude sites")
@click.option("--no-config", is_flag=True, help="Exclude config")
@click.option("--destination", "-d", default=None, help="Destination directory for archive")
def create(name, no_db, no_sites, no_config, destination):
    result = core.backup_create(
        name=name,
        include_databases=not no_db,
        include_sites=not no_sites,
        include_config=not no_config,
        destination=destination,
    )
    console.print(f"[green]Backup created: {result.get('name')}[/green]")
    console.print(f"  Path: {result.get('path')}")
    if result.get("archive"):
        console.print(f"  Archive: {result.get('archive')}")
    manifest = result.get("manifest", {})
    console.print(f"  Includes:")
    console.print(f"    Config:     {'Yes' if manifest.get('includes', {}).get('config') else 'No'}")
    console.print(f"    Sites:      {len(manifest.get('includes', {}).get('sites', []))}")
    console.print(f"    Databases:  {len(manifest.get('includes', {}).get('databases', []))}")


@backup.command()
def list():
    backups = core.backup_list()
    if not backups:
        console.print("[yellow]No backups found[/yellow]")
        return
    table = Table(title="Backups")
    table.add_column("Name", style="cyan")
    table.add_column("Created", style="white")
    table.add_column("Contents", style="blue")
    for name, backup_data in backups.items():
        manifest = backup_data.get("includes", {})
        contents = []
        if manifest.get("config"):
            contents.append("config")
        if manifest.get("sites"):
            contents.append(f"sites({len(manifest['sites'])})")
        if manifest.get("databases"):
            contents.append(f"db({len(manifest['databases'])})")
        contents_str = ", ".join(contents) if contents else "unknown"
        table.add_row(
            name,
            backup_data.get("created_at", "-"),
            contents_str,
        )
    console.print(table)


@backup.command()
@click.argument("name")
@click.option("--no-db", is_flag=True, help="Skip database restore")
@click.option("--no-sites", is_flag=True, help="Skip site restore")
@click.option("--no-config", is_flag=True, help="Skip config restore")
def restore(name, no_db, no_sites, no_config):
    result = core.backup_restore(name, not no_db, not no_sites, not no_config)
    if "error" in result:
        console.print(f"[red]{result['error']}[/red]")
        sys.exit(1)
    console.print(f"[green]Backup restored: {name}[/green]")


@backup.command()
@click.option("--interval", "-i", type=click.Choice(["hourly", "daily", "weekly", "monthly"]), default="daily", help="Backup interval")
@click.option("--time", "-t", "time_str", default="0 2", help="Cron time expression (min hour or hour for daily/weekly)")
@click.option("--keep", "-k", default=30, help="Days to keep backups")
@click.option("--disable", is_flag=True, help="Disable scheduled backup")
def schedule(interval, time_str, keep, disable):
    result = core.backup_schedule(interval, time_str, enabled=not disable, keep_days=keep)
    if "error" in result:
        console.print(f"[red]{result['error']}[/red]")
        sys.exit(1)
    if disable:
        console.print("[yellow]Scheduled backup disabled[/yellow]")
    else:
        console.print(f"[green]Backup scheduled: {interval}[/green]")
        console.print(f"  Interval: {result.get('interval')}")
        console.print(f"  Keep days: {result.get('keep_days')}")


@cli.group()
def monitor():
    pass


@monitor.command()
def status():
    result = core.monitor_status()
    cpu = result["cpu"]
    memory = result["memory"]
    disk = result["disk"]
    uptime = result["uptime"]

    def render_bar(percent, width=30):
        filled = int(width * percent / 100)
        bar = "█" * filled + "░" * (width - filled)
        return bar

    console.print(Panel(f"[bold cyan]System Status[/bold cyan]"))
    console.print(f"[bold]CPU:[/bold] {cpu['percent']}% ({cpu['count']} cores)")
    console.print(f"  {render_bar(cpu['percent'])}")
    console.print(f"[bold]Memory:[/bold] {memory['percent']}%")
    mem_used_gb = memory['used'] / (1024**3)
    mem_total_gb = memory['total'] / (1024**3)
    console.print(f"  {render_bar(memory['percent'])}  {mem_used_gb:.1f}GB / {mem_total_gb:.1f}GB")
    console.print(f"[bold]Disk:[/bold] {disk['percent']}%")
    disk_used_gb = disk['used'] / (1024**3)
    disk_total_gb = disk['total'] / (1024**3)
    console.print(f"  {render_bar(disk['percent'])}  {disk_used_gb:.1f}GB / {disk_total_gb:.1f}GB")
    console.print(f"[bold]Uptime:[/bold] {uptime['uptime_hours']:.1f} hours")


@monitor.command()
@click.option("--sort", "-s", "sort_by", type=click.Choice(["cpu", "memory"]), default="cpu", help="Sort by")
@click.option("--limit", "-l", default=20, help="Number of processes to show")
def processes(sort_by, limit):
    proc_list = core.monitor_processes(sort_by, limit)
    if not proc_list:
        console.print("[yellow]No process information available[/yellow]")
        return
    table = Table(title=f"Top {limit} Processes (by {sort_by})")
    table.add_column("PID", style="cyan")
    table.add_column("Name", style="white")
    table.add_column("CPU%", style="green")
    table.add_column("MEM%", style="blue")
    table.add_column("Status", style="yellow")
    table.add_column("User", style="magenta")
    for proc in proc_list:
        table.add_row(
            str(proc.get("pid", "-")),
            proc.get("name", "-")[:40],
            f"{proc.get('cpu_percent', 0):.1f}",
            f"{proc.get('memory_percent', 0):.1f}",
            proc.get("status", "-"),
            proc.get("username", "-")[:15],
        )
    console.print(table)


@monitor.command()
@click.argument("log_type", type=click.Choice(["system", "auth", "nginx", "apache", "mysql"]), default="system")
@click.option("--lines", "-n", default=50, help="Number of lines")
def logs(log_type, lines):
    result = core.monitor_logs(log_type, lines)
    if "error" in result:
        console.print(f"[red]{result['error']}[/red]")
        sys.exit(1)
    console.print(f"[bold]Recent {log_type} logs:[/bold]")
    for line in result.get("lines", []):
        console.print(line)


@monitor.command()
def alerts():
    alert_list = core.monitor_alerts()
    if not alert_list:
        console.print("[green]No active alerts[/green]")
        return
    table = Table(title="Active Alerts")
    table.add_column("Level", style="cyan")
    table.add_column("Source", style="white")
    table.add_column("Message", style="yellow")
    table.add_column("Timestamp", style="blue")
    for alert in alert_list:
        level_style = "[red]CRITICAL[/red]" if alert.get("level") == "critical" else "[yellow]WARNING[/yellow]"
        table.add_row(
            level_style,
            alert.get("source", "-"),
            alert.get("message", "-"),
            alert.get("timestamp", "-"),
        )
    console.print(table)


@cli.group()
def ai():
    pass


@ai.command()
@click.argument("model_name")
@click.argument("model_path")
@click.option("--port", "-p", default=8000, help="API port")
@click.option("--workers", "-w", default=1, help="Number of workers")
def deploy(model_name, model_path, port, workers):
    if not Path(model_path).exists():
        console.print(f"[red]Model path not found: {model_path}[/red]")
        sys.exit(1)
    result = core.ai_deploy(model_name, model_path, port, workers)
    if "error" in result:
        console.print(f"[red]{result['error']}[/red]")
        sys.exit(1)
    console.print(f"[green]AI model deployed: {model_name}[/green]")
    console.print(f"  Port:   {result.get('port')}")
    console.print(f"  Status: {result.get('status')}")


@ai.command()
def list():
    models = core.ai_list()
    if not models:
        console.print("[yellow]No AI models deployed[/yellow]")
        return
    table = Table(title="Deployed AI Models")
    table.add_column("Name", style="cyan")
    table.add_column("Model Path", style="white")
    table.add_column("Port", style="blue")
    table.add_column("Status", style="green")
    table.add_column("Deployed", style="yellow")
    for name, model_data in models.items():
        table.add_row(
            name,
            model_data.get("model_path", "-"),
            str(model_data.get("port", "-")),
            model_data.get("status", "-"),
            model_data.get("deployed_at", "-"),
        )
    console.print(table)


@ai.command()
@click.argument("model_name")
@click.option("--lines", "-n", default=50, help="Number of lines")
def logs(model_name, lines):
    result = core.ai_logs(model_name, lines)
    if "error" in result:
        console.print(f"[red]{result['error']}[/red]")
        sys.exit(1)
    console.print(f"[bold]Logs for AI model '{model_name}':[/bold]")
    for line in result.get("lines", []):
        console.print(line)


@cli.group()
def config():
    pass


@config.command()
def show():
    config_data = core.config_show()
    if not config_data:
        console.print("[yellow]No configuration found. Run 'init' first.[/yellow]")
        return
    import yaml as yaml_lib
    console.print(yaml_lib.dump(config_data, default_flow_style=False))


@config.command()
@click.argument("key_path")
@click.argument("value")
def set(key_path, value):
    parsed_value = value
    if value.lower() in ("true", "false"):
        parsed_value = value.lower() == "true"
    elif value.isdigit():
        parsed_value = int(value)
    result = core.config_set(key_path, parsed_value)
    console.print(f"[green]Set {key_path} = {parsed_value}[/green]")


@config.command()
@click.argument("output_path", default=None, required=False)
def export(output_path):
    result = core.config_export(output_path)
    if "error" in result:
        console.print(f"[red]{result['error']}[/red]")
        sys.exit(1)
    console.print(f"[green]Configuration exported to {result.get('path')}[/green]")


@config.command()
@click.argument("input_path")
def import_config(input_path):
    result = core.config_import(input_path)
    if "error" in result:
        console.print(f"[red]{result['error']}[/red]")
        sys.exit(1)
    console.print(f"[green]Configuration imported from {input_path}[/green]")


def main():
    cli(obj={})


if __name__ == "__main__":
    main()
