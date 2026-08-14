"""Log-based AI diagnostics API."""

from fastapi import APIRouter, Depends, Query

from atulya_launch.ai import log_analyzer
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/diagnose")
def diagnose_logs(
    hours: int = Query(4, ge=1, le=168),
    use_llm: bool = Query(True),
    user: dict = Depends(get_current_user),
):
    """Run log-based diagnostics on all available logs + metrics.

    Returns root-cause analysis + suggested fix.
    `use_llm=true` attempts Tantra-LLM then OpenAI-compatible; falls back to heuristic.
    """
    return log_analyzer.diagnose(hours=hours, use_llm=use_llm)


@router.get("/diagnose/{domain}")
def diagnose_domain_logs(
    domain: str,
    hours: int = Query(4, ge=1, le=168),
    use_llm: bool = Query(True),
    user: dict = Depends(get_current_user),
):
    """Run log-based diagnostics scoped to a specific domain.

    Only analyzes that site's error/access logs + global metrics.
    """
    return log_analyzer.diagnose_for_domain(domain=domain, hours=hours, use_llm=use_llm)