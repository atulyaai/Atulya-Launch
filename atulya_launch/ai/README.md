# Atulya Launch AI Engine

`atulya_launch/ai/` implements the panel's AI layer. It is **dependency-free
by design**: everything works with the Python standard library, and Tantra-LLM
integration is optional.

## Modules

### `predictive.py` — predictive health

1. **Sample** — a metric snapshot (CPU %, memory %, disk %, load 1m, bytes
   sent/recv) is collected by reusing the health-dashboard helpers
   (`web/api/healthdashboard.py`).
2. **Persist** — the sample is stored in the `ai_metric_history` SQLite table.
3. **Forecast** — a linear least-squares trend is fit over the recent history
   and the next value is projected.
4. **Score** — each metric is graded healthy / watch / warning / critical from
   threshold bands, with an action attached (restart heavy process, rotate
   backups, review workers).
5. **Automate** — only actions flagged `auto=True` (currently backup rotation
   on critically-full disk) are executed by `/api/ai/automate`. Process
   restarts always require operator approval.

### `nlcommand.py` — natural-language commands

Turns free-text operator commands into structured, auditable plans:

1. **Parse** — `parse_intent()` deterministically extracts an `Intent`
   (action, domain, app, PHP version, cache, SSL, staging) with regex/entity
   detection. Zero external AI required.
2. **Plan** — `assemble_plan()` maps the intent to an ordered `Plan` of steps
   that reuse the panel's core APIs (`site_create`, `site_set_php_version`,
   `database_create`, `wordpress_install`/`app_install`,
   `ssl_issue_letsencrypt`, `nginx_apply_and_reload`, `site_delete`).
3. **Apply** — `apply_plan(dry_run=True)` returns the proposal for review;
   `dry_run=False` executes approved steps, recording per-step state, and
   `/api/ai/command` writes an `ai.command` audit entry.

Supported actions: `CREATE_SITE` (static / PHP / DB / app installs with
optional cache + SSL), `DELETE_SITE`, `ENABLE_SSL`, `ENABLE_CACHE`.

## API

| Endpoint | Purpose |
| --- | --- |
| `GET /api/ai/predict?hours=24&use_llm=true` | Sample + evaluate + optional LLM analysis |
| `GET /api/ai/history?hours=24` | Raw metric history |
| `POST /api/ai/automate` | Run safe automated actions for critical metrics |
| `POST /api/ai/command` | Parse an NL command; `dry_run=true` returns the plan, `dry_run=false` executes it |

## Optional LLM enrichment

When `Tantra` is importable, `analyze_with_llm()` augments the predictive
report and `enrich_with_llm()` round-trips an LLM-parsed JSON intent back into
the NL command `Intent` model. Without it everything still works standalone.

## Tests

- `tests/test_new_features.py` — prediction, history recording, risk scoring,
  Windows-safe metric sampling.
- `tests/test_nlcommand.py` — intent parsing, plan ordering, dry-run/apply,
  `/api/ai/command` endpoint (offline path).