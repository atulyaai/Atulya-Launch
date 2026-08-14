# Atulya Launch AI Engine

`atulya_launch/ai/predictive.py` implements the panel's predictive-health
engine. It is **dependency-free by design**: everything works with the Python
standard library, and Tantra-LLM integration is optional.

## Flow

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

## API

| Endpoint | Purpose |
| --- | --- |
| `GET /api/ai/predict?hours=24&use_llm=true` | Sample + evaluate + optional LLM analysis |
| `GET /api/ai/history?hours=24` | Raw metric history |
| `POST /api/ai/automate` | Run safe automated actions for critical metrics |

## Optional LLM enrichment

When `Tantra` is importable, `analyze_with_llm()` augments the report with a
plain-language diagnostic. Without it the engine still returns a full report.

## Tests

`tests/test_new_features.py` covers prediction, history recording, risk
scoring, and the Windows-safe metric sampling path.