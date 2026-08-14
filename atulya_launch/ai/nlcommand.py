"""Natural-language command layer for Atulya Launch.

Turns free-form operator commands like "create a WordPress site example.com
with Redis caching and SSL" into a structured, auditable, dry-run-able plan
that reuses the panel's existing core APIs and driver layer.

Design:
- `parse_intent(text)` — regex/entity-extraction based intent parsing, no
  external AI required.
- `assemble_plan(intent)` — maps the parsed intent to a list of concrete
  operations with fill-in args.
- `enrich_with_llm(text)` — optional Tantra-LLM full-text parsing fallback
  when heuristic parsing cannot agree on an intent.

Every step is deterministic and testable; nothing executes until the operator
approves via the `/api/ai/command` endpoint.
"""

import re
from dataclasses import dataclass, field
from typing import Any

# ─── Entities ─────────────────────────────────────────────────────────────

DOMAIN_RE = re.compile(r"([a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", re.IGNORECASE)
WORD = re.compile(r"[a-z0-9_\-]+", re.IGNORECASE)


@dataclass
class Intent:
    """Parsed intent from an NL command."""

    action: str                       # CREATE_SITE, ENABLE_SSL, ENABLE_CACHE, ...
    domain: str | None = None
    app: str | None = None            # wordpress, nextcloud, laravel, ghost, ...
    php_version: str | None = None
    wants_php: bool = False
    wants_db: bool = False
    wants_cache: str | None = None    # redis | memcached
    wants_ssl: bool = False
    staging: bool = False
    raw: str = ""
    confidence: float = 1.0
    tokens: list[str] = field(default_factory=list)

    def describe(self) -> str:
        bits = [self.action]
        if self.domain:
            bits.append(f"domain={self.domain}")
        if self.app:
            bits.append(f"app={self.app}")
        if self.wants_ssl:
            bits.append("ssl")
        if self.wants_cache:
            bits.append(f"cache={self.wants_cache}")
        if self.wants_db:
            bits.append("db")
        if self.wants_php:
            bits.append(f"php={self.php_version or 'default'}")
        return " ".join(bits)


# ─── App aliases ──────────────────────────────────────────────────────────

APP_ALIASES = {
    "wordpress": "wordpress",
    "wp": "wordpress",
    "nextcloud": "nextcloud",
    "laravel": "laravel",
    "ghost": "ghost",
    "flask": "flask",
    "django": "django",
}

CACHE_ALIASES = {"redis": "redis", "memcached": "memcached", "cache": "redis"}


def _extract_domain(text: str) -> str | None:
    m = DOMAIN_RE.search(text)
    return m.group(0).lower() if m else None


def _extract_app(text: str) -> str | None:
    lowered = text.lower()
    for alias, canonical in APP_ALIASES.items():
        if re.search(rf"\b{alias}\b", lowered):
            return canonical
    return None


def _extract_cache(text: str) -> str | None:
    lowered = text.lower()
    for alias, canonical in CACHE_ALIASES.items():
        if re.search(rf"\b{alias}\b", lowered):
            return canonical
    return None


def _extract_php_version(text: str) -> str | None:
    lowered = text.lower()
    m = re.search(r"php\s*([0-9]+\.[0-9]+)", lowered)
    return m.group(1) if m else None


def _text_lower(text: str) -> str:
    return text.lower()


def parse_intent(text: str) -> Intent:
    """Parse an NL command into an Intent. Pure and deterministic."""
    lowered = _text_lower(text)
    domain = _extract_domain(text)
    app = _extract_app(text)
    cache = _extract_cache(text)
    php_version = _extract_php_version(text)

    wants_php = bool(re.search(r"\bphp\b", lowered)) or php_version is not None
    wants_db = bool(re.search(r"\bdatabase\b|\bdb\b|mysql|mariadb|postgres", lowered)) or app in ("wordpress", "nextcloud", "laravel")
    wants_ssl = bool(re.search(r"\bssl\b|\bcertificate\b|\bcert\b|https|letsencrypt|lets encrypt", lowered)) and not bool(
        re.search(r"\bwithout\s+(ssl|cert|certificate)|no\s+(ssl|cert|certificate)\b", lowered)
    )
    staging = bool(re.search(r"\bstaging\b", lowered))

    verbs = ["create", "set up", "setup", "deploy", "install", "make", "launch", "add", "start"]
    removed = ["delete", "remove", "drop", "teardown", "stop", "kill"]
    create = any(re.search(rf"\b{v}\b", lowered) for v in verbs)
    delete = any(re.search(rf"\b{v}\b", lowered) for v in removed)

    if delete and not create:
        action = "DELETE_SITE"
    else:
        action = "CREATE_SITE"

    # Standalone SSL request without a site verb.
    if wants_ssl and not create and not delete:
        action = "ENABLE_SSL"
    elif cache and not create and not delete and not wants_ssl:
        action = "ENABLE_CACHE"

    intent = Intent(
        action=action,
        domain=domain,
        app=app,
        php_version=php_version,
        wants_php=wants_php or php_version is not None,
        wants_db=wants_db,
        wants_cache=cache,
        wants_ssl=wants_ssl,
        staging=staging,
        raw=text,
        confidence=1.0 if domain else 0.5,
        tokens=WORD.findall(lowered),
    )
    return intent


