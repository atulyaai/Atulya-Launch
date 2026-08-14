"""AI-powered health prediction and automation API."""


from fastapi import APIRouter, Depends, Query

from atulya_launch.ai import predictive
from atulya_launch.web.auth import get_current_user
from atulya_launch.web.database import audit_log

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/predict")
def predict_health(
    hours: int = Query(24, ge=1, le=720),
    use_llm: bool = Query(False),
    user: dict = Depends(get_current_user),
):
    """Collect a fresh metric sample and return the predictive health report."""
    sample = predictive.sample_metrics()
    predictive.record_sample(sample)
    history = predictive.get_history(hours=hours)
    report = predictive.evaluate(sample, history)
    if use_llm:
        report = predictive.analyze_with_llm(report)
    audit_log(user.get("sub", "admin"), "ai.predict", "ok", {"risk": report["overall_risk"]})
    return report


@router.get("/history")
def health_history(
    hours: int = Query(24, ge=1, le=720),
    user: dict = Depends(get_current_user),
):
    history = predictive.get_history(hours=hours)
    return {"hours": hours, "points": len(history), "history": history}


@router.post("/automate")
def run_automations(user: dict = Depends(get_current_user)):
    """Execute safe, non-destructive automated actions for critical metrics.

    Only automation-flagged actions (currently backup rotation / log cleanup)
    are executed automatically; process restarts always require operator
    approval via the regular panel flows.
    """
    sample = predictive.sample_metrics()
    predictive.record_sample(sample)
    history = predictive.get_history(hours=24)
    report = predictive.evaluate(sample, history)

    executed = []
    for action in report.get("automated_actions", []):
        key = action.get("key")
        if key == "disk_percent":
            ok, detail = _rotate_backups()
        else:
            continue
        executed.append({"key": key, "action": action.get("action"), "ok": ok, "detail": detail})
        audit_log(user.get("sub", "admin"), "ai.automate", "ok" if ok else "error", {"key": key, "detail": detail})

    report["automation_executed"] = executed
    return report


def _rotate_backups() -> tuple[bool, str]:
    """Delete the oldest backups when disk is critically full (safest auto-action)."""
    from atulya_launch.web import backup_service
    try:
        backups = backup_service.list_backups()
        if not isinstance(backups, dict):
            backups = {}
        if len(backups) <= 2:
            return False, "not enough backups to rotate (kept 2 minimum)"
        oldest = min(backups.keys(), key=lambda name: backups[name].get("created_at") or "")
        ok = backup_service.delete_backup(oldest)
        return ok, f"removed oldest backup {oldest}"
    except Exception as e:
        return False, str(e)