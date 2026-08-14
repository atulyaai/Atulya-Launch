"""Log-based diagnostics engine for Atulya Launch.

Feeds recent server logs (nginx error/access, PHP error) + metric history
into an LLM (Tantra-LLM first, OpenAI-compatible fallback) to produce
root-cause analysis + suggested fix. Works fully offline with heuristic
fallback when no LLM is available.
"""

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from atulya_launch.ai import predictive


# Common error patterns to surface in heuristic mode
ERROR_PATTERNS = [
    (r"connect\(\) failed.*Connection refused", "upstream_down", "Upstream service (PHP-FPM/Node.js) not running"),
    (r"permission denied", "permission_denied", "Filesystem permission issue on webroot or socket"),
    (r"Too many open files", "fd_exhaustion", "File descriptor limit reached; increase ulimit"),
    (r"Out of memory|OOM", "oom_kill", "Process killed by OOM killer; check memory limits"),
    (r"disk.*full|No space left", "disk_full", "Filesystem full; rotate logs/backups"),
    (r"upstream timed out", "upstream_timeout", "PHP-FPM/Node.js slow; increase timeout or workers"),
    (r"502 Bad Gateway|503 Service Unavailable", "gateway_error", "Upstream not responding; check PHP-FPM/Node.js"),
    (r"SSL.*handshake|certificate verify failed", "ssl_error", "SSL certificate issue; check cert/key paths"),
    (r"client denied by server configuration", "access_denied", "Nginx deny rule blocking request"),
    (r"Primary script unknown", "php_script_missing", "PHP file not found; check webroot/index.php"),
    (r"Access denied for user", "mysql_auth_fail", "Database credential mismatch"),
    (r"Connection refused.*(3306|111)|Can't connect to MySQL", "mysql_down", "MySQL/MariaDB not running or wrong socket"),
    (r"redis.*Connection refused|redis.*ECONNREFUSED", "redis_down", "Redis not running or wrong port"),
    (r"certbot.*renew|Let's Encrypt.*fail", "cert_renew_fail", "Certificate renewal failed; check DNS/port 80"),
    (r"ufw.*BLOCK|iptables.*DROP", "firewall_block", "Firewall dropping traffic; check rules"),
    (r"fail2ban.*Ban", "fail2ban_ban", "IP banned by Fail2Ban; review jail config"),
]


def _now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"


def fetch_recent_logs(hours: int = 4, max_lines_per_source: int = 200) -> dict[str, Any]:
    """Fetch recent log lines from all available sources."""
    import os
    import glob
    from pathlib import Path

    sources = {}

    # System logs
    log_paths = {
        "nginx_error": "/var/log/nginx/error.log",
        "nginx_access": "/var/log/nginx/access.log",
        "apache_error": "/var/log/apache2/error.log",
        "apache_access": "/var/log/apache2/access.log",
        "php_error": "/var/log/php_errors.log",
        "php_fpm_error": "/var/log/php*-fpm/error.log",  # glob
    }

    # Site-specific logs
    site_logs = {}
    try:
        from atulya_launch import utils
        sites = utils.load_config().get("sites", {})
        for domain, config in sites.items():
            web_root = config.get("web_root", f"/var/www/{domain}")
            for log_type in ("error", "access"):
                p = Path(web_root) / "logs" / f"{log_type}.log"
                if p.exists():
                    site_logs[f"{domain}_{log_type}"] = str(p)
    except Exception:
        pass

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    cutoff_ts = cutoff.timestamp()

    for name, path in {**log_paths, **site_logs}.items():
        # Handle glob patterns
        paths = glob.glob(path) if "*" in path else [path]
        lines = []
        for p in paths:
            try:
                if not os.path.exists(p):
                    continue
                stat = os.stat(p)
                if stat.st_mtime < cutoff_ts:
                    continue
                with open(p, "r", errors="replace") as f:
                    all_lines = f.readlines()[-max_lines_per_source:]
                lines.extend([l.rstrip() for l in all_lines])
            except Exception:
                continue
        if lines:
            sources[name] = lines[-max_lines_per_source:]

    return {
        "window_hours": hours,
        "sources": sources,
        "total_lines": sum(len(v) for v in sources.values()),
    }


def fetch_metric_history(hours: int = 24) -> list[dict[str, Any]]:
    """Fetch recent metric samples."""
    return predictive.get_history(hours=hours)


def fetch_current_metrics() -> dict[str, Any]:
    """Get current metric snapshot."""
    return predictive.sample_metrics()