def intent_from_dict(d: dict[str, Any], raw: str) -> Intent:
    """Reconstitute an Intent from an enriched (optionally LLM) dict."""
    return Intent(
        action=str(d.get("action", "CREATE_SITE")).upper(),
        domain=d.get("domain") or _extract_domain(raw),
        app=d.get("app"),
        php_version=str(d.get("php_version")) if d.get("php_version") else None,
        wants_php=bool(d.get("wants_php", False)),
        wants_db=bool(d.get("wants_db", False)),
        wants_cache=d.get("wants_cache"),
        wants_ssl=bool(d.get("wants_ssl", False)),
        staging=bool(d.get("staging", False)),
        raw=raw,
        confidence=1.0 if d.get("domain") else 0.5,
        tokens=WORD.findall(raw.lower()),
    )


# ─── Plan assembly ────────────────────────────────────────────────────────

PLAN_STEP = {
    "CREATE_SITE": ["provision_site", "configure_php_fpm", "create_database", "install_app"],
    "DELETE_SITE": ["remove_site"],
    "ENABLE_SSL": ["issue_ssl", "reload_web"],
    "ENABLE_CACHE": ["enable_cache", "reload_web"],
}


def _cnf_payload(intent: Intent) -> dict[str, Any]:
    """Build the canonical args for each plan step from an Intent."""
    domain = intent.domain or "example.com"
    app = intent.app or "static"
    php_version = intent.php_version or ("8.3" if intent.app in ("wordpress", "laravel", "nextcloud") else None)
    return {
        "provision_site": {
            "domain": domain,
            "proxy_pass": None,
            "php": intent.wants_php or (app in ("wordpress", "nextcloud", "laravel", "laravel")),
            "php_version": php_version,
        },
        "configure_php_fpm": {"domain": domain, "php_version": php_version or "8.3"},
        "create_database": {
            "name": f"db_{domain.split('.')[0]}_{('' if not app else app)[:10]}",
            "db_type": "mysql",
        },
        "install_app": {"app": app, "domain": domain, "db_required": intent.wants_db},
        "issue_ssl": {"domain": domain, "staging": intent.staging},
        "reload_web": {"domain": domain},
        "enable_cache": {"cache": intent.wants_cache or "redis", "domain": domain},
        "remove_site": {"domain": domain},
    }


class PlanStep:
    """A single planned operation with resumable state."""

    def __init__(self, name: str, args: dict[str, Any]) -> None:
        self.name = name
        self.args = args
        self.executed = False
        self.ok = False
        self.result: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "step": self.name,
            "args": self.args,
            "executed": self.executed,
            "ok": self.ok,
            "result": _safe_json(self.result),
        }


class Plan:
    """An ordered, auditable sequence of PlanSteps."""

    def __init__(self, intent: Intent) -> None:
        self.intent = intent
        self.steps: list[PlanStep] = []

    def append(self, name: str, intent: Intent) -> None:
        self.steps.append(PlanStep(name, _cnf_payload(intent)[name]))

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent.describe(),
            "action": self.intent.action,
            "domain": self.intent.domain,
            "app": self.intent.app,
            "confidence": self.intent.confidence,
            "steps": [s.to_dict() for s in self.steps],
        }


