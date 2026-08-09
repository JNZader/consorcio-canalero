# Tasks: Rainfall v2 Materialization

## Review Workload Forecast

Note: design.md's PR table (lines 390-393, verified against the artifact read for
this task breakdown) states **~260/~360/~360/~40**, not the ~200/~330/~360/~40 figures
cached at session start — PR1 and PR3 grew during the JDA-201/JDB-201 post-judgment
amendment (advisory-lock plumbing + the two-connection concurrent-latch test). The
table below uses the verified, current design.md numbers.

| Field | Value |
|-------|-------|
| Estimated changed lines | PR1 ~260, PR2 ~360, PR3 ~360, PR4 ~40 (design.md:390-393, post-amendment) |
| 400-line budget risk | Low (largest slices ~360, each independently verifiable) |
| Chained PRs recommended | Yes |
| Suggested split | PR1 persistence → PR2 compute → PR3 revisit+finalization+guards → PR4 daily-source flip |
| Delivery strategy | auto-chain |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Interval persistence + NRT correction supersession | PR 1 | Base = tracker `feat/rainfall-materialization`. ~260 lines |
| 2 | `build_analysis` materialization + fingerprint plumbing + per-row commit | PR 2 | Base = PR 1 branch. ~360 lines |
| 3 | Daily revisit sweep (stage 1) + year-rollover finalization (stage 2) + advisory-lock guards | PR 3 | Base = PR 2 branch. ~360 lines. Inert until PR 4 |
| 4 | Daily-source flip (opens GEE traffic) | PR 4 | Base = PR 3 branch. ~40 lines, ships alone and last |

Only the tracker branch merges to `main` (single prod deploy). TDD note: for every
task below, the named test is written and run RED against the listed source files
before those files are changed to make it pass.

## Phase 1 (PR 1) — Persistence