def heuristic_analysis(logs: dict[str, Any], metrics: dict[str, Any]) -> dict[str, Any]:
    """Pure-Python heuristic diagnosis without LLM."""
    findings = []

    # Scan logs for known patterns
    for source, lines in logs.get("sources", {}).items():
        for line in lines:
            for pattern, code, msg in ERROR_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    findings.append({
                        "source": source,
                        "pattern": code,
                        "message": msg,
                        "snippet": line[:200],
                    })
                    break  # first match per line

    # Correlate with metrics
    current = metrics
    metric_issues = []
    if current.get("disk_percent", 0) > 90:
        metric_issues.append({"metric": "disk_percent", "value": current["disk_percent"], "issue": "disk_critical"})
    if current.get("mem_percent", 0) > 90:
        metric_issues.append({"metric": "mem_percent", "value": current["mem_percent"], "issue": "memory_critical"})
    if current.get("cpu_percent", 0) > 90:
        metric_issues.append({"metric": "cpu_percent", "value": current["cpu_percent"], "issue": "cpu_critical"})
    if current.get("load_1m", 0) > 8:
        metric_issues.append({"metric": "load_1m", "value": current["load_1m"], "issue": "load_critical"})

    # Synthesize root cause
    root_causes = []
    fixes = []

    # Log-based causes
    for f in findings[:5]:
        if f["pattern"] == "upstream_down":
            root_causes.append("PHP-FPM or Node.js upstream not running")
            fixes.append("Restart PHP-FPM: `systemctl restart php8.3-fpm`")
        elif f["pattern"] == "permission_denied":
            root_causes.append("Filesystem permission issue")
            fixes.append("Fix webroot ownership: `chown -R www-data:www-data /var/www/domain`")
        elif f["pattern"] == "disk_full":
            root_causes.append("Filesystem full")
            fixes.append("Rotate logs/backups: `atulya-launch backup rotate`")
        elif f["pattern"] == "oom_kill":
            root_causes.append("Out of memory killer triggered")
            fixes.append("Increase memory limit or add swap")
        elif f["pattern"] == "ssl_error":
            root_causes.append("SSL certificate/key mismatch")
            fixes.append("Re-issue cert: `atulya-launch ssl issue domain`")
        elif f["pattern"] == "mysql_down":
            root_causes.append("MySQL/MariaDB not running")
            fixes.append("Start MySQL: `systemctl start mariadb`")
        elif f["pattern"] == "redis_down":
            root_causes.append("Redis not running")
            fixes.append("Start Redis: `systemctl start redis-server`")
        elif f["pattern"] == "cert_renew_fail":
            root_causes.append("Certificate renewal failed")
            fixes.append("Check DNS/port 80, re-run certbot manually")

    # Metric-based causes
    for m in metric_issues:
        if m["issue"] == "disk_critical":
            root_causes.append(f"Disk critical: {m['value']}%")
            fixes.append("Clean up: `atulya-launch backup rotate && journalctl --vacuum-time=7d`")
        elif m["issue"] == "memory_critical":
            root_causes.append(f"Memory critical: {m['value']}%")
            fixes.append("Restart PHP-FPM: `systemctl restart php8.3-fpm`")
        elif m["issue"] == "cpu_critical":
            root_causes.append(f"CPU critical: {m['value']}%")
            fixes.append("Review worker processes: `htop` / `systemctl reload nginx`")
        elif m["issue"] == "load_critical":
            root_causes.append(f"Load critical: {m['value']}")
            fixes.append("Identify heavy process: `ps aux --sort=-%cpu | head`")

    # Dedup
    root_causes = list(dict.fromkeys(root_causes))
    fixes = list(dict.fromkeys(fixes))

    confidence = 0.0
    if findings or metric_issues:
        confidence = min(0.9, 0.3 + 0.1 * len(findings) + 0.15 * len(metric_issues))

    return {
        "method": "heuristic",
        "confidence": round(confidence, 2),
        "findings": findings[:10],
        "metric_issues": metric_issues,
        "root_causes": root_causes[:5],
        "suggested_fixes": fixes[:5],
    }


def analyze_with_llm(logs: dict[str, Any], metrics: dict[str, Any], heuristic: dict[str, Any]) -> dict[str, Any]:
    """Enrich heuristic diagnosis with LLM (Tantra-LLM first, OpenAI-compatible fallback)."""
    # Try Tantra-LLM
    try:
        from Tantra import llm_chat
    except Exception:
        pass
    else:
        return _llm_analyze(logs, metrics, heuristic, llm_chat, "Tantra-LLM")

    # Try OpenAI-compatible
    try:
        import openai
        client = openai.OpenAI()  # uses OPENAI_API_KEY env
    except Exception:
        pass
    else:
        def openai_chat(prompt: str) -> str:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
            )
            return resp.choices[0].message.content
        return _llm_analyze(logs, metrics, heuristic, openai_chat, "OpenAI")

    return heuristic


