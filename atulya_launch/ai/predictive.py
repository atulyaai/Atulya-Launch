"""AI predictive-health engine for Atulya Launch.

Collects periodic system metric samples (CPU, memory, disk, load, network),
keeps a rolling history in SQLite, computes trend forecasts, and produces risk
scores with suggested automated actions. When Tantra-LLM is installed it augments
the heuristic forecast with a model-based analysis; without it the engine still
works fully using lightweight linear-trend math (no external deps beyond the
existing panel stack).
"""

import datetime
import json
from typing import Any

from atulya_launch.web.database import connect

METRIC_KEYS = ["cpu_percent", "mem_percent", "disk_percent", "load_1m", "bytes_sent", "bytes_recv"]

# Risk thresholds -> recommended proactive actions.
_ACTION_MAP = {
    "cpu_percent": {"warn": 80, "crit": 90, "action": "restart_heavy_process", "auto": False},
    "mem_percent": {"warn": 85, "crit": 95, "action": "restart_php_fpm_or_mysql", "auto": False},
    "disk_percent": {"warn": 85, "crit": 95, "action": "rotate_backups_and_clean_logs", "auto": True},
    "load_1m": {"warn": 4.0, "crit": 8.0, "action": "review_worker_processes", "auto": False},
}


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat() + "Z"


def _timestamp() -> int:
    return int(datetime.datetime.now(datetime.timezone.utc).timestamp())


def sample_metrics() -> dict[str, Any]:
    """Collect a current metric snapshot reusing the health dashboard helpers."""
    from atulya_launch.web.api.healthdashboard import (
        _get_cpu_info,
        _get_memory_info,
        _get_disk_info,
        _get_network_info,
        _get_load_average,
    )
    cpu = _get_cpu_info()
    mem = _get_memory_info()
    disk = _get_disk_info()
    net = _get_network_info()
    load = _get_load_average()
    return {
        "cpu_percent": cpu.get("percent", 0),
        "mem_percent": mem.get("percent", 0),
        "disk_percent": disk.get("percent", 0),
        "load_1m": load.get("load_1m", 0),
        "bytes_sent": net.get("bytes_sent", 0),
        "bytes_recv": net.get("bytes_recv", 0),
        "ts": _timestamp(),
    }


def record_sample(sample: dict[str, Any]) -> None:
    """Persist a metric sample into the ai_metric_history table."""
    row_json = json.dumps({k: sample.get(k, 0) for k in METRIC_KEYS})
    try:
        with connect() as conn:
            conn.execute(
                "INSERT INTO ai_metric_history (collected_at, metrics_json) VALUES (?, ?)",
                (_now(), row_json),
            )
    except Exception:
        pass


def get_history(hours: int = 24) -> list[dict[str, Any]]:
    """Return recent metric samples ordered oldest-first."""
    cutoff = _now_from_hours(hours)
    try:
        with connect() as conn:
            rows = conn.execute(
                "SELECT collected_at, metrics_json FROM ai_metric_history WHERE collected_at >= ? ORDER BY collected_at ASC",
                (cutoff,),
            ).fetchall()
        result = []
        for r in rows:
            entry = json.loads(r["metrics_json"])
            entry["collected_at"] = r["collected_at"]
            result.append(entry)
        return result
    except Exception:
        return []


def _now_from_hours(hours: int) -> str:
    ts = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
    return ts.replace(tzinfo=None).isoformat() + "Z"


def _forecast(values: list[float]) -> dict[str, Any]:
    """Linear least-squares trend + naive next-value forecast."""
    if len(values) < 2:
        return {"current": values[-1] if values else 0, "slope": 0, "forecast_next": values[-1] if values else 0}
    n = len(values)
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(values) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values))
    den = sum((x - mean_x) ** 2 for x in xs)
    slope = num / den if den else 0
    current = values[-1]
    forecast_next = slope + current if abs(slope) < 10 else current
    return {"current": round(current, 2), "slope": round(slope, 3), "forecast_next": round(forecast_next, 2)}


def _score_risk(key: str, value: float) -> dict[str, Any]:
    config = _ACTION_MAP.get(key)
    if not config:
        return {"key": key, "risk": "low", "score": 0, "action": None, "auto": False}
    warn, crit, action, auto = config["warn"], config["crit"], config["action"], config["auto"]
    if value >= crit:
        return {"key": key, "risk": "critical", "score": 2, "action": action, "auto": auto}
    if value >= warn:
        return {"key": key, "risk": "warning", "score": 1, "action": action, "auto": auto}
    return {"key": key, "risk": "low", "score": 0, "action": None, "auto": False}


def evaluate(current: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any]:
    """Evaluate current metrics + history into a predictive health report."""
    risks = []
    forecast = {}
    for key in METRIC_KEYS:
        series = [float(h.get(key, 0)) for h in history if key in h]
        series = series[-120:]  # cap at ~120 samples
        fc = _forecast(series + [current.get(key, 0)])
        forecast[key] = fc
        risk = _score_risk(key, current.get(key, 0))
        # escalare risk one level if the trend is strongly upward
        if fc["slope"] > 0.5 and risk["risk"] == "low":
            risk["risk"] = "watch"
        risks.append({**risk, "current": current.get(key, 0), "forecast_next": fc["forecast_next"]})

    overall = max((r["score"] for r in risks), default=0)
    overall_label = {0: "healthy", 1: "attention", 2: "critical"}.get(overall, "healthy")

    automations = [r for r in risks if r.get("auto") and r["risk"] == "critical"]
    suggestions = [r for r in risks if r.get("action")]

    return {
        "timestamp": _now(),
        "overall_risk": overall_label,
        "risk_score": overall,
        "metrics": {
            k: {
                "current": current.get(k, 0),
                "forecast_next": forecast[k]["forecast_next"],
                "trend": forecast[k]["slope"],
            }
            for k in METRIC_KEYS
        },
        "risks": risks,
        "suggested_actions": suggestions,
        "automated_actions": automations,
        "history_points": len(history),
    }


def analyze_with_llm(report: dict[str, Any]) -> dict[str, Any]:
    """Optionally enrich the heuristic report using Tantra-LLM when available."""
    try:
        from Tantra import llm_chat  # type: ignore
    except Exception:
        return report
    try:
        summary = json.dumps({k: report.get(k) for k in ("overall_risk", "metrics", "suggested_actions")})
        response = llm_chat(
            f"You are a server ops AI. Given this health prediction JSON, give a 2-3 sentence "
            f"plain-language diagnostic and the single most important next action:\n{summary}"
        )
        report["llm_analysis"] = str(response)
    except Exception:
        pass
    return report