def assemble_plan(intent: Intent) -> Plan:
    """Build an ordered Plan for a parsed intent."""
    plan = Plan(intent)
    order = PLAN_STEP.get(intent.action, [])

    if intent.action == "CREATE_SITE":
        # Deterministic app extension: WordPress/Nextcloud imply DB + PHP.
        # Other static sites only need the site provisioned.
        if intent.app in ("wordpress", "nextcloud", "laravel", "ghost"):
            order = ["provision_site", "configure_php_fpm", "create_database", "install_app"]
        elif intent.wants_db:
            order = ["provision_site", "create_database"]
        else:
            order = ["provision_site"]
        if intent.wants_php and "configure_php_fpm" not in order:
            order.insert(1, "configure_php_fpm")
        if intent.wants_cache:
            order.append("enable_cache")
        if intent.wants_ssl:
            order.append("issue_ssl")
        if order and order[-1] in ("issue_ssl", "enable_cache"):
            order.append("reload_web")

    for name in order:
        if name in ("remove_site",) and intent.action != "DELETE_SITE":
            continue
        if name in ("enable_cache",) and not intent.wants_cache:
            continue
        if name in ("issue_ssl",) and not intent.wants_ssl:
            continue
        if name in ("create_database", "install_app") and intent.action != "CREATE_SITE":
            continue
        plan.append(name, intent)
    return plan


def _safe_json(value: Any) -> Any:
    """Best-effort JSON-safe copy of a step result."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_safe_json(v) for v in value]
    if isinstance(value, dict):
        return {k: _safe_json(v) for k, v in value.items()}
    return str(value)


# ─── Execution ────────────────────────────────────────────────────────────

from atulya_launch import core


def _call(step: PlanStep) -> Any:
    """Invoke the core function for a plan step with its args."""
    if step.name == "install_app":
        app = step.args.get("app")
        domain = step.args.get("domain")
        if app == "wordpress":
            fn = getattr(core, "wordpress_install", None)
            if fn is None:
                return {"error": "wordpress installer unavailable"}
            return core.wordpress_install(domain=domain)
        fn = getattr(core, "app_install", None)
        if fn is None:
            return {"error": f"app installer unavailable for {app}"}
        return core.app_install(app_name=app, domain=domain)

    if step.name == "enable_cache":
        cache = step.args.get("cache", "redis")
        return {
            "planned": True,
            "cache": cache,
            "note": f"{cache} enable runs via /api/cache/{cache}/enable",
        }

    registry: dict[str, str] = {
        "provision_site": "site_create",
        "configure_php_fpm": "site_set_php_version",
        "create_database": "database_create",
        "issue_ssl": "ssl_issue_letsencrypt",
        "reload_web": "nginx_apply_and_reload",
        "remove_site": "site_delete",
    }
    fn_name = registry.get(step.name)
    fn = getattr(core, fn_name, None) if fn_name else None
    if fn is None:
        return {"error": f"no executor for step {step.name}"}

    kwargs = {"domain": step.args.get("domain")}
    if step.name == "configure_php_fpm":
        kwargs["php_version"] = step.args.get("php_version")
    elif step.name == "create_database":
        kwargs = {"name": step.args.get("name"), "db_type": step.args.get("db_type")}
    elif step.name == "issue_ssl":
        kwargs = {"domain": step.args.get("domain"), "staging": step.args.get("staging")}
    try:
        return fn(**kwargs)
    except Exception as exc:
        return {"error": str(exc)}


def apply_plan(plan: Plan, dry_run: bool = True, stop_on_error: bool = True) -> dict[str, Any]:
    """Execute a plan. `dry_run=True` returns the plan without running steps."""
    results = []
    if dry_run:
        for step in plan.steps:
            results.append({"step": step.name, "dry_run": True, "ok": True, "result": None})
        return {"intent": plan.intent.describe(), "dry_run": True, "ok": True, "results": results}

    ok_all = True
    for step in plan.steps:
        try:
            result = _call(step)
        except Exception as exc:
            result = {"error": str(exc)}
        step.executed = True
        step.ok = bool(result) and not (isinstance(result, dict) and result.get("error"))
        step.result = result
        results.append({"step": step.name, "dry_run": False, "ok": step.ok, "result": _safe_json(result)})
        if not step.ok and stop_on_error:
            ok_all = False
            break
    return {"intent": plan.intent.describe(), "dry_run": False, "ok": ok_all, "results": results}


def enrich_with_llm(text: str) -> dict[str, Any] | None:
    """Optional Tantra-LLM full-text parsing; returns raw JSON if available."""
    try:
        from Tantra import llm_chat  # type: ignore
        response = llm_chat(
            "You are a server-ops NL parser. Convert this command to JSON with keys: "
            "action (CREATE_SITE/DELETE_SITE/ENABLE_SSL/ENABLE_CACHE), domain, app, "
            "php_version, wants_php, wants_db, wants_cache, wants_ssl, staging.\n"
            f"Command: {text}"
        )
        raw = str(response)
        import json
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end > start:
            return json.loads(raw[start : end + 1])
    except Exception:
        pass
    return None