def _llm_analyze(logs: dict[str, Any], metrics: dict[str, Any], heuristic: dict[str, Any], chat_fn, provider: str) -> dict[str, Any]:
    """Run LLM analysis and merge with heuristic."""
    # Prepare condensed context
    log_summary = []
    for src, lines in logs.get("sources", {}).items():
        # Only include lines that matched patterns or look error-like
        relevant = [l for l in lines if re.search(r"error|fail|fatal|critical|denied|timeout|refused|timeout", l, re.I)]
        if relevant:
            log_summary.append(f"[{src}]\n" + "\n".join(relevant[:5]))

    metric_summary = {
        k: {"current": v, "unit": "%" if "percent" in k else ""}
        for k, v in metrics.items()
        if k in ("cpu_percent", "mem_percent", "disk_percent", "load_1m")
    }

    prompt = (
        "You are a senior Linux server operator. Given recent log snippets and current metrics, "
        "provide a concise root-cause diagnosis and the SINGLE most important action to fix it.\n"
        "Respond in JSON with keys: root_cause, confidence (0-1), fix_action, reasoning.\n\n"
        f"LOGS (last 4h):\n{json.dumps(log_summary[:3], ensure_ascii=False)[:3000]}\n\n"
        f"METRICS:\n{json.dumps(metric_summary)}\n\n"
        f"HEURISTIC HINTS:\n{json.dumps(heuristic)}"
    )

    try:
        response = chat_fn(prompt)
        # Parse JSON from response
        start = response.find("{")
        end = response.rfind("}")
        if start >= 0 and end > start:
            llm_result = json.loads(response[start:end + 1])
        else:
            llm_result = {"root_cause": str(response)[:200], "confidence": 0.7, "fix_action": "see reasoning", "reasoning": "unparsed"}

        # Merge with heuristic
        return {
            "method": provider,
            "confidence": llm_result.get("confidence", 0.7),
            "root_cause": llm_result.get("root_cause", heuristic.get("root_causes", ["unknown"])[0]),
            "fix_action": llm_result.get("fix_action", heuristic.get("suggested_fixes", ["investigate manually"])[0]),
            "reasoning": llm_result.get("reasoning", ""),
            "heuristic_findings": heuristic.get("findings", [])[:5],
            "metric_issues": heuristic.get("metric_issues", []),
        }
    except Exception as e:
        return {**heuristic, "method": f"{provider}-failed", "error": str(e)}


def diagnose(hours: int = 4, use_llm: bool = True) -> dict[str, Any]:
    """Main entry: fetch logs + metrics -> analyze -> return diagnosis."""
    logs = fetch_recent_logs(hours=hours)
    metrics = fetch_current_metrics()
    history = fetch_metric_history(hours=24)

    # Add trend info from history
    trend = {}
    for key in ("cpu_percent", "mem_percent", "disk_percent", "load_1m"):
        series = [float(h.get(key, 0)) for h in history if key in h]
        if len(series) >= 2:
            slope = (series[-1] - series[-2]) if len(series) >= 2 else 0
            trend[key] = {"current": series[-1], "slope": round(slope, 2)}

    heuristic = heuristic_analysis(logs, metrics)
    if use_llm:
        result = analyze_with_llm(logs, metrics, heuristic)
    else:
        result = heuristic

    result["timestamp"] = _now()
    result["metrics_snapshot"] = {**metrics, "trend": trend}
    result["log_sources_checked"] = list(logs.get("sources", {}).keys())
    return result


def diagnose_for_domain(domain: str, hours: int = 4, use_llm: bool = True) -> dict[str, Any]:
    """Domain-scoped diagnosis: only that site's logs + global metrics."""
    from pathlib import Path
    from atulya_launch import utils

    sites = utils.load_config().get("sites", {})
    if domain not in sites:
        return {"error": "Site not found"}

    web_root = sites[domain].get("web_root", f"/var/www/{domain}")
    log_files = {}
    for log_type in ("error", "access"):
        p = Path(web_root) / "logs" / f"{log_type}.log"
        if p.exists():
            try:
                lines = p.read_text(errors="replace").splitlines()[-200:]
                log_files[f"{domain}_{log_type}"] = lines
            except Exception:
                pass

    logs = {"window_hours": hours, "sources": log_files, "total_lines": sum(len(v) for v in log_files.values())}
    metrics = fetch_current_metrics()
    heuristic = heuristic_analysis(logs, metrics)

    if use_llm:
        result = analyze_with_llm(logs, metrics, heuristic)
    else:
        result = heuristic

    result["timestamp"] = _now()
    result["domain"] = domain
    result["metrics_snapshot"] = metrics
    return result