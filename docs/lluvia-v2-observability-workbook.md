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
| `rainfall.xlsx.served` | `router.py::export_analysis_xlsx` | An authorized **xlsx** export was returned (design.md D7): the friendly two-sheet view — Resumen (the same `metric_rows(normalize_snapshot(...))` projection the CSV serializes) and Serie diaria (the same `build_series` contract `/series` serves). Read-only, like the CSV and `/series` routes: it enqueues nothing. The three disclosure fields are stamped INTO the file, not just logged, because a workbook outlives the screen that would have shown them — `consistent_with_snapshot`/`consistency_reason` become the Resumen row "Serie diaria consistente con el análisis: sí \| no — &lt;motivo&gt;", and `normal_curve_state` becomes "Curva normal 1991–2020", whose three labels must read differently (a `suppressed` and an `integrity_refused` curve leave byte-identical empty columns). **When it spikes**: a share of `consistent_with_snapshot: false` mirrors `rainfall.series.served` and needs no separate investigation; any `normal_curve_state: integrity_refused` here is the same data-integrity incident described under `rainfall.series.normal_curve_refused` and is worse in this route, because the reader keeps the file. `bytes` is the payload size — a sudden collapse toward the empty-workbook floor means the projection stopped producing rows. | `revision_id`, `consistent_with_snapshot`, `consistency_reason`, `normal_curve_state`, `points`, `bytes`, `latency_ms` |
| `rainfall.analysis.policy_revision_stale` | `router.py::read_analysis` | The served revision was written under a SUPERSEDED `metric_policy.revision`. It is still served — normalized with its OWN policy revision, so it stays self-consistent — and a refresh labelled `policy_revision_stale` is enqueued so the enriched envelope eventually lands. Neither scheduled sweep revisits a past-year key that is already `done`, so the request path is the only place this is noticed. **When it spikes**: expected and self-limiting right after a `RAINFALL_METRIC_POLICY_REVISION` bump — one burst per key that anyone actually views, then silence. A rate that does NOT decay means the refreshes are not landing: check `rainfall.outbox.cooldown` for a `reason` other than `recent_done` (a key stuck behind the failed or gate-refused backoff) and `rainfall.outbox.failed`. | `revision_id`, `scope_kind`, `scope_id`, `scope_version`, `year`, `served_policy_revision`, `current_policy_revision` |
| `rainfall.series.served` | `router.py::read_analysis_series` | The daily series for one stored revision was returned (HTTP 200). Read-only: this route enqueues nothing, so it can never turn a chart into GEE work. `consistent_with_snapshot` is the **server-side pin** (design.md D3): the revision's `data_revision` digest recomputed over exactly the keys and the D6-widened window the build read, compared with the digest stored on the row. It speaks about the **selected scope's own intervals only** — the baseline store is not in that hash, so a `true` pin never vouches for the normal curve (see `normal_curve_state` below and `rainfall.series.normal_curve_refused`). `consistency_reason` is `null` when it matches, and otherwise one of the two values in the table under this section. `normal_curve_state` is `available` (a curve was computed and passed its integrity checks), `suppressed` (there is no baseline to draw — an unmapped scope, a thin baseline, invalid evidence at build time) or `integrity_refused` (a curve was computable and was thrown away). **When it spikes**: a rising share of `data_revision_moved` on current-year keys is normal NRT correction traffic — the chart still renders, above its staleness notice — but a key that stays inconsistent means its refresh is not landing (correlate with `rainfall.outbox.cooldown` and `rainfall.outbox.failed`). | `revision_id`, `data_revision`, `consistent_with_snapshot`, `consistency_reason`, `normal_curve_state`, `points`, `latency_ms` |
| `rainfall.analysis.requeue_failed` | `router.py::_requeue_stale_revision` | LI2B-002: the stale-policy refresh above could not be enqueued (any `SQLAlchemyError`, or the `RuntimeError` `queue_missing_analysis` raises when its `IntegrityError` recovery finds no row). The read is **still served** from the snapshot already in memory — a background bookkeeping failure never degrades an answer the system already has. The enqueue runs inside its own SAVEPOINT, rolled back here, so the session is not left in an aborted transaction (SQLSTATE 25P02) that would poison every later statement. **When it spikes**: this is a database-health signal, not a rainfall signal — the reads are fine and the refreshes are not happening, so the enriched envelope will not land until it stops. Correlate with connection-pool/DB alerts, and expect `policy_revision_stale` to stay flat instead of decaying while it lasts. | `scope_kind`, `scope_id`, `scope_version`, `year`, `error_type` (exception class name), `error_message` (truncated to 200 chars) |
| `rainfall.series.normal_curve_refused` | `series.py::build_series` | LI3A-001: the normal curve was computed and then **refused**, so the response carries `normal_curve_state: "integrity_refused"` and every `normal_accumulated` is `null`. The curve is read LIVE from the baseline store while `annual.normal.value` was computed once at build time and is immutable, and nothing rebuilds a finalized past year — so a curve that has drifted would otherwise be drawn contradicting the card it sits beside, under a pin that still reports `consistent_with_snapshot: true`. `reason` is `duplicate_baseline_slot` (two non-superseded rows share one `interval_start` — the same broken invariant `baseline_cumulatives` raises `DuplicateBaselineSlotError` on, which inflates the curve while hiding itself), `last_point_disagrees_with_stored_normal` (the curve's last point is not `annual.normal.value` within float tolerance — design.md D3's acceptance rule, enforced at runtime), or `stored_normal_unreadable` (the snapshot marks `annual.normal` available with no numeric value, so the check cannot run). **When it fires**: never, in a healthy deployment — treat any occurrence as a data-integrity incident, not as noise. For `duplicate_baseline_slot`, find the offending slot with `SELECT interval_start, provider_revision, value FROM rainfall_interval_value WHERE scope_kind='provider_asset' AND scope_id=<asset> GROUP BY ... HAVING count(*) > 1` and repair it the same way as a `rainfall.baseline.duplicate_slots` alert (§2.3) — the two events are the same defect seen from the read side and the build side, and the build side will already be suppressing `annual.normal` on every NEW revision for that asset. For `last_point_disagrees_with_stored_normal`, the baseline evidence has moved since the revision was built: compare the stored `annual.normal.value` against a fresh `baseline_cumulatives` read at the same cutoff, and rebuild the affected revisions rather than "fixing" the curve. `stored_normal_unreadable` is a corrupt snapshot envelope — escalate, do not repair in place (revision rows are append-only). | `revision_id`, `reason`, `scope_kind`, `scope_id`, `scope_version`, `year` |

