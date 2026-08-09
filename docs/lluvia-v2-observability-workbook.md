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
| `rainfall.outbox.reused` | `service.py::queue_missing_analysis` | Request matched an existing pending outbox row — no new work enqueued. Also fires when a concurrent identical request lost a real race on `ix_rainfall_outbox_pending_unique` and recovered by re-reading the winner's row (`IntegrityError` caught, rolled back, re-`SELECT`ed) — both callers still get a 202 with the same `outbox_id`. | `source_id`, `role`, `scope_kind`, `scope_id`, `scope_version`, `year`, `labels` |
| `rainfall.outbox.cooldown` | `service.py::queue_missing_analysis` | A `done` row for this key completed within `RAINFALL_RECOMPUTE_COOLDOWN` (10 min) — re-enqueue skipped regardless of whether a revision exists. Governs the **request path only**; the scheduled sweeps below are not bound by it. | `source_id`, `role`, `scope_kind`, `scope_id`, `scope_version`, `year`, `outbox_id` |
| `rainfall.outbox.queued` | `service.py::queue_missing_analysis` | Missing work for this scope/year/role was enqueued. | `source_id`, `role`, `scope_kind`, `scope_id`, `scope_version`, `year`, `labels` |
| `rainfall.outbox.gated` | `tasks.py::_process_outbox_batch` | A `pending` row was SKIPPED (not processed, not failed, not retried) because its metric-role flag is OFF. The audit row is retained. | `source_id`, `role`, `scope_kind`, `scope_id`, `year` |
| `rainfall.outbox.done` | `tasks.py::_process_outbox_batch` | Row completed and set `status='done'`. Committed per-row (decision 2c); durable the instant this event fires. | `source_id`, `role`, `scope_kind`, `scope_id`, `year` |
| `rainfall.outbox.failed` | `tasks.py::_process_outbox_batch` | Row reached `MAX_RETRIES` and is terminal `failed`. | `source_id`, `role`, `scope_kind`, `scope_id`, `year`, `retry_count`, `error_type` (exception class name), `error_message` (truncated to 200 chars) |
| `rainfall.outbox.delayed` | `tasks.py::_process_outbox_batch` | Row failed transiently and was rescheduled (`pending`, new `next_attempt_at`). | same as `rainfall.outbox.failed` |
| `rainfall.compute.skipped` | `tasks.py::_process_outbox_row` | A `done` row with a legacy `NULL` `request_fingerprint` whose interval bounds are not exactly the year bounds (decision 4b) — compute cannot be safely derived, so it is skipped rather than guessed. | `reason` (`fingerprint_unavailable`), `source_id`, `role`, `scope_kind`, `scope_id`, `year` |
| `rainfall.outbox.batch_truncated` | `tasks.py::_process_outbox_batch` | R4-204: the batch stopped BETWEEN rows because `PROCESS_OUTBOX_WALL_CLOCK_BUDGET_SECONDS` (420s, under celery_app.py's default `task_time_limit=600` — this task is not in `RECOVERABLE_TASK_ANNOTATIONS`) elapsed. Every row processed before this point is already committed (decision 2c); the remaining candidates are picked up by the next minute's scheduled run. A graceful early return instead of the hard SIGKILL the un-truncated loop would otherwise eventually hit under a burst of slow rows. | `processed` (count so far this call), `remaining` (candidates not yet attempted) |

### 2.3 Materialization — revision writes, the latch, and the daily/year-rollover sweep

| Event | Emitter | Meaning | Key fields |
|---|---|---|---|
| `rainfall.build.revision_written` | `tasks.py::_persist_analysis_revision` | A `rainfall_analysis_revision` row was written (or would-be-idempotent-no-op) for a fingerprint. **Fires pre-commit**, inside the row's `SAVEPOINT` (decision 2b/2c) — a commit failure AFTER this point still yields this event for work that then rolls back. Bounded: `rainfall.outbox.done` (fired post-commit, above) is the durable signal that the row's work actually landed; do not alert on `revision_written` alone. | `data_revision`, `created` (`true` for a genuinely new row, `false` for `persist_revision`'s own idempotent no-op) |
| `rainfall.build.latched` | `tasks.py::_persist_analysis_revision` | The write gate (`revision_write_decision`) returned `"latched"`: a provisional candidate over an already-served `final` incumbent was refused, unconditionally, under the per-fingerprint advisory lock (design.md "Serializing siblings"). Zero new revision rows. `incumbent_source_id` is read through `served_state()` (R2-002), the same single reader every other consumer of the served envelope uses. | `data_revision`, `source_id` (the refused candidate's), `incumbent_source_id` |
| `rainfall.finalization.gate_refused` | `tasks.py::_persist_analysis_revision` | The write gate returned `"gate_refused"`: a cross-source (finalization) candidate would be `suppressed` under `RAINFALL_METRIC_POLICY` (the SAME function the disclosure path runs). Zero new revision rows; the previously served snapshot is untouched, and the sweep keeps retrying on its normal schedule (not a one-shot refusal). | `scope_kind`, `scope_id`, `scope_version`, `year`, `coverage`, `completeness`, `quality_score` (R2-008: flat fields, the same shape `rainfall.finalization.skipped` below uses — was a nested `scope` object) |

### 2.4 Daily revisit sweep — stage 1 (current-year refresh) and stage 2 (year-rollover finalization)

Both stages run inside the single `rainfall.revisit_stale` Beat task (`crontab(minute="30", hour="3")`, `America/Argentina/Cordoba`, `bind=True`/`max_retries=2` restored — R4-203). Their re-enqueue is a DIFFERENT mechanism from `queue_missing_analysis` and is deliberately not bound by `rainfall.outbox.cooldown` above (see the "GEE Quota Guards on Request-Path Re-enqueue and Poll" spec requirement — the cooldown governs the request path only).

| Event | Emitter | Meaning | Key fields |
|---|---|---|---|
| `rainfall.revisit.skipped` | `tasks.py::_revisit_stage1` | Stage 1 skipped a current-year `done` key. `reason="fingerprint_unavailable"`: the newest `done` row has a `NULL` `request_fingerprint` (pre-`lluvia_v2_005` legacy row). `reason="pending_in_flight"`: a refresh for this key is already `pending` (the upfront check, or the `IntegrityError` backstop on `ix_rainfall_outbox_pending_unique` firing the same reason). | `reason`, `source_id`, `role`, `scope_kind`, `scope_id`, `scope_version`, `year` |
| `rainfall.revisit.completed` | `tasks.py::_revisit_stale` | Stage 1 finished this sweep (whether or not it raised — see `rainfall.revisit.failed` below). `truncated=true` when `revisit_scanned == MAX_OUTBOX_BATCH` (50): the candidate set may hold more current-year keys than this run reached: the NEXT sweep continues from a rotated cursor (`repository.current_year_done_keys`, C2), not from the same lexicographic prefix. | `revisit_scanned`, `revisit_enqueued`, `revisit_skipped`, `truncated` |
| `rainfall.revisit.failed` | `tasks.py::_revisit_stale` | Stage 1 raised an unexpected exception (a DB error, not a per-key skip reason above). Stage 2 still runs this cycle (R4-203); the task retries via Celery's own `bind=True`/`max_retries=2` after both stages have already run and recorded their events. | `error_type`, `error_message` (truncated to 200 chars, same convention as `rainfall.outbox.failed`) |
| `rainfall.finalization.skipped` | `tasks.py::_revisit_stage2` | Stage 2 skipped a completed-year `daily`/`done` candidate before enqueueing a transition. `reason="revision_missing"`: the `done` row has no revision at all (the JDA-002 healing case, not a finalization case). `reason="provenance_unavailable"`: the served snapshot's `served_state()` returned `None` (a corrupt or pre-contract row) — treated as unknown, never as finalized. `reason="event_window_key"`: the candidate's interval bounds are not the year bounds (structurally unreachable — `resolve_missing_work_source` routes any `event_window` request to the `intensity` role before the year test — kept as a loud assertion). `reason="pending_in_flight"`: the RE-RESOLVED key (`chirps-v3-final`/`historical`, not the stale `done` row's own key) already has a transition pending. | `reason`, `scope_kind`, `scope_id`, `scope_version` (R2-008: was missing), `year` |
| `rainfall.finalization.completed` | `tasks.py::_revisit_stale` | Stage 2 finished this sweep. `finalization_terminated` (R2-004) counts keys the per-row `served_state` defense-in-depth check terminated on THIS run — see the termination paragraph below for why that count is normally zero. `finalization_scanned == finalization_enqueued + finalization_skipped + finalization_terminated` always closes. `truncated=true` when `finalization_scanned == MAX_OUTBOX_BATCH`, same rotation caveat as stage 1's event. | `finalization_scanned`, `finalization_enqueued`, `finalization_skipped`, `finalization_terminated`, `truncated` |

**Termination is no longer silent by construction, and it is primarily an SQL-side exclusion, not a Python `continue`** (C1, closed in the PR3 review fix round — the earlier text here claiming the SQL pre-filter already did this was FALSE at the time it was written; it is corrected now that the fix landed). `repository.completed_year_daily_done_keys` reads each candidate key's own newest revision (the same `created_at DESC, id DESC` order `get_snapshot` uses) and excludes it from the SQL result the moment that revision discloses `("chirps-v3-final", "final")` — a terminated key simply stops appearing in `finalization_scanned` on the next sweep, which is why the count can legitimately DROP between two consecutive runs. The per-row Python `served_state` check inside `tasks._revisit_stage2` stays as defense-in-depth for the race the SQL exclusion's own docstring documents (relying on the latch's guarantee that a provisional revision is never written over a final incumbent), and now increments `finalization_terminated` in `rainfall.finalization.completed` above instead of silently `continue`-ing — in steady state this count is zero, because the SQL exclusion already did the job before the row ever reached this check. There is still no dedicated PER-KEY termination event: the transition itself is already fully observable via `rainfall.analysis.served`/`get_snapshot`, and the aggregate `finalization_terminated` counter is enough to see that the defense-in-depth path is (correctly) idle.

### 2.5 Metrics drivers — the two numbers that mean the most

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