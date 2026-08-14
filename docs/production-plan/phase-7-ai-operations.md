# Phase 7 - AI Operations

Turn Atulya Launch from a manual control panel into an **AI-native hosting
panel** that predicts, diagnoses, and (safely) self-heals — on top of the
existing driver, audit, and API foundations.

## Shipped in v1.1.0

- **Predictive health engine** — `atulya_launch/ai/predictive.py`:
  1. Collects a metric snapshot (CPU, memory, disk, load, network) reusing the
     health-dashboard helpers.
  2. Persists it into the `ai_metric_history` SQLite table.
  3. Fits a linear least-squares trend and forecasts the next value.
  4. Scores each metric (healthy / watch / warning / critical) and emits
     suggested actions (restart heavy process, rotate backups, review workers).
  5. Flags which actions are safe to automate.
- **API** — `atulya_launch/web/api/aipredict.py`:
  - `GET /api/ai/predict?hours=24&use_llm=true` — sample + evaluate + (optional)
    Tantra-LLM enrichment.
  - `GET /api/ai/history?hours=24` — raw samples.
  - `POST /api/ai/automate` — executes only safe automations (e.g. backup
    rotation on critical disk usage).
- **Zero-dependency by default** — the engine runs standalone. When Tantra-LLM
  is importable it augments the report with a plain-language diagnostic.

## Shipped in v1.1.1

- **Natural-language command layer** — `atulya_launch/ai/nlcommand.py`:
  1. `parse_intent(text)` — deterministic regex/entity parsing into an
     `Intent` (action, domain, app, php version, cache, ssl, staging). No
     external AI required.
  2. `assemble_plan(intent)` — maps the intent to an ordered `Plan` of
     concrete steps that reuse the panel's existing core APIs (`site_create`,
     `site_set_php_version`, `database_create`, `wordpress_install` /
     `app_install`, `ssl_issue_letsencrypt`, `nginx_apply_and_reload`,
     `site_delete`).
  3. `apply_plan(plan, dry_run=True)` — returns the full proposal for review;
     `dry_run=False` executes approved steps with a per-step audit trail.
- **API** — `atulya_launch/web/api/aicommand.py`:
  - `POST /api/ai/command` with `{command, dry_run=true}` → parsed intent +
    proposed plan; `dry_run=false` executes and records an `ai.command` audit
    entry. Confidence < 0.5 returns 422 asking for confirmation.
- **Optional LLM enrichment** — `enrich_with_llm()` round-trips Tantra-LLM
  parsed JSON back into the same `Intent` model; heuristic parsing is the
  offline default.
- **Supported actions**: `CREATE_SITE` (static / PHP / DB / app installs with
  optional cache + SSL), `DELETE_SITE`, `ENABLE_SSL`, `ENABLE_CACHE`.

## Remaining Work

1. **Log-based diagnostics** — feed `/api/logs` + `/api/errorlogs` and recent
   metric deltas into an LLM to produce root cause + one-click fix suggestions.
2. **Auto-optimizer** — mine `bandwidth` and `resourcehistory` for trends and
   propose nginx/php-fpm tuning with apply/rollback.
3. **Learning backup scheduler** — learn low-usage windows from backup events
   and propose/shift schedules.
4. **Provider abstraction** — Tantra-LLM first, OpenAI-compatible fallback,
   keys stored in the panel config (never committed).

## Guardrails (non-negotiable)

- Every AI-initiated action is written to the audit log and reversible.
- Destructive actions require operator approval; only safe automations run
  unattended.
- AI endpoints must keep working with zero external AI dependencies installed.

## Exit Criteria

- [x] AI actions auditable (per-step `PlanStep` state + `ai.command` audit).
- [ ] All AI actions reversible via the driver layer.
- [ ] Destructive AI actions gated behind explicit operator approval.
- [x] AI feature suite passes with no LLM installed (offline path tested in
      `tests/test_new_features.py` and `tests/test_nlcommand.py`).
- [x] End-to-end NL command demo covered by tests (e.g. "create WP + Redis +
      SSL").