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

## Remaining Work

1. **Natural-language command layer** — "create a WordPress site example.com
   with Redis caching and SSL" → resolve intent → assemble a driver plan from
   the existing sites / rediscache / letsencryptwildcard APIs → dry-run →
   approve → apply. Audit the whole decision trace.
2. **Log-based diagnostics** — feed `/api/logs` + `/api/errorlogs` and recent
   metric deltas into an LLM to produce root cause + one-click fix suggestions.
3. **Auto-optimizer** — mine `bandwidth` and `resourcehistory` for trends and
   propose nginx/php-fpm tuning with apply/rollback.
4. **Learning backup scheduler** — learn low-usage windows from backup events
   and propose/shift schedules.
5. **Provider abstraction** — Tantra-LLM first, OpenAI-compatible fallback,
   keys stored in the panel config (never committed).

## Guardrails (non-negotiable)

- Every AI-initiated action is written to the audit log and reversible.
- Destructive actions require operator approval; only safe automations run
  unattended.
- AI endpoints must keep working with zero external AI dependencies installed.

## Exit Criteria

- [ ] All AI actions auditable + reversible.
- [ ] Destructive AI actions gated behind explicit operator approval.
- [ ] AI feature suite passes with no LLM installed (tests in
      `tests/test_new_features.py` already cover the offline path).
- [ ] One end-to-end NL command demo documented (e.g. "create WP + Redis +
      SSL").