- [x] 1.1 Re-running an identical `ingest_source_scope` twice adds no duplicate `rainfall_interval_value` rows and raises nothing. Test: `gee-backend/tests/new/geo/rainfall/test_rainfall_materialization.py::test_reingest_is_idempotent`. Files: `gee-backend/app/domains/geo/rainfall/repository.py`.
- [x] 1.2 Create `compute.py` with pure `revision_family(provider_revision) -> str` and `correction_revision(family, ordinal) -> str`; round-trip verified (`"v3-nrt+r2"` ↔ `("v3-nrt", 2)`). Test: `gee-backend/tests/test_mutation_targets_rainfall.py::test_revision_family_and_correction_revision_roundtrip`. Files: `gee-backend/app/domains/geo/rainfall/compute.py` (create).
- [x] 1.3 `persist_intervals` classifies an absent slot as an INSERT carrying the family revision, via `on_conflict_do_nothing(constraint="uq_rainfall_interval_revision").returning(id)`. Test: `test_rainfall_materialization.py::test_persist_intervals_inserts_absent_slot`. Files: `gee-backend/app/domains/geo/rainfall/repository.py`.
- [x] 1.4 A slot re-fetched with a value equal at 6 decimal places (`round(new,6)==round(current,6)`) is a no-op: no new interval row, no lifecycle row. Test: `test_rainfall_materialization.py::test_persist_intervals_unchanged_slot_writes_nothing` (real PG) + `test_mutation_targets_rainfall.py::test_six_decimal_equality_boundary` (pure boundary case). Files: `gee-backend/app/domains/geo/rainfall/repository.py`.
- [x] 1.5 A slot re-fetched with a changed value is INSERTed as a `family+rN` row, and `record_supersession` writes the matching `rainfall_interval_lifecycle` row (`event_type="superseded"`) only for the ids `RETURNING` reports as landed. Test: `test_rainfall_materialization.py::test_persist_intervals_changed_slot_appends_correction_and_lifecycle_row`. Files: `gee-backend/app/domains/geo/rainfall/repository.py`.
- [x] 1.6 A second correction of the same slot chains `+r2` off `+r1` (ordinal = current row's ordinal + 1). Test: `test_rainfall_materialization.py::test_second_correction_chains_off_first`. Files: `gee-backend/app/domains/geo/rainfall/repository.py`.
- [x] 1.7 `intervals_in_window` anti-joins `rainfall_interval_lifecycle` (`event_type='superseded'`) and returns at most one non-superseded row per slot, ordered by `interval_start`. Test: `test_rainfall_materialization.py::test_intervals_in_window_excludes_superseded_rows`. Files: `gee-backend/app/domains/geo/rainfall/repository.py`.
- [x] 1.8 `ingest_source_scope(*, ..., db: Session | None = None)`: given a `db`, writes via `persist_intervals` without committing; given `None`, opens its own `SessionLocal()` and commits. The existing no-`db` contract test (`test_provider_adapters.py:436-456`) stays green unmodified. Test: `test_rainfall_materialization.py::test_ingest_source_scope_writes_without_commit_when_given_db`. Files: `gee-backend/app/domains/geo/rainfall/tasks.py`.
- [x] 1.9 `backfill_missing` passes its own open `db` into `ingest_source_scope(db=db, ...)` so the checkpoint write and interval persistence share one transaction. Test: `test_rainfall_materialization.py::test_backfill_missing_shares_transaction_with_ingest`. Files: `gee-backend/app/domains/geo/rainfall/tasks.py`.

## Phase 2 (PR 2) — Compute

- [x] 2.1 Migration `lluvia_v2_005` adds nullable `rainfall_outbox.request_fingerprint` (`String(128)`) plus a non-unique index on the outbox key + `completed_at` (decision 6); `down_revision="lluvia_v2_004"`. Verify manually: `alembic upgrade head && alembic downgrade -1 && alembic upgrade head` against a scratch database (no test in `conftest.py` exercises the migration path — `Base.metadata.create_all` bypasses it). Files: `gee-backend/app/db/migrations/versions/lluvia_v2_005_rainfall_outbox_request_fingerprint.py` (create).
- [x] 2.2 `RainfallOutbox.request_fingerprint: Mapped[str | None]` matches the migration column. Test: `test_rainfall_materialization.py::test_outbox_model_has_request_fingerprint_column`. Files: `gee-backend/app/domains/geo/rainfall/models.py`.
- [x] 2.3 `router.py` passes its already-computed `analysis_request_fingerprint(request)` into `queue_missing_analysis`; `service.queue_missing_analysis` accepts and stores it on enqueue instead of recomputing (removes the `exclude_none` drift class, decision 4). Test: `test_rainfall_materialization.py::test_queue_missing_analysis_stores_router_computed_fingerprint`. Files: `gee-backend/app/domains/geo/rainfall/router.py`, `gee-backend/app/domains/geo/rainfall/service.py`.
- [x] 2.4 `compute.build_snapshot(...)` builds an envelope whose root keys are a subset of `SNAPSHOT_ROOT_KEYS`, ships only `annual.selected` (decision 5), and each `MetricResult` carries the full `extra="forbid"` field set with `quality["score"]` in `[0,1]` (decision 5b). Test: `test_mutation_targets_rainfall.py::test_build_snapshot_envelope_contract`. Files: `gee-backend/app/domains/geo/rainfall/compute.py`.
- [x] 2.5 `build_snapshot` recomputes coverage/completeness/quality over `[year_start, min(comparison_end, last_interval_end))`, not the raw fetch window (decision 5c) — this is the snapshot-evidence-at-build-time requirement. Test: `test_mutation_targets_rainfall.py::test_build_snapshot_bounds_coverage_window_to_available_through`. Files: `gee-backend/app/domains/geo/rainfall/compute.py`.
- [x] 2.6 `compute.data_revision_for(...)` is a sha256 over `[source_id, provider_revision_family, scope, year, comparison_end, [(iso, round(v,6))…]]`: stable when neither the resolved intervals nor `comparison_end` move, and changes when `comparison_end` advances alone (decision 3b). Test: `test_mutation_targets_rainfall.py::test_data_revision_for_stability_and_advance`. Files: `gee-backend/app/domains/geo/rainfall/compute.py`.
- [x] 2.7 `build_snapshot` raises on a repeated `interval_start` instead of summing it. Test: `test_mutation_targets_rainfall.py::test_build_snapshot_raises_on_duplicate_interval_start`. Files: `gee-backend/app/domains/geo/rainfall/compute.py`.
- [x] 2.8 `policy.py` gains `RAINFALL_METRIC_POLICY` + `RAINFALL_METRIC_POLICY_REVISION` module constants (0.8/0.8 starting thresholds, pending the domain lead's number per Open Questions), embedded in every snapshot and mirrored into the revision's `policy_revision` column (decision 5d). Test: `test_mutation_targets_rainfall.py::test_rainfall_metric_policy_constants_shape`. Files: `gee-backend/app/domains/geo/rainfall/policy.py`.
- [x] 2.9 `repository.persist_revision(...)` uses `on_conflict_do_nothing(constraint="uq_rainfall_analysis_snapshot")` then `SELECT`, so an identical `data_revision` is a no-op returning the existing id. Test: `test_rainfall_materialization.py::test_persist_revision_is_idempotent_on_identical_data_revision`. Files: `gee-backend/app/domains/geo/rainfall/repository.py`.
- [x] 2.10 `build_analysis(*, outbox_id, batch, db=None, now=None)` reads persisted non-superseded intervals via `intervals_in_window`, builds and persists exactly one `rainfall_analysis_revision` keyed by the outbox row's `request_fingerprint`, and the written snapshot passes `normalize_snapshot` (contract gate — must land before PR 4). Test: `test_rainfall_materialization.py::test_build_analysis_writes_one_revision_and_passes_normalize_snapshot`. Files: `gee-backend/app/domains/geo/rainfall/tasks.py`.
- [x] 2.11 `build_analysis` is chained inside `_process_outbox_row` before `status="done"` (decision 1); a `done` row whose `interval_start`/`interval_end` are the year bounds derives the full-year fingerprint when it is null, otherwise skips compute, stays `done`, and emits `rainfall.compute.skipped{reason:"fingerprint_unavailable"}` (decision 4b). Test: `test_rainfall_materialization.py::test_process_outbox_row_chains_build_analysis_before_done` and `::test_legacy_null_fingerprint_row_skips_compute`. Files: `gee-backend/app/domains/geo/rainfall/tasks.py`.
- [x] 2.12 Per-row commit: `repository.claim_outbox_row` re-claims `WHERE id=:id AND status='pending' AND next_attempt_at<=now() FOR UPDATE SKIP LOCKED` (`None` ⇒ another worker owns it, skip); each row's work runs inside `db.begin_nested()` (decision 2b) and is committed individually (decision 2c). Decision 1b's invariant — `done` ⇒ `get_snapshot(row.request_fingerprint)` is non-`None` — holds at the fingerprint level, and a row that fails after another succeeded leaves the succeeded row already committed. Test: `test_rainfall_materialization.py::test_per_row_commit_survives_a_later_row_failure`. Files: `gee-backend/app/domains/geo/rainfall/repository.py`, `gee-backend/app/domains/geo/rainfall/tasks.py`.
- [x] 2.13 Thread `now: datetime | None = None` through `process_outbox` → `_process_outbox_batch` (resolved once per batch) → `_process_outbox_row` → `build_analysis`; `completed_at`/`next_attempt_at`/backoff arithmetic stay on the real wall clock, never on the seam. Test: `test_rainfall_materialization.py::test_now_seam_drives_comparison_end_without_moving_backoff_clock`. Files: `gee-backend/app/domains/geo/rainfall/tasks.py`.
- [x] 2.14 E2E: `POST /api/v2/geo/rainfall/analyses` → 202 → `process_outbox(db)` → `POST` again → 200 with the normalized snapshot, without monkeypatching `ingest_source_scope`. Test: `test_rainfall_materialization.py::test_e2e_post_202_then_200_without_monkeypatching_ingest`. Files: none (integration wiring only, verifies PR 1 + PR 2 together).

## Phase 3 (PR 3) — Revisit, Finalization, Guards

- [x] 3.1 `repository.recent_done` seeks the decision-6 done-lookup index; `queue_missing_analysis` skips re-enqueue when a `done` row for the same key has `completed_at` within `RAINFALL_RECOMPUTE_COOLDOWN` (10 min), regardless of whether a revision exists, returning the same 202 body + a `rainfall.outbox.cooldown` event. Test: `test_rainfall_materialization.py::test_repeated_post_skips_reenqueue_after_recent_done`. Files: `gee-backend/app/domains/geo/rainfall/repository.py`, `gee-backend/app/domains/geo/rainfall/service.py`.
- [x] 3.2 `compute.fingerprint_lock_key(request_fingerprint)` derives a deterministic signed 64-bit int from the fingerprint's first 16 hex chars (unsigned big-endian → signed bigint wraparound), and `repository.acquire_fingerprint_lock(db, lock_key=...)` issues `SELECT pg_advisory_xact_lock(:lock_key)`. Test: `test_mutation_targets_rainfall.py::TestFingerprintLockKey` (4 tests). Files: `gee-backend/app/domains/geo/rainfall/compute.py`, `gee-backend/app/domains/geo/rainfall/repository.py`.
- [x] 3.3 `build_analysis` takes the advisory lock as its **first** database statement, inside the per-row transaction of decision 2c, before the incumbent `get_snapshot` read. Test: `test_rainfall_materialization.py::test_build_analysis_locks_before_incumbent_read`. Files: `gee-backend/app/domains/geo/rainfall/tasks.py`.
- [x] 3.4 `compute.served_state(snapshot)` reads `(annual.selected.provenance.source_id, annual.selected.temporal_state)` from a complete envelope and returns `None` when either is missing. Test: `test_mutation_targets_rainfall.py::TestServedState` (4 tests). Files: `gee-backend/app/domains/geo/rainfall/compute.py`.
- [x] 3.5 `compute.revision_write_decision(incumbent, candidate, policy)` covers every branch: no/unreadable incumbent or same `source_id` → `"write"`; cross-source, candidate provisional over incumbent final → `"latched"`; cross-source otherwise → `"write"` iff `apply_metric_policy(...).state=="available"` else `"gate_refused"` — including the coverage-equals-threshold boundary (`policy.py:166` is `<`, so equality passes). Test: `test_mutation_targets_rainfall.py::TestRevisionWriteDecision` (10 tests). Files: `gee-backend/app/domains/geo/rainfall/compute.py`.
- [x] 3.6 `build_analysis` applies `revision_write_decision` before any INSERT: a `gate_refused` build writes zero revision rows and leaves the previously served snapshot untouched. Test: `test_rainfall_materialization.py::test_write_gate_refuses_suppressed_candidate_without_touching_served_snapshot`. Files: `gee-backend/app/domains/geo/rainfall/tasks.py`.
- [x] 3.7 Latch regression, sequential and concurrent: a `chirps-v3-sat` build over an already-served final revision writes nothing; and, on **two independent `SessionLocal()` connections**, a daily-role sibling `build_analysis` blocks on the advisory lock until a historical-role sibling for the same fingerprint commits, then re-reads a fresh incumbent and returns `latched` in both claim orders. Test: `test_rainfall_materialization.py::test_latch_sequential_and_concurrent_two_connections`. Files: none (verifies 3.3/3.5/3.6 under concurrency).
- [x] 3.8 `service.resolve_missing_work_source(event_window, year, *, requested_role=None, now: datetime | None = None)` feeds `now` into exactly the `year == now.year` routing test; `queue_missing_analysis` leaves `now` unset so the request path stays on the real clock. Test: `test_mutation_targets_rainfall.py::TestResolveMissingWorkSourceNowSeam` (3 tests). Files: `gee-backend/app/domains/geo/rainfall/service.py`.
- [x] 3.9 `repository.current_year_done_keys(db, *, year, limit)` returns `DISTINCT ON` the outbox key, newest `done` row per key, for sweep stage 1. Test: `test_rainfall_materialization.py::test_current_year_done_keys_distinct_on_key`. Files: `gee-backend/app/domains/geo/rainfall/repository.py`.
- [x] 3.10 `revisit_stale` stage 1: for each current-year `done` key, INSERT a fresh `pending` row copying key, `work_labels`, interval bounds and `request_fingerprint`; skip (with `rainfall.revisit.skipped`) a key with a `pending` row in flight or a NULL fingerprint. Test: `test_rainfall_materialization.py::test_revisit_stage1_enqueues_fresh_pending_row_per_current_year_key`. Files: `gee-backend/app/domains/geo/rainfall/tasks.py`.
- [x] 3.11 Stage 1 dedup and year filter: running the sweep twice on one key still leaves exactly one fresh pending row (`pending_in_flight`); a past-year `done` key produces zero rows from stage 1. Test: `test_rainfall_materialization.py::test_revisit_stage1_dedups_and_exempts_past_years`. Files: `gee-backend/app/domains/geo/rainfall/tasks.py`.
- [x] 3.12 E2E — same key, later date (JDA-001 regression): POST → 202 → `process_outbox(db)` → 200 with `comparison_end==D` (revision R1); extend the fake series by a day, run `revisit_stale(db, now=D+1)` + `process_outbox(db, now=D+1)`, POST the same payload again → 200 with `comparison_end==D+1`, two revisions retained under one `request_fingerprint`, newer served; repeat with an unchanged series and confirm a new revision is still written because `comparison_end` is in the address. This also proves a supersession correction becomes a later served revision (decision 3c's visibility scenario). Test: `test_rainfall_materialization.py::test_e2e_same_key_later_date_and_corrected_revision_becomes_visible`. Files: none (verifies 1.5 + 2.10 + 3.10 together).
- [x] 3.13 `repository.completed_year_daily_done_keys(db, *, before_year, limit)`: `status='done' AND role='daily' AND year<:before_year AND request_fingerprint IS NOT NULL`, `DISTINCT ON` scope+year — a superset, never the termination condition. Test: `test_rainfall_materialization.py::test_completed_year_daily_done_keys_is_a_superset`. Files: `gee-backend/app/domains/geo/rainfall/repository.py`.
- [x] 3.14 `revisit_stale` stage 2: terminate (enqueue nothing) a key whose served snapshot already reports `("chirps-v3-final","final")`; otherwise re-resolve source/role via `resolve_missing_work_source(None, year, now=now)` and enqueue a `pending` row with the source/role re-resolved but `request_fingerprint` copied verbatim; skip a pending-in-flight key, a historical-role key, and a NULL-fingerprint key with their matching skip events; at most one work item and one fetch per key per run. Test: `test_rainfall_materialization.py::test_revisit_stage2_reresolves_source_and_terminates_on_final`. Files: `gee-backend/app/domains/geo/rainfall/tasks.py`.
- [x] 3.15 Self-extinguishing regression (JDB-101 — the test that must not be dropped): an inadequate final series is refused twice in a row (0 revisions each time, provisional snapshot still served, sweep still enqueues on both following runs); an adequate series is then supplied and the *next* sweep after that enqueues zero. Test: `test_rainfall_materialization.py::test_finalization_is_retried_not_abandoned_then_terminates`. Files: none (verifies 3.5/3.6/3.14 together).
- [x] 3.16 E2E — year rollover (JDB-101 regression at the API boundary): POST year Y while current → 200 provisional/`chirps-v3-sat`; move the seam to January of Y+1 with an adequate final series, run `revisit_stale(db, now=…)` + `process_outbox(db, now=…)`, POST the same payload again → 200 final/`chirps-v3-final`, both revisions retained, same `request_fingerprint`. Test: `test_rainfall_materialization.py::test_e2e_year_rollover_transitions_to_final`. Files: none (verifies 3.8 + 3.14 together).
- [x] 3.17 Add the `rainfall-revisit-stale` Beat entry: `crontab(minute="30", hour="3")`, queue `celery`, next to `rainfall-process-outbox` (`conf.timezone="America/Argentina/Cordoba"`). Test: `test_rainfall_materialization.py::test_revisit_stale_beat_entry_is_registered`. Files: `gee-backend/app/core/celery_app.py`.
- [x] 3.18 Small fixes: `RAINFALL_VALIDATION_SOURCE="smn-gauge"` (`service.py`) matches the manifest; `queue_missing_analysis` catches `IntegrityError` → `db.rollback()` → re-`SELECT pending` → returns the reuse payload, so two identical concurrent POSTs both get 202. Test: `test_rainfall_materialization.py::test_validation_source_matches_manifest` and `::test_concurrent_identical_post_does_not_surface_500`. Files: `gee-backend/app/domains/geo/rainfall/service.py`.
- [ ] 3.19 Register `compute.py` in the rainfall block of `.cosmic-ray.toml`, kept commented/unmeasured (repo rule: no threshold gate without a measured run — blocked on the same Python-3.11 cosmic-ray availability gap already tracked for `policy.py`/`service.py`/`temporal.py`; no new numeric threshold is invented here). Files: `gee-backend/.cosmic-ray.toml`.

## Phase 4 (PR 4) — Daily-Source Flip

- [ ] 4.1 `RAINFALL_DAILY_SOURCE` flips `"sqpe-obs"` → `"chirps-v3-sat"` with a `TODO(smn)` comment; provenance sets `fallback_used=True` for any role whose spec-primary source differs from the one actually used (documents the "Daily role uses the documented default" spec scenario as a deliberate, tracked deviation). Test: `test_rainfall_materialization.py::test_daily_source_flips_to_chirps_v3_sat_with_fallback_flag`. Files: `gee-backend/app/domains/geo/rainfall/service.py`.
- [ ] 4.2 First real current-year materialization: with the flip live, a current-year key reaches `done` (no longer blocked by the unwired `sqpe-obs` adapter) and the stage-1 daily sweep starts finding keys. Test: `test_rainfall_materialization.py::test_current_year_key_reaches_done_after_flip_and_sweep_finds_it`. Files: none (verifies PR 1-3 under the flipped constant).

## Phase 5 — Ops / Rollout (non-code)

- [ ] 5.1 Post-deploy: `DELETE` the 2 failed `sqpe-obs` outbox rows in prod (re-enqueueing them as `pending` would violate `ix_rainfall_outbox_pending_unique`; no requeue helper exists).
- [ ] 5.2 Write the ops runbook note for the two-tier kill switch: removing the `rainfall-revisit-stale` Beat entry stops both sweep stages (the `build_analysis` latch stays active — pausing the sweep must not re-open the shadowing path); writing an all-`false` `analisis/rainfall_feature_flags` blob is the no-deploy whole-feature switch (must be written, not deleted — absent reads as enabled).
- [ ] 5.3 Staging validation of the `comparison_end`-vs-provider-lag semantics (Open Question, decided-with-deferral): before the prod cutover, validate with the partner that calendar `comparison_end` + `available_through` disclosure reads correctly and is not mistaken for a claim about measured data.

## Coverage: Spec Scenario → Task

| Requirement | Scenario | Task(s) |
|---|---|---|
| Interval Persistence on Ingest | Ingest persists fetched intervals | 1.3, 1.8 |
| | Re-ingest is idempotent | 1.1 |
| Analysis Materialization and Chained Resolution | Ingest done triggers materialization within one cycle | 2.10, 2.11 |
| | Invalid snapshot preserves the existing failure contract | 2.10 (contract gate); pre-existing router 503 path stays covered by `test_backend_api.py`, unmodified |
| Current-Year Re-materialization Cadence | Current-year snapshot refreshed next day | 3.12 |
| | Newly published days enter refreshed snapshot | 3.12 |
| | Completed year not refreshed for freshness | 3.11 |
| | In-flight refresh not duplicated | 3.11 |
| Year-Rollover Finalization | Transition enqueued after year completes | 3.14 |
| | Final revision becomes served answer | 3.14, 3.16 |
| | Inadequate final data does not replace served snapshot | 3.15 |
| | Refused transition retried, not abandoned | 3.15 |
| | Adequate final revision terminates sweep | 3.14, 3.15 |
| | Late provisional build does not shadow finalized year | 3.7 |
| | Pending transition bounded to one fetch per run | 3.14 |
| Provider Correction Supersession Within a Revision | Restated value stored without losing original | 1.5 |
| | Supersession recorded as evidence | 1.5 |
| | Computation resolves one value per interval | 1.7, 2.7 |
| | Unchanged re-fetch writes nothing | 1.4 |
| | Corrected value becomes visible as a later revision | 3.12 |
| GEE Quota Guards on Request-Path Re-enqueue and Poll | Repeated POST skips re-enqueue after recent done | 3.1 |
| | Scheduled sweep not bound by request-path cooldown | 3.1, 3.10, 3.14 |
| | Repeated poll serves stored revision | pre-existing `get_snapshot` hit path, reinforced by 3.1 |
| Snapshot Evidence Computed at Build Time | Metric evidence reflects persisted rows | 2.5 |
| Operational Robustness of the Materialization Path | Validation identifier matches manifest | 3.18 |
| | Concurrent identical POST does not surface a 500 | 3.18 |
| Evidence-Gated Source Roles (MODIFIED) | Validated CHIRPS v3 Final / operational-candidate / radar-unavailable scenarios | pre-existing behavior, unchanged by this design; no task |
| | Daily role uses the documented default ahead of eligibility record | 4.1 |

## Mutation Targets (per module)

| Module | Target tests | Threshold status |
|---|---|---|
| `compute.py` (new) | `test_mutation_targets_rainfall.py` — revision family/ordinal parsing, 6-dp equality, disclosure-window hashing, duplicate-slot raise, `served_state` disclosure/absence, every `revision_write_decision` branch, `fingerprint_lock_key` wraparound | Registered in `.cosmic-ray.toml` (task 3.19), kept commented/unmeasured — repo rule, no threshold without a measured run |
| `service.py` | `test_mutation_targets_rainfall.py` — `resolve_missing_work_source` routing on both sides of a year boundary under an injected `now` | Pre-existing commented target; unchanged, still blocked on the Python 3.11 cosmic-ray measurement gap |
| `policy.py`, `temporal.py` | Existing `test_mutation_targets_rainfall.py` cases (71, unaffected) | Pre-existing commented targets; unaffected by this change |
