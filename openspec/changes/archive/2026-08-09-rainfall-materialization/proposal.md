# Proposal: Rainfall v2 Materialization

## Intent

Rainfall v2 shipped an API that never produces data. In prod (`main @ c90e795`) `rainfall_analysis_revision` and `rainfall_interval_value` are both empty: the daily role routes to an unimplemented adapter (`sqpe-obs`), `ingest_source_scope` fetches a `SourceBatch` and discards it, and no task ever writes an analysis revision. Staff see a labelled "pending" that cannot resolve, and every view spends Google Earth Engine quota on a result nobody stores.

## Scope

### In Scope

- Persist `SourceBatch` intervals into `rainfall_interval_value`, idempotent via `INSERT .. ON CONFLICT DO NOTHING` on `uq_rainfall_interval_revision`.
- New `build_analysis` task: persisted intervals → `temporal` computations → `normalize_snapshot`-valid envelope → `rainfall_analysis_revision`.
- Add `rainfall_outbox.request_fingerprint` (migration) so compute addresses its snapshot without recomputing an ambiguous key.
- Daily role default `sqpe-obs` → `chirps-v3-sat`, with `TODO(smn)`. Ships **last** in the chain, alone.
- **Current-year re-materialization** (sweep stage 1): a daily `rainfall.revisit_stale` Beat sweep re-enqueues every current-year key that already reached `done`, so the snapshot's `comparison_end` and totals keep advancing instead of freezing at first compute. Completed years are exempt from this freshness refresh. Without this, spec.md:76-81 (same-date comparison for the current year) has no implementation path — the router only enqueues on a snapshot miss (`router.py:130-141`).
- **Year-rollover finalization** (sweep stage 2): a completed year that was materialized while it was still running stays on provisional CHIRPS NRT data **forever** without an explicit transition. The request fingerprint hashes `{scope, year}` only (`service.py:102-107`) — no role, no source — and the router serves any snapshot hit without re-resolving the role, so the "past year → historical role → `chirps-v3-final`" switch never runs for a key that has already materialized. Stage 2 selects completed-year keys by the **served snapshot's own provenance** (`temporal_state` + `provenance.source_id`, `schemas.py:37,39`), re-resolves the work through `resolve_missing_work_source` instead of copying the stale `source_id`, and persists the final revision only when `apply_metric_policy` (`policy.py:148-172`) would call it available — so inadequate final data never replaces a served NRT snapshot. This is what gives spec.md:167 (a later final revision MUST become visible) and spec.md:238 (historical metrics MUST use CHIRPS v3 Final) an implementation path at year scale.
- **NRT correction supersession**: CHIRPS restates recent daily values behind a constant `provider_revision` (`chirps.py:26-29`), which `ON CONFLICT DO NOTHING` on `uq_rainfall_interval_revision` would silently drop. Corrections are appended as a new interval row under a correction-suffixed revision, the superseded row is retained, the link is written to `rainfall_interval_lifecycle` (the first app-code writer of that table), and reads resolve one non-superseded row per slot. This is what gives spec.md:165-181 (provisional → later revision visible) an intra-year path.
- GEE quota guards: chain `build_analysis` to the ingest `done` in the same processing cycle (202→200 within ~1 min); skip re-enqueue in `queue_missing_analysis` when a recent `done` exists for the same key.
- Carry coverage / completeness / quality into the snapshot at compute time for `apply_metric_policy`.
- Fold in: `smn-gauges`→`smn-gauge` typo (`service.py:23` vs `manifests.py:51`); capture the `IntegrityError` race in `queue_missing_analysis`.

### Out of Scope

- SMN NetCDF (`sqpe-obs`) and `sinarame-rqpe` adapters.
- Formal eligibility ladder via `policy.select_source` — needs a `rainfall_source_eligibility` producer and enabled manifests (all 7 are `enabled=False`).
- Intensity/validation role completion; honouring `event_window` interval bounds. Consequence to revisit then: the outbox/cooldown key has no `event_window` component (`models.py:140-148`), so two different event windows for the same zone and year collapse onto one key.
- `rainfall_outbox` retention. The daily sweep appends one `done` row per current-year key per day, plus one per completed-year key whose finalization is still pending; the rows are small and additive, and no purge job exists for that table today.
- A backoff for repeatedly refused finalization attempts. The cost is already bounded at one fetch per key per day and the right constant is a function of CHIRPS v3 Final's publication lag, which is an open question in the design. Every refusal is instrumented so the first real deployment produces the evidence; adding a backoff later is a scheduling change, not a redesign.
- Generalizing the finalization write gate past the v1 metric set. The gate evaluates `annual.selected` because that is the only metric v1 ships; it becomes a per-metric decision when antecedents and intensity land.
- Lifecycle expiry (`event_type='expired'` + `purge_expired_rainfall_intervals`). Supersession writes `event_type='superseded'` with a null `expires_at`, which is deliberately outside the purge path.
- Frontend polling work. RESILIENCE-001 already shipped a bounded 12-poll budget and a terminal `gaveUp` state; only error-path `REREVIEW-001` (WARNING) remains open.
- A batch-level evidence table.

