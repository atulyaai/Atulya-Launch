"""Natural-language command API: parse NL -> plan -> approve -> execute."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch.ai import nlcommand
from atulya_launch.web.auth import get_current_user
from atulya_launch.web.database import audit_log

router = APIRouter(prefix="/api/ai", tags=["ai"])


class CommandRequest(BaseModel):
    command: str
    dry_run: bool = True
    use_llm: bool = False


@router.post("/command")
def run_command(body: CommandRequest, user: dict = Depends(get_current_user)):
    """Interpret a natural-language command and (optionally) execute it.

    `dry_run=true` (default) returns the proposed plan for review.
    `dry_run=false` executes the approved plan step-by-step and records an audit
    trail. Weak confidence (>0.5 domain required) yields a 422 asking the
    operator to confirm; misparsed intent asks again.
    """
    command = body.command.strip()
    if not command:
        raise HTTPException(status_code=422, detail="empty command")

    intent = nlcommand.parse_intent(command)
    if intent.confidence < 0.5:
        raise HTTPException(
            status_code=422,
            detail=f"could not confidently parse command (confidence={intent.confidence})",
        )

    if body.use_llm:
        llm = nlcommand.enrich_with_llm(command)
        if llm:
            intent = nlcommand.intent_from_dict(llm, raw=command)

    plan = nlcommand.assemble_plan(intent)
    if not plan.steps:
        raise HTTPException(status_code=422, detail="no actionable steps derived from command")

    result = nlcommand.apply_plan(plan, dry_run=body.dry_run)

    audit_log(
        user.get("sub", "admin"),
        "ai.command",
        "ok",
        {
            "command": command,
            "intent": intent.describe(),
            "dry_run": body.dry_run,
            "ok": result.get("ok"),
            "steps": len(plan.steps),
        },
    )
    result["command"] = command
    return result