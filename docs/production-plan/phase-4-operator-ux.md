# Phase 4 - Operator UX

Goal: make daily hosting work understandable, fast, and calm.

## Scope

- Flash messages and toasts.
- Live metrics.
- Better file manager.
- Audit/activity feed.
- Global search.
- Mobile navigation.
- Consistent empty/error/loading states.

## Scaffolded Work Items

| ID | Task | Size | Status |
| --- | --- | --- | --- |
| P4-01 | Flash message helpers and base template rendering | Medium | Todo |
| P4-02 | Toast bridge for API and HTMX errors | Medium | Todo |
| P4-03 | SSE or polling dashboard metrics | Medium | Todo |
| P4-04 | File manager upload progress | Medium | Todo |
| P4-05 | File editor with safe save/preview | Medium | Todo |
| P4-06 | Archive compress/extract with traversal protection | Medium | Todo |
| P4-07 | Global command search | Medium | Todo |
| P4-08 | Audit feed filters | Medium | Todo |
| P4-09 | Mobile sidebar and responsive tables | Medium | Todo |
| P4-10 | Dark/light mode cleanup | Small | Todo |

## UX Policy

- Every write action must show success or failure.
- Long-running actions must show progress, status, or a queued job state.
- Empty states should tell the operator what object is missing, not explain the
  whole product.
- Tables must stay readable on mobile.

## Acceptance Criteria

- Operators can create a site, DNS zone, DB, mailbox, SSL cert, backup, and
  restore without reading server logs.
- Common failed actions show a clear next step.
- Mobile layout is usable for emergency operations.

## Test Hooks

- Future template rendering tests.
- Future Playwright smoke tests for dashboard, DNS, sites, files, backups.