## Scope Decision

- **Mode**: Selective
- **Justification**: Prod is running a feature that promises a result it structurally cannot deliver, so Hold is untenable and Expansion (SMN/radar adapters) buys unvalidated access risk. The core is irreducible — persistence without compute yields no snapshot, compute without persistence has no input, a one-shot materialization freezes the current year on the day it first runs, and the daily fallback alone opens GEE traffic with nothing to store — so the reduction is taken at the edges instead: frontend deferred (already fixed), no new evidence table, ladder deferred. One reduction was considered and **rejected**: dropping the `request_fingerprint` column and recomputing it. Recomputation is exact only while `event_window` is `None`; it would silently produce wrong fingerprints the day the intensity role ships.
- **Scope added after design review** (Judgment Day round 1, JDA-001 / JDA-002): current-year re-materialization and NRT correction supersession. Both were implicit, and both are load-bearing for existing MUSTs rather than new capability — a frozen snapshot violates spec.md:76-81 and a discarded correction leaves spec.md:165-181 with no intra-year path. Deferring them would have shipped a pipeline whose only refresh mechanism is deleting rows by hand, and a correction path that has to be retrofitted onto an append-only table with a live unique constraint. Cost accepted: one more slice in the chain and one full-year zonal fetch per current-year key per day.
- **Scope added after design review** (Judgment Day round 2, JDB-101): year-rollover finalization. The design had claimed the provisional→final transition came free with "the role switch"; that claim was false — the switch only runs on a `get_snapshot` miss, which never happens again once a key has materialized — so completed years would have been served from provisional NRT data permanently. This is not new capability either: it is the implementation path for spec.md:167 and spec.md:238 at year scale, and without it the two existing MUSTs are unmet the first time a year rolls over. Deferring it was rejected because the defect only becomes visible on 1 January, months after the code ships, and by then every completed year is already wrong. Cost accepted: the finalization stage folds into the existing sweep slice (PR 3, ~230 → ~330 lines) and adds one full-year fetch per stalled completed-year key per day until CHIRPS v3 Final publishes adequate data.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `rainfall-analysis`: the daily role selects a documented default source **without** the recorded per-role eligibility outcome that "Source Eligibility Validation Gate" (spec.md:213) requires. Permitted as a `MAY` fallback under "Evidence-Gated Source Roles" (spec.md:238), but the deviation is deliberate and must be stated in the spec delta, not left implicit.

## Approach

Close the pipeline in dependency order behind one tracker branch, opening GEE traffic only once there is somewhere to put the result.

1. **Persistence** — `ingest_source_scope` writes intervals instead of returning counts. Mapping is 1:1 across 9 columns. The write classifies each fetched interval as absent, unchanged or restated, and appends corrections as new rows linked by `rainfall_interval_lifecycle` rather than mutating an append-only table.
2. **Compute** — `build_analysis` reads the persisted, non-superseded intervals, adapts `SourceInterval` → `tuple[datetime, float]` for `temporal`, and writes the revision keyed by the outbox `request_fingerprint`. The revision is content-addressed over the resolved values *and* the disclosed comparison end, so a refresh that moves either writes a new revision and one that moves neither is a no-op.
3. **Refresh and finalize** — `revisit_stale` becomes a daily two-stage sweep. Stage 1 re-enqueues current-year keys; the existing consumer does the rest. Stage 2 re-enqueues completed-year keys whose *served snapshot* is still provisional, with the source and role re-resolved rather than copied, and `build_analysis` persists the final revision only when the display policy would accept it — so the transition can be attempted every day, for as many months as CHIRPS v3 Final needs, without ever downgrading what staff are looking at. Both stages are inert until step 4, because no current-year key can reach `done` while the daily role points at an unimplemented adapter.
4. **Daily fallback** — flip the constant, alone. Traffic opens against a pipeline that already stores what it fetches and already knows how to refresh it.

Batch-level evidence travels **inside the snapshot**, computed at build time from the persisted interval rows. The spec already requires coverage/completeness/quality per metric (spec.md:117), and the snapshot is the immutable revision-addressed disclosure envelope — a fifth evidence table would add a writer with no reader.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `gee-backend/app/domains/geo/rainfall/tasks.py` | Modified | Interval persistence with correction classification; new `build_analysis` including the incumbent-revision read, the finalization write gate and the provisional-over-final latch; chain to `done`; the analysis-clock seam threaded `process_outbox` → `_process_outbox_batch` → `_process_outbox_row` → `build_analysis`; `revisit_stale` reshaped from a per-key passthrough into the two-stage daily sweep |
| `gee-backend/app/domains/geo/rainfall/service.py` | Modified | Daily source constant, `smn-gauge` typo, re-enqueue cooldown, `IntegrityError` capture. `resolve_missing_work_source` gains a second caller (the finalization stage) and stays the single place that maps a `{year}` to a source and role |
| `gee-backend/app/domains/geo/rainfall/repository.py` | Modified | Add write paths (currently read-only), the superseded-row anti-join on reads, and both sweep queries (current-year keys, completed-year provisional keys) |
| `gee-backend/app/core/celery_app.py` | Modified | New `rainfall-revisit-stale` Beat entry (daily 03:30, both sweep stages in one task, `conf.timezone` is `America/Argentina/Cordoba`) |
| `rainfall_interval_lifecycle` table | Behaviour | Gains its first application writer: `event_type='superseded'` rows linking a restated interval to its replacement. No schema change |
| `gee-backend/app/db/migrations/` | New | `rainfall_outbox.request_fingerprint` (nullable) + the done-lookup index |
| `gee-backend/tests/new/` | New | First end-to-end coverage without monkeypatching `ingest_source_scope`, plus supersession, same-key-later-date and year-rollover regressions — including the one that proves a gate-refused finalization attempt does **not** stop the sweep |
| Contract `POST /api/v2/geo/rainfall/analyses` | Behaviour | 202 becomes terminal-resolving; a current-year key keeps returning a *newer* revision day after day; and a key polled after its year completes eventually flips from `temporal_state: "provisional"` / `chirps-v3-sat` to `"final"` / `chirps-v3-final` under the same fingerprint. No schema change; the flip is disclosure the spec already requires (spec.md:117, 167) |
| GEE quota / ops | Modified | Fetch volume shifts from per-poll to per-materialization, plus one full-year zonal fetch per current-year materialized key per day, plus one per completed-year key whose finalization is still pending (drains to zero once CHIRPS v3 Final publishes; the two sweep stages have separate per-run budgets so finalization backlog cannot starve the daily refresh) |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Partial chain reaches prod → GEE burn with no storage | Medium | Tracker branch; only the tracker merges to main; fallback flip ordered last |
| Snapshot fails `normalize_snapshot` → router 503 | Medium | Envelope contract test before the fallback PR lands |
| Re-ingest collides on `uq_rainfall_interval_revision` | High | `ON CONFLICT DO NOTHING` — the collision *is* the intended path for an unchanged slot, since `provider_revision` is constant per adapter. A slot whose value changed does not take that path: it is appended under a correction-suffixed revision and linked as a supersession |
| Test suite green while the real path stays broken | High | At least one test that does **not** monkeypatch `ingest_source_scope` |
| Savepoint illusion in tests hides non-durability | Medium | Cross-session assertions via `SessionLocal()` directly |
| Daily fallback ships without an eligibility record | Accepted | Stated in the spec delta; ladder tracked as follow-up |
| Daily sweep multiplies GEE traffic by the number of current-year keys | Medium | Daily, not hourly; bounded batch; current year only; the sweep is inert until the fallback flip, so the first day of real traffic is a deliberate step |
| Supersession resolves wrongly → an interval counted twice or a correction ignored | High | The anti-join makes one-row-per-slot structural, not conventional; compute raises on a duplicated slot instead of summing; asserted in both the persistence and the compute slice against real PostgreSQL |
| Daily rebuild churns revision rows with no new information | Low | Content address includes the disclosed comparison end and nothing else volatile: a day with neither new data nor a moved comparison end writes nothing at all |
| Finalization self-extinguishes and a completed year stays provisional forever while the audit trail looks complete | High | The termination condition is the **served snapshot's provenance**, never outbox history. A refused attempt leaves a `done` outbox row but no final revision, so the key is still selected tomorrow. An explicit regression test drives two consecutive refusals and asserts the third sweep still enqueues |
| Final data arrives incomplete and replaces a good NRT snapshot with a suppressed null | Medium | The write gate is `apply_metric_policy` itself — the same function the disclosure path runs — so a candidate that would render as suppressed is never persisted. The absolute policy threshold is used rather than "≥ incumbent", because the two revisions' coverage/completeness are ratios over different windows and a relative rule can permanently refuse a strictly better final revision |
| A late `chirps-v3-sat` build shadows an already-finalized year | Medium | Real: a stage-1 row enqueued on 31 December, or a request made minutes before midnight, can drain in January and would otherwise write a newer provisional revision. `build_analysis` latches — a provisional candidate over a final incumbent is never written — and the latch stays active even when the Beat entry is removed |
| Finalization stalls indefinitely because the policy threshold is set too high | Medium | The threshold is an open question with a named owner; every refusal emits coverage/completeness/quality so a stall is visible in the first week rather than discovered a year later. Staff keep seeing the provisional snapshot with its provisional badge, which the spec explicitly permits (spec.md:167) |

## Rollback Plan

- **Narrowest kill switch**: remove the `rainfall-revisit-stale` Beat entry. This stops both sweep stages — the daily refresh and the year-rollover finalization — while leaving request-driven materialization working. The `build_analysis` latch that stops a provisional build shadowing a finalized year is deliberately *not* part of the Beat entry and stays active: pausing the sweep must not re-open the downgrade path.
- **No-deploy kill switch (fastest, whole feature)**: `PUT` `analisis/rainfall_feature_flags` with an all-false blob. This gates ingest and restores today's 202 behaviour without touching code. Note `_role_enabled` returns `True` when the setting is absent (`tasks.py:44-46`), so the blob must be written, not deleted. Gated rows are skipped and retained, and the `pending`-only unique index caps the backlog at one row per key.
- **Code**: revert the single tracker merge commit — one deploy in, one deploy out.
- **Migration**: `request_fingerprint` is nullable and additive; leave it in place on revert. No data loss, no backfill.
- **Data**: persisted intervals and revisions are additive evidence rows and are safe to leave. If a bad snapshot must be withdrawn, delete the affected `rainfall_analysis_revision` rows; the next request re-queues.

## Dependencies

- Post-deploy ops: `DELETE` the failed `sqpe-obs` outbox rows. Re-enqueueing them as `pending` would violate `ix_rainfall_outbox_pending_unique`, and there is no requeue helper.
- Live GEE credentials and quota headroom for the first real materialization run.
- `consorcio-celery-beat` is Docker-unhealthy while still dispatching — investigate separately; it does not block this change. It does become more load-bearing: both sweep stages are one Beat entry, so a genuinely dead Beat degrades the current year back to a frozen snapshot **and** leaves completed years stuck on provisional data. Both degradations are visible rather than silent — the served comparison end stops advancing, and the served `temporal_state` stays `provisional` past year end.

## Success Criteria

- [ ] A `POST /api/v2/geo/rainfall/analyses` for a supported zone/year returns 202 and then 200 with a snapshot within one processing cycle.
- [ ] `rainfall_interval_value` and `rainfall_analysis_revision` are non-empty in prod for both the historical and daily roles.
- [ ] Re-running the same ingest twice adds no duplicate interval rows and raises no `IntegrityError`.
- [ ] A repeated poll for an already-materialized key triggers no new GEE fetch; the only scheduled fetches for that key are the daily refresh while its year is current, and — at most one per day, until it succeeds — the year-rollover finalization once the year has completed.
- [ ] At least one integration test drives POST → outbox → GET 200 without monkeypatching `ingest_source_scope`.
- [ ] Every snapshot metric carries coverage, completeness, and quality, and `apply_metric_policy` reads them from the snapshot.
- [ ] Polling the same current-year key on a later day returns a snapshot with a later comparison end, backed by a new revision row, with the earlier revision retained.
- [ ] A re-fetch that restates one day's value stores the correction, keeps the superseded row, writes the lifecycle link, and moves the annual total by the delta — never by the sum. An unchanged re-fetch writes nothing.
- [ ] Polling a key materialized during its calendar year, after that year has completed and adequate CHIRPS v3 Final data exists, returns a snapshot whose `temporal_state` is `final` and whose `provenance.source_id` is `chirps-v3-final`, under the same request fingerprint, with the provisional revision retained.
- [ ] A finalization attempt whose final-source data would be suppressed by the metric policy writes no revision, leaves the provisional snapshot served, and is re-attempted by the next sweep — proven by a test that refuses twice and still enqueues a third time.
- [ ] Once an adequate final revision is served for a completed-year key, the sweep enqueues nothing further for it and spends no further provider fetch on it.
- [ ] A `chirps-v3-sat` build processed after a final revision is already served for the same fingerprint writes no revision.
