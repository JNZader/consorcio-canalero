# Lluvia v2 — Observability Workbook

Authoritative companion to the Rainfall v2 (lluvia-v2) operations rollout.
This document IS the source of truth for the meaning of every rainfall metric
event and gauge emitted from `gee-backend`, and for the owners/rollout
procedures (Task 4.3 and Task 4.2 of the change).

The runtime seam that emits these events lives in
`gee-backend/app/domains/geo/rainfall/metrics.py`. That module's docstring
points here; do not rely on inline commentary for semantics — the catalogue
below is the contract.

## 1. What ships

| Deliverable | Location | Status |
|---|---|---|
| Metrics-ready seam | `app/domains/geo/rainfall/metrics.py` | shipped (this change) |
| Feature-flag gate (per metric-role) | `app/domains/geo/rainfall/feature_flags.py` + `tasks.py::_role_enabled` | shipped (this change) |
| Rollback = disable flags/jobs, keep audits | see §5 | shipped + tested |
| Latency / queue events wired | `router.py`, `service.py`, `tasks.py` | shipped (this change) |

No metrics backend (Prometheus / OTel / statsd) is required for this change:
production parsing is the app's existing single `structlog` configuration,
which routes ALL stdlib `logging` records through its `ProcessorFormatter`
`foreign_pre_chain`. Every event below already ships as one JSON envelope
(`event`, `level`, `service`, `worker_id`, `timestamp`). Wiring a real
counters/gauges backend later is a change ONLY to `metrics.py` — call sites
are untouched.

## 2. Event catalogue (stable names)

Event names are `rainfall.<area>.<action>`. Fields are always emitted as keys
on the JSON payload; a missing field is absent, never `null`-as-zero unless a
column is genuinely absent.

### 2.1 Serve path — latency and disclosure

| Event | Emitter | Meaning | Key fields |
|---|---|---|---|
| `rainfall.analysis.served` | `router.py::read_analysis` | A fully-normalized, policy-agreed analysis snapshot was returned (HTTP 200). `latency_ms` is the full handler time from request arrival to normalized response. | `revision_id`, `scope_kind`, `scope_id`, `scope_version`, `year`, `latency_ms` |
| `rainfall.csv.served` | `router.py::export_analysis` | An authorized CSV export was returned. | `revision_id`, `latency_ms` |

### 2.2 Ingest queue — gaps / outcome

| Event | Emitter | Meaning | Key fields |
|---|---|---|---|
| `rainfall.outbox.reused` | `service.py::queue_missing_analysis` | Request matched an existing pending outbox row — no new work enqueued. | `source_id`, `role`, `scope_kind`, `scope_id`, `scope_version`, `year`, `labels` |
| `rainfall.outbox.queued` | `service.py::queue_missing_analysis` | Missing work for this scope/year/role was enqueued. | same as above |
| `rainfall.outbox.gated` | `tasks.py::_process_outbox_batch` | A `pending` row was SKIPPED (not processed, not failed, not retried) because its metric-role flag is OFF. The audit row is retained. | same as above |
| `rainfall.outbox.done` | `tasks.py::_process_outbox_batch` | Row completed and set `status='done'`. | same as above |
| `rainfall.outbox.failed` | `tasks.py::_process_outbox_batch` | Row reached `MAX_RETRIES` and is terminal `failed`. | same + `retry_count` |
| `rainfall.outbox.delayed` | `tasks.py::_process_outbox_batch` | Row failed transiently and was rescheduled (`pending`, new `next_attempt_at`). | same + `retry_count` |

### 2.3 Metrics drivers — the two numbers that mean the most

| Alert axis | Derived from | Descripción |
|---|---|---|
| Latency | `rainfall.analysis.served.latency_ms` | p50/p95 of the served path; provider fan-out is bounded by adapters, so this is DB + policy + serialization time. |
| Backlog / freshness | count(`rainfall.outbox.*` with `status='pending'` in DB), plus `done/failed/delayed/gated` rates | Gaps between requested and served analysis; a sustained plateau of `pending` with zero `done` means the flag gate or the provider is stuck. |
| Fallback | `SourceSelection.fallback_used` is per-request, not yet emitted as a counter — see §5 open items. | Metric-level ordered source fallback; no blending. |
| Revision health | `analysis.served.revision_id` + `metric_contract_valid` states | Immutable snapshots keep audit; a rising `unavailable(metric_contract_invalid)` share indicates a contract drift between writer and reader. |