**`consistency_reason` — the two values, and what each one means for the operator** (LI3A-002). The enum stays at **three** states in total (`null`, plus the two below): the pin reports "not exactly one revision family" for BOTH zero families and two-or-more, deliberately, because with zero rows the build's own family cannot be reconstructed either — so no fourth value was added for the empty case. That makes one string cover two operationally opposite situations, which this table separates.

The table below is a table of **VALUES of one field**, not of events. `rainfall.analysis.requeue_failed` spent slice 3a as its last row (JDA-004 / JDB-002) — a substring search found it, so the catalogue pin stayed green, while a reader saw a fourth `consistency_reason` the API can never emit and the §2.1 event table had lost the event entirely. New events go in the event table above; nothing but the enum's own values goes below. Both halves are now pinned structurally by `test_slice2b_resilience_fixes.py` (`test_every_new_rainfall_event_is_documented_in_the_observability_workbook`, `test_the_consistency_reason_table_lists_only_consistency_reasons`), which parse the tables rather than grep the file — leave a blank line between them, because that blank line is what makes them two tables.

| `consistency_reason` | Shape | What it means | What to do |
|---|---|---|---|
| `data_revision_moved` | — | The daily values behind the revision were corrected after it was stored (an NRT supersession inside the build's window). | Normal for current-year keys. The chart still renders above its staleness notice. A key that stays inconsistent means its refresh is not landing — correlate with `rainfall.outbox.cooldown` and `rainfall.outbox.failed`. |
| `interval_family_ambiguous` | **Zero resolved rows** (`points` are all `mm: null`) | The revision was built with no interval evidence at all — `revision_write_decision` writes a snapshot with `annual.selected.state: "unavailable"` when there is no incumbent, and that revision hashed an empty interval set. With nothing to read, there is no family to reconstruct. **Benign**, and `consistent_with_snapshot` is permanently `false` for that revision: it can never flip to `true`, because once rows DO arrive the digest recomputes over a non-empty set and reports `data_revision_moved` instead. | Nothing, as an integrity matter. It is an ingest signal: the key has no data. Check `rainfall.outbox.*` for that scope/year. |
| `interval_family_ambiguous` | **Two or more live families** (`points` carry real values) | Two non-superseded revision families share one window. Decision 7's one-family-per-source invariant says this cannot happen, so it is a **real invariant breach** and the pin refuses to guess which family the build used. | Investigate. Identify the families with `SELECT DISTINCT provider_revision FROM rainfall_interval_value WHERE ...` over the build window and find the correction whose supersession link never landed. |

### 2.2 Ingest queue — gaps / outcome

| Event | Emitter | Meaning | Key fields |
|---|---|---|---|
| `rainfall.outbox.reused` | `service.py::queue_missing_analysis` | Request matched an existing pending outbox row — no new work enqueued. Also fires when a concurrent identical request lost a real race on `ix_rainfall_outbox_pending_unique` and recovered by re-reading the winner's row (`IntegrityError` caught, rolled back, re-`SELECT`ed) — both callers still get a 202 with the same `outbox_id`. | `source_id`, `role`, `scope_kind`, `scope_id`, `scope_version`, `year`, `labels` |
| `rainfall.outbox.cooldown` | `service.py::queue_missing_analysis` | Re-enqueue was skipped because this key is inside one of the three request-path cooldowns (`service._requeue_cooldown`), named by `reason`. Governs the **request path only**; the scheduled sweeps below are not bound by it. See the cooldown ladder below the table for what each `reason` means and what to do when it dominates. | `source_id`, `role`, `scope_kind`, `scope_id`, `scope_version`, `year`, `outbox_id`, `reason`, `cooldown_seconds` |
| `rainfall.outbox.queued` | `service.py::queue_missing_analysis` | Missing work for this scope/year/role was enqueued. | `source_id`, `role`, `scope_kind`, `scope_id`, `scope_version`, `year`, `labels` |
| `rainfall.outbox.gated` | `tasks.py::_process_outbox_batch` | A `pending` row was SKIPPED (not processed, not failed, not retried) because its metric-role flag is OFF. The audit row is retained. | `source_id`, `role`, `scope_kind`, `scope_id`, `year` |
| `rainfall.outbox.done` | `tasks.py::_process_outbox_batch` | Row completed and set `status='done'`. Committed per-row (decision 2c); durable the instant this event fires. | `source_id`, `role`, `scope_kind`, `scope_id`, `year` |
| `rainfall.outbox.failed` | `tasks.py::_process_outbox_batch` | Row reached `MAX_RETRIES` and is terminal `failed`. | `source_id`, `role`, `scope_kind`, `scope_id`, `year`, `retry_count`, `error_type` (exception class name), `error_message` (truncated to 200 chars) |
| `rainfall.outbox.delayed` | `tasks.py::_process_outbox_batch` | Row failed transiently and was rescheduled (`pending`, new `next_attempt_at`). | same as `rainfall.outbox.failed` |
| `rainfall.compute.skipped` | `tasks.py::_process_outbox_row` | A `done` row with a legacy `NULL` `request_fingerprint` whose interval bounds are not exactly the year bounds (decision 4b) — compute cannot be safely derived, so it is skipped rather than guessed. | `reason` (`fingerprint_unavailable`), `source_id`, `role`, `scope_kind`, `scope_id`, `year` |
| `rainfall.outbox.batch_truncated` | `tasks.py::_process_outbox_batch` | R4-204: the batch stopped BETWEEN rows because `PROCESS_OUTBOX_WALL_CLOCK_BUDGET_SECONDS` (420s, under celery_app.py's default `task_time_limit=600` — this task is not in `RECOVERABLE_TASK_ANNOTATIONS`) elapsed. Every row processed before this point is already committed (decision 2c); the remaining candidates are picked up by the next minute's scheduled run. A graceful early return instead of the hard SIGKILL the un-truncated loop would otherwise eventually hit under a burst of slow rows. | `processed` (count so far this call), `remaining` (candidates not yet attempted) |

**The request-path cooldown ladder (`rainfall.outbox.cooldown.reason`).** Each `reason` is one terminal state a key's own history can be in, and each has its own window; `service._requeue_cooldown` evaluates them in this order and stops at the first match. Only the request path is bound by them — the scheduled sweeps enqueue through a different mechanism (§2.4).

| `reason` | Window | Fires when | What to do when it dominates |
|---|---|---|---|
| `recent_done` | 10 min (`RAINFALL_RECOMPUTE_COOLDOWN`) | The key's newest `done` row completed inside the window. The ordinary, expected case — it is what keeps a 5-second frontend poll from becoming a per-poll GEE fetch. | Nothing. A high rate here is the guard working. |
| `terminal_failed` | 6 h (`RAINFALL_FAILED_REQUEUE_COOLDOWN`) | The key's newest terminal row is `failed` — it exhausted `MAX_RETRIES` inside the window. **LI2B-001**: before this cooldown existed, a `failed` row matched neither the `done` cooldown nor the pending pre-check, so every poll started a fresh 5-attempt cycle; for a deterministic compute-time failure (ingest succeeds, so the adapter's circuit breaker never trips) that never terminated on its own. | Read the paired `rainfall.outbox.failed` for that key's `error_type`. A repeating `terminal_failed` on the SAME key is a deterministic failure that will not heal by waiting — `rainfall.baseline.duplicate_slots` (§2.3) is one known cause. The cooldown bounds the cost (≤ 4 retry cycles/day); it does not fix the key. |
| `non_write_latched` / `non_write_gate_refused` | 24 h (`RAINFALL_REFUSED_REQUEUE_COOLDOWN`) | The key's newest `done` row carries an `outcome:` marker — its build ran to completion but `revision_write_decision` refused to write (see the marker semantics below). | Expected in small numbers around a year rollover. A key stuck here for days is waiting on upstream data quality, not on this system: correlate with `rainfall.finalization.gate_refused`'s `coverage`/`completeness`/`quality_score` for that scope/year. |

**`outcome:` markers on the outbox row (LI2B-003).** `revision_write_decision` can return `latched` or `gate_refused`, both of which write **no revision** while the row still finishes cleanly as `done` — the work ran, it just produced nothing new. `tasks._process_outbox_row` therefore appends `outcome:latched` / `outcome:gate_refused` to that row's `work_labels` (`RainfallOutbox` has no result/note column, so `work_labels` is the only schema-compatible place to record it). Two consequences worth knowing when reading rows by hand:

- A `done` row carrying an `outcome:` marker is **not** a productive completion. Without the marker it is indistinguishable from one, which is exactly why the served snapshot used to stay stale while the key was re-enqueued every 10 minutes forever.
- The markers are **stripped** whenever either sweep copies a row's labels onto a fresh `pending` row (`service.carryover_labels`, used by `tasks._revisit_stage1`/`_revisit_stage2`): a marker describes ONE build's decision, never the work itself, so a key that has since been rebuilt does not inherit its own past refusal — and does not keep backing off because of it.

### 2.3 Materialization — revision writes, the latch, and the daily/year-rollover sweep

| Event | Emitter | Meaning | Key fields |
|---|---|---|---|
| `rainfall.build.revision_written` | `tasks.py::_persist_analysis_revision` | A `rainfall_analysis_revision` row was written (or would-be-idempotent-no-op) for a fingerprint. **Fires pre-commit**, inside the row's `SAVEPOINT` (decision 2b/2c) — a commit failure AFTER this point still yields this event for work that then rolls back. Bounded: `rainfall.outbox.done` (fired post-commit, above) is the durable signal that the row's work actually landed; do not alert on `revision_written` alone. | `data_revision`, `created` (`true` for a genuinely new row, `false` for `persist_revision`'s own idempotent no-op) |
| `rainfall.build.latched` | `tasks.py::_persist_analysis_revision` | The write gate (`revision_write_decision`) returned `"latched"`: a provisional candidate over an already-served `final` incumbent was refused, unconditionally, under the per-fingerprint advisory lock (design.md "Serializing siblings"). Zero new revision rows. `incumbent_source_id` is read through `served_state()` (R2-002), the same single reader every other consumer of the served envelope uses. | `data_revision`, `source_id` (the refused candidate's), `incumbent_source_id` |
| `rainfall.finalization.gate_refused` | `tasks.py::_persist_analysis_revision` | The write gate returned `"gate_refused"`: a cross-source (finalization) candidate would be `suppressed` under `RAINFALL_METRIC_POLICY` (the SAME function the disclosure path runs). Zero new revision rows; the previously served snapshot is untouched, and the sweep keeps retrying on its normal schedule (not a one-shot refusal). The outbox row is stamped `outcome:gate_refused` (LI2B-003, see §2.2) so the request path can back its own re-enqueue off to a daily cadence instead of retrying a refusal every 10 minutes. | `scope_kind`, `scope_id`, `scope_version`, `year`, `coverage`, `completeness`, `quality_score` (R2-008: flat fields, the same shape `rainfall.finalization.skipped` below uses — was a nested `scope` object) |
| `rainfall.baseline.duplicate_slots` | `tasks.py::_persist_analysis_revision` | LI2B-004: `repository.baseline_cumulatives` refused to answer because ONE baseline year holds two non-superseded rows for one `interval_start` (`DuplicateBaselineSlotError`) — the residue of a correction whose supersession link never landed. The build **degrades instead of dying**: `annual.normal` and `annual.percentile` suppress with reason `baseline_evidence_invalid` (distinct from `baseline_scope_unmapped`, which means the scope has no provider asset at all), and `annual.selected` / `antecedents` / `intensity` still build and land. Before this, the bare `ValueError` aborted the entire build, permanently — a retry cannot un-duplicate persisted data. **When it fires at all**: treat as a data-repair ticket, not a transient. The offending rows are `rainfall_interval_value` under `scope_kind='provider_asset'`, `scope_id=<asset>`, `interval_start` inside `baseline_year`; the fix is the missing `rainfall_interval_lifecycle` supersession row, never a delete (the table is append-only). Until then that scope serves no normal/percentile. | `source_id`, `asset`, `baseline_year` (the duplicated year), `matched_rows`, `distinct_slots`, `scope_kind`, `scope_id`, `scope_version`, `year` (the ANALYSIS year being built) |

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
| Rank suppression | share of served revisions whose `annual.percentile.reason` is `selected_evidence_below_threshold` | Ops.6: the percentile refuses to rank a selected year that is missing days INSIDE its own disclosed comparison window, because the rank sums only the intervals present and places that year in a sample whose baseline years each had to be ~whole to participate. This is **not** a percentile bug — it is an ingest-gap symptom surfacing on the serve path, so correlate it with the §2.2 queue events for the same scope rather than with anything under `annual.normal` (which is a baseline average, ranks nothing, and stays available). Distinguish it from the two baseline reasons (`baseline_scope_unmapped`, `baseline_evidence_invalid`), which are about the 1991–2020 store, and from `coverage_below_threshold`, which speaks for `annual.selected` itself. **When it spikes**: expect a step change when a provider backfills late or a scope's daily ingest has been failing — the accumulated total may still be shown (its own gate is looser), so the percentile disappearing alone is the earliest visible signal that a scope's evidence has holes. |

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