## 3. Feature-flag activation gate (rollout control)

Setting key (system settings, category `analisis`, value is an object):

```
analisis/rainfall_feature_flags = {
  "historical": true,
  "daily":      true,
  "intensity":  true,
  "validation": false
}
```

The blob must always list ALL four roles explicitly — the role set is fixed at
`historical`, `daily`, `intensity`, `validation` (the four `RAINFALL_SOURCE_ROLES`).

Semantics (`feature_flags.py`, `tasks.py::_role_enabled`) — the three explicit states:

- **Absent setting = OPEN**: if `analisis/rainfall_feature_flags` is never set,
  every role runs (`_role_enabled` returns `True` for an unconfigured system).
  This is intentional: a stack that ran before the gate existed keeps working
  for sequential rollout.
- **Configured blob**: only roles listed with an explicit `true` run.
- **Omitted role in a configured blob = false**: the missing role is gated off.
  A partially written blob therefore DISABLES the omitted role; it does not
  open it. Expected `false` in a configured blob is the explicit **rollback
  signal**.

Enforcement points:

1. `tasks.py::ingest_source_scope` — raises `RainfallRoleDisabled` before any
   provider contact. Disabled role never reaches the adapter.
2. `tasks.py::_process_outbox_batch` — skips (never processes, never fails,
   never retries) rows whose role is off; audit row stays `pending`.

## 4. Rollback procedure (Task 4.2)

Rollback must DISABLE, never DELETE — and never by REMOVING the key.

1. Flip the flag: write the COMPLETE blob under
   `analisis/rainfall_feature_flags` with EVERY role explicitly `false`:

   ```
   analisis/rainfall_feature_flags = {
     "historical": false,
     "daily":      false,
     "intensity":  false,
     "validation": false
   }
   ```

   Omit nothing. NEVER remove the key to disable: an absent setting is the
   unconfigured OPEN default (`_role_enabled` returns `True`), so removing the
   key RE-ENABLES every role — the opposite of a rollback. Remember the
   unset/configured semantics: absent setting = OPEN (all roles run);
   configured blob = only the roles listed `true` run; omitted role in a
   configured blob = false (rollback signal).
2. Disable the Celery Beat jobs that schedule ingest/revisit/backfill (the
   outbox consumer keeps draining nothing queued).
3. Keep all rows: `rainfall_outbox`, `rainfall_source_eligibility`,
   `rainfall_interval_value`, `rainfall_analysis_revision` are NOT touched.
   The public 1991–2020 normal and `PrecipChart` never depend on this v2 news.
4. Re-enable: set roles back to `true`; the outbox consumer resumes
   `pending`- drain and backfill checkpoints continue (idempotent — replays
   are no-ops via the `already_complete` checkpoint)
5. Audits: every decision point happens through immutable
   `rainfall_analysis_revision`; replay/key checks move between terminal
   states and are never double-ingested (partial unique index on
   `rainfall_outbox.status='pending'`).

Procement is verified by `tests/new/geo/rainfall/test_phase4_verification.py`.

## 5. Open items — manual owner decisions (Task 4.3 completion)

These are intentionally left OPEN for a human owner to close; this workbook
records them so none is lost:

1. **Named owners** — the design requires named people for technical-lead,
   data-operations and validation-approval roles. No names are assigned yet;
   fill in the table below.
2. **Prometheus / OTel backend wiring** — currently log-only; decide when a
   counter/gauges endpoint backend is needed, then edit ONLY `metrics.py`.
3. **Fallback counter** — `fallback_used` lives on the per-request snapshot,
   not yet aggregated into its own `rainfall.source.fallback` event. If a
   fallback metric is part of the deployment SLO, add
   `rainfall.source.fallback` {metric, chosen_source, fallback_used,
   rejected_sources} at the selection call site.
4. **Source-health gauge** — `rainfall.health.????` for per-source
   freshness/available_through is defined in the schema; emitting a gauge on a
   beat is open.
5. **Backlog gauge alert threshold** — pick the `pending`-plateau window and
   alert level (e.g. pending > 50 for > 10 min while gate enabled).

Owners table (to fill):

| Role | Name (assign) |
|---|---|
| Domain technical lead (policy approval) | — |
| Data operations (spike/backfill runner) | — |
| Validation approval (golden reports) | — |
| On-call for rainfall check | — |