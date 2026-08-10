# Tasks: Lluvia Insights — Rainfall v2 Product Layer

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | ~1630 total (1: 380, 2a: 240, 2b: 210, 3a: 240, 3b: 210, 4: 350) |
| 400-line budget risk | Medium (each slice designed ≤400; test-file overhead could push an estimate) |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2a → PR 2b → PR 3a → PR 3b → PR 4 |
| Delivery strategy | auto-chain |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: Medium

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|---|---|---|---|
| 1 | Provider-asset baseline key (D1) + backfill orchestrator/CLI, `(AdapterError, CircuitOpen)` stop (D2) | PR 1 | base = `feat/lluvia-insights` (tracker); merge → manual 1991 dry-run → full backfill (Ops.1-3) |
| 2a | `annual.normal`/`percentile`/antecedents metrics + 4 thresholds (D4 rows, D5, D6) | PR 2a | base = PR 1 branch; empty baseline suppresses safely, never wrong numbers |
| 2b | disclosure-time `summary` + revision bump + cross-source caveat + stale requeue (D3, D4, D5) | PR 2b | base = PR 2a branch; revision bump lands the enriched envelope |
| 3a | series module + consistency pin + `data_revision` exposure (D3) | PR 3a | base = PR 2b branch |
| 3b | xlsx export + TS series/xlsx contract (D7) | PR 3b | base = PR 3a branch; audit CSV byte regression required |
| 4 | frontend chart + campaign preset + staleness UI (D8) | PR 4 | base = PR 3b branch; droppable last — server-side flag stays authoritative without it |

Only the tracker (`feat/lluvia-insights`) merges to `main`.

## Slice 1: Historical Baseline Backfill (D1, D2)

- [x] 1.1 RED `gee-backend/tests/new/geo/rainfall/test_rainfall_baseline.py::test_provider_asset_scope_key_persists_and_reads_back` — persist intervals under `scope_kind="provider_asset", scope_id="zona_cc_ampliada", scope_version="v1"`, assert readback. Files: new test file.
- [x] 1.2 GREEN `adapters/gee_client.py::asset_name_for` — add `scope_kind == "provider_asset"` branch returning `scope_id` unchanged; export `BASELINE_ASSET_VERSION = "v1"`. Makes 1.1 pass.
- [x] 1.3 RED `test_rainfall_baseline.py::test_baseline_cumulatives_returns_per_year_totals` — 3 baseline years persisted for one asset; `repository.baseline_cumulatives(db, source_id=..., asset=..., dates=[...])` returns `{year: (total_mm, matched_days, expected_days)}` matching a manual SQL sum.
- [x] 1.4 GREEN `repository.py::baseline_cumulatives` — SQL window `SUM` per baseline year, anti-joined on supersession (pattern of `intervals_in_window`, `repository.py:213-246`).
- [x] 1.5 RED `test_rainfall_baseline.py::test_zoning_republication_does_not_orphan_baseline` — bump a zone `scope_version`; `baseline_cumulatives` for the unchanged asset still returns the same rows.
- [x] 1.6 GREEN — assert-only: the asset key never includes `scope_version` (1.2/1.4); confirm 1.5 passes with no further code.
- [x] 1.7 RED `test_rainfall_baseline.py::test_unmapped_basin_raises_unknown_provider_scope` — a basin id absent from `BASIN_ASSET_NAMES` raises `UnknownProviderScope` when the baseline asset is resolved.
- [x] 1.8 GREEN `tasks.py::_persist_analysis_revision` — catch `UnknownProviderScope`, pass `baseline=None` to `build_snapshot` (full suppression wiring completes in 2a.7). Deviation: also proven for the MAPPED-scope happy path (`test_persist_analysis_revision_resolves_mapped_baseline_and_passes_it_through`, RED-then-GREEN verified), beyond the unmapped-basin case the task literally names — see apply-progress.
- [x] 1.9 RED `gee-backend/tests/new/geo/rainfall/test_rainfall_backfill.py::test_backfill_dedupes_shared_asset_one_fetch_per_year` — two zone scopes sharing one asset; the provider is fetched once per year (30 total), not per scope.
- [x] 1.10 GREEN `tasks.py::backfill_baseline_range(asset, years=range(1991, 2021))` — loop years, reuse `backfill_missing` verbatim per key (`tasks.py:947-972`), sleep `RAINFALL_BACKFILL_PACE_SECONDS` (default 5s), `record_event("rainfall.backfill.year", ...)`.
- [x] 1.11 RED `test_rainfall_backfill.py::test_backfill_resumes_after_interruption_no_refetch` — checkpoint stops at year N; rerun starts at N+1, 0 provider calls for years ≤N.
- [x] 1.12 GREEN — assert-only against 1.10's inherited `already_complete` short-circuit; no new code.
- [x] 1.13 RED `test_rainfall_backfill.py::test_backfill_stops_labelled_on_circuit_open` — `FakeGeeClient` forcing a pre-opened Redis circuit for role `historical` yields `{"stopped": True, "reason": "circuit_open"}`, no traceback, no further provider call. Deviation: implemented as a drop-in fake `CircuitStore` (`RedisCircuitStore` monkeypatched at its class seam, `test_resilience.py`'s pattern) rather than a `FakeGeeClient` — `can_attempt()` raises before any adapter/`ee` call is ever reached, so GEE is equally untouched; see apply-progress.
- [x] 1.14 RED `test_rainfall_backfill.py::test_backfill_stops_labelled_on_adapter_error` — same shape, `reason: "adapter_error"`.
- [x] 1.15 GREEN `tasks.py::backfill_baseline_range` — wrap the per-year ingest in `except (AdapterError, CircuitOpen):`, `record_event("rainfall.backfill.stopped", reason=...)`, return the stop result instead of raising. Makes 1.13/1.14 pass.
- [x] 1.16 Create `backfill_cli.py` — `__main__` one-shot runner calling `backfill_baseline_range(DEFAULT_ZONE_ASSET)`; `--help` states the ~300s recovery-window wait-out rule (D2).
- [x] 1.17 Confirm no new pure-logic module is wired uncommented into `.cosmic-ray.toml:78-90` — `baseline_cumulatives` is SQL, out of the pure-target set.

## Slice 2a: Metric Core — Normal, Percentile, Antecedents, Thresholds (D4 rows, D5, D6, LIB-102 fold)

- [ ] 2a.1 RED `gee-backend/tests/test_mutation_targets_rainfall.py::test_weibull_percentile_rank_and_ties` — `p = 100*i/(N+1)` over baseline+selected (N=n+1), ties take mean position; range 3.1–96.9 at n=30.
- [ ] 2a.2 GREEN `compute.py::weibull_percentile` (pure) + `MIN_BASELINE_YEARS = 20`.
- [ ] 2a.3 RED `test_mutation_targets_rainfall.py::test_percentile_suppressed_below_min_baseline_years` — 19 eligible years suppresses `reason="baseline_years_below_minimum"`; 20 does not.
- [ ] 2a.4 RED `test_mutation_targets_rainfall.py::test_percentile_suppressed_feb29_small_sample` — Feb-29, 8 leap-year baseline sample, suppressed same reason (spec: "February 29 rank on a small sample").
- [ ] 2a.5 GREEN — per-year day-completeness filter (<0.95 drops the year) + the two-layer suppression in `compute.py`'s normal/percentile builder. Makes 2a.3/2a.4 pass.
- [ ] 2a.6 RED `test_mutation_targets_rainfall.py::test_annual_normal_and_percentile_envelope_shape` — `provenance.source_id="chirps-v3-final"`, `unit="percentil"` (not `"%"`), `interval_*` = baseline envelope (1991-01-01 → last baseline comparison_end+1d).
- [ ] 2a.7 GREEN `compute.py::build_snapshot` — add `annual.normal`/`annual.percentile` from the `baseline_cumulatives` dict (slice 1); `baseline=None` → both suppress `reason="baseline_scope_unmapped"` (completes 1.8's wiring).
- [ ] 2a.8 Add an inline note beside the `Provenance(...)` construction in 2a.7: `Provenance`/`MetricResult` both set `extra="forbid"` (`schemas.py:11,25`) — baseline metrics build a complete field set from scratch (no adapter batch to inherit from), never ad hoc extras. LIB-102 fold, code comment only.
- [ ] 2a.9 RED `test_mutation_targets_rainfall.py::test_antecedents_cross_year_window_and_suppression` — d7/d30/d90 read `[year_start-90d, year_end)`; a prior-year window gap raises `EventSuppressed`, suppresses with its own reason, never a short sum.
- [ ] 2a.10 GREEN `tasks.py` — widen the resolved-interval read to `[year_start-90d, year_end)` (D6); `compute.py`'s `in_window` filter keeps `annual.selected` unchanged.
- [ ] 2a.11 Add 4 threshold entries to `policy.py::RAINFALL_METRIC_POLICY` — `annual_normal` (0.9/0.8), `annual_percentile` (0.9/0.8), `d7`/`d30`/`d90` (0.9/0.8 each). No `summary` entry.
- [ ] 2a.12 RED `gee-backend/tests/new/geo/rainfall/test_rainfall_insights_metrics.py::test_no_metric_suppressed_as_policy_threshold_unset` (real PG) — full-coverage analysis: every new metric `available`, none `policy_threshold_unset` (spec: "Complete analysis has no unthresholded metric").
- [ ] 2a.13 RED `test_rainfall_insights_metrics.py::test_normal_and_percentile_share_selected_comparison_end`.
- [ ] 2a.14 RED `test_rainfall_insights_metrics.py::test_d90_suppressed_with_reason_when_prior_year_incomplete` — integration-level cross-year d90.
- [ ] 2a.15 Confirm `compute.py` stays in the commented `.cosmic-ray.toml:78-90` block alongside `policy.py`/`service.py`/`temporal.py` — no new uncommented pure module introduced.

## Slice 2b: Summary Mechanism, Revision Bump, Cross-Source Caveat, Stale Requeue (D3, D4, D5, LIA-102 fold)

- [ ] 2b.1 RED `test_mutation_targets_rainfall.py::test_summary_never_describes_policy_suppressed_metric_as_available` — feed `rainfall_summary` post-policy groups where build-time completeness would read `available` but policy suppressed it; summary names it suppressed, never available (spec: "Policy suppresses a metric the raw data would have supported").
- [ ] 2b.2 RED `test_mutation_targets_rainfall.py::test_summary_states_match_disclosed_metric_states` — every state named in the summary matches the disclosed per-metric state (spec: "Summary and badges cannot disagree").
- [ ] 2b.3 RED `test_mutation_targets_rainfall.py::test_build_snapshot_emits_no_summary_key` — `compute.build_snapshot`'s envelope has no `"summary"` root key.
- [ ] 2b.4 GREEN `service.py::rainfall_summary(normalized_groups)` — pure, reads only `state`/`reason`/`value`; called at the end of `normalize_snapshot` after the `_normalize_metric` loop (`service.py:435-448`), writes `normalized["summary"]`. Remove `summary` emission from `compute.build_snapshot`. Makes 2b.1-2b.3 pass.
- [ ] 2b.5 RED `gee-backend/tests/new/geo/rainfall/test_backend_api.py::test_summary_disagrees_from_build_time_completeness_end_to_end` (real PG) — thresholds chosen so build-time and post-policy state disagree; served JSON `summary` matches post-policy.
- [ ] 2b.6 Bump `policy.py::RAINFALL_METRIC_POLICY_REVISION`. RED `test_backend_api.py::test_revision_bump_lands_enriched_envelope_not_conflict_skipped` — a key already `done` under the old revision produces a new row instead of an `ON CONFLICT DO NOTHING` discard.
- [ ] 2b.7 RED `test_backend_api.py::test_stale_policy_revision_served_and_requeued` — a served snapshot whose `metric_policy.revision` differs from the current constant is still served, and a refresh is enqueued labelled `policy_revision_stale`, bounded by `recent_done`'s cooldown (`service.py:238-248`).
- [ ] 2b.8 GREEN `router.py::read_analysis` — when `revision.policy_revision != RAINFALL_METRIC_POLICY_REVISION`, serve the row and enqueue the labelled refresh. Makes 2b.6/2b.7 pass.
- [ ] 2b.9 RED `test_mutation_targets_rainfall.py::test_cross_source_baseline_caveat_present_for_nrt_selected_year` — `annual.normal`/`annual.percentile` carry `"cross_source_baseline=chirps-v3-final_vs_chirps-v3-sat"` in `discrepancies` when the selected year's source differs from `chirps-v3-final`.
- [ ] 2b.10 RED `test_mutation_targets_rainfall.py::test_cross_source_baseline_caveat_absent_when_sources_match` — no such entry when both sides are Final.
- [ ] 2b.11 GREEN `compute.py::build_snapshot` — fixed `cross_source_baseline=...` discrepancy entry on normal/percentile (D5). Makes 2b.9/2b.10 pass.
- [ ] 2b.12 Edit `design.md` D4 mechanism reason 3 (~line 230-232, LIA-102 fold): the audit CSV route only serializes `metric_rows(normalized)` (`service.py:451-459`), which iterates `METRIC_GROUPS=("annual","antecedents","intensity")` and never the root `summary` key. Correct "single funnel for all three disclosures" to name JSON and the xlsx Resumen sheet as the two carrying `summary` (CSV's own row projection excludes root keys). Doc-only — proving check: reviewer diff of `design.md`.

## Slice 3a: Series Module — Consistency Pin + `data_revision` Exposure (D3, LIB-101 fold)

- [ ] 3a.1 RED `gee-backend/tests/new/geo/rainfall/test_rainfall_series_consistency.py::test_untouched_intervals_report_consistent_true` (real PG) — unchanged intervals in the build window → `consistent_with_snapshot: true`, `consistency_reason: null` (spec: "Series still matches its revision").
- [ ] 3a.2 RED `test_rainfall_series_consistency.py::test_superseded_slot_reports_data_revision_moved` — supersede one slot inside the build window after the revision is stored → `false` + `"data_revision_moved"` (spec: "Daily data was corrected after the analysis was stored").
- [ ] 3a.3 RED `test_rainfall_series_consistency.py::test_two_nonsuperseded_families_report_interval_family_ambiguous` — two revision families present, neither superseded, in the window → `false` + `"interval_family_ambiguous"`.
- [ ] 3a.4 RED `test_rainfall_series_consistency.py::test_pin_uses_d6_widened_read_window` — pin recompute uses `[year_start-90d, year_end)`, not the displayed calendar-year window.
- [ ] 3a.5 GREEN `repository.py::daily_series_rows` + `repository.py::baseline_curve_rows` — both anti-joined on supersession (pattern of `intervals_in_window`).
- [ ] 3a.6 GREEN create `series.py` — recompute `compute.data_revision_for(...)` over `(source_id, scope.kind/id/version)` and the D6-widened window; family via `revision_family(RainfallIntervalValue.provider_revision)` over the read rows (exactly one family, else `interval_family_ambiguous`); compare to the row's stored `data_revision`; return points + `consistent_with_snapshot`/`consistency_reason`. Makes 3a.1-3a.4 pass.
- [ ] 3a.7 Add a one-line note to `design.md` D3 step 2 (~line 152-153, LIB-101 fold): build-time family comes from the adapter batch's single reported `provider_revision` (`tasks.py:285`); pin-time family is derived per-row from persisted `RainfallIntervalValue.provider_revision` across possibly-multiple rows — bounded to the conservative direction (a false `interval_family_ambiguous`, never a false-consistent match). Doc-only — proving check: reviewer diff of `design.md`.
- [ ] 3a.8 RED `test_rainfall_series_consistency.py::test_normal_curve_last_point_equals_annual_normal_value` — normal curve's last point equals `annual.normal.value`; curve keyed by `(month, day)`, Feb-29 omitted.
- [ ] 3a.9 GREEN `series.py`/`baseline_curve_rows` — normal curve averaged across exactly `annual.normal`'s eligible-year set. Makes 3a.8 pass.
- [ ] 3a.10 GREEN `service.py` — add `"data_revision"` to `SNAPSHOT_ROOT_KEYS` (`service.py:142-155`).
- [ ] 3a.11 RED `test_backend_api.py::test_analyses_response_discloses_data_revision` (real PG) — served `/analyses` JSON includes `data_revision` matching the row's column.
- [ ] 3a.12 GREEN `router.py::read_analysis` — inject `normalized["data_revision"] = str(revision.data_revision)` post-normalize, mirroring `analysis_revision_id` (`router.py:148-156`). Makes 3a.11 pass.
- [ ] 3a.13 GREEN `router.py` — new `GET /rainfall/analyses/{revision}/series`, resolved from the revision id (inherits the CSV route's auth/404), echoing `data_revision`/`comparison_end`/`available_through`.
- [ ] 3a.14 RED `consorcio-web/tests/unit/rainfallApi.test.ts::"snapshot type carries data_revision"`; GREEN `consorcio-web/src/lib/api/rainfall.ts` — add `data_revision: string` to `RainfallAnalysisSnapshot` (`rainfall.ts:74-86`).

## Slice 3b: xlsx Export + TS Contract + Consistency Exposure (D7)

- [ ] 3b.1 RED `gee-backend/tests/new/geo/rainfall/test_rainfall_export_xlsx.py::test_authorized_export_has_resumen_and_serie_diaria_sheets` (real PG) — authorized request returns both sheets, non-complete states by state+reason, never zero (spec: "Authorized export includes both sheets").
- [ ] 3b.2 RED `test_rainfall_export_xlsx.py::test_unauthorized_export_denied` — a requester lacking Rainfall v2 authorization is denied (spec: "Unauthorized export is denied").
- [ ] 3b.3 RED `test_rainfall_export_xlsx.py::test_resumen_stamps_series_consistency_both_directions` — Resumen's `"Serie diaria consistente con el análisis: sí | no — <motivo>"` reflects both cases from slice 3a.
- [ ] 3b.4 RED `test_rainfall_export_xlsx.py::test_export_filename_and_content_disposition` — `Content-Disposition: attachment; filename="lluvia_{revision}.xlsx"`.
- [ ] 3b.5 RED `test_rainfall_export_xlsx.py::test_audit_csv_bytes_unchanged` — regression: existing `.csv` route output untouched.
- [ ] 3b.6 GREEN create `export.py` — `openpyxl.Workbook(write_only=True)` → `BytesIO`; Resumen from `metric_rows(normalize_snapshot(...))` (`None` → empty cell, never 0) + series-consistency stamp; Serie diaria from `series.py` (fecha, mm, acumulado, normal acumulada, estado).
- [ ] 3b.7 GREEN `router.py::export_analysis_xlsx` — `GET /rainfall/analyses/{revision}.xlsx`, inherits router-level `require_admin_or_operator` (`router.py:39-41`). Makes 3b.1-3b.5 pass.
- [ ] 3b.8 RED `consorcio-web/tests/unit/rainfallApi.test.ts::"downloads xlsx and types series response"` — `downloadRainfallXlsx(revisionId)` requests `.xlsx`; series response type has `consistent_with_snapshot: boolean` and `consistency_reason: string | null`.
- [ ] 3b.9 GREEN `consorcio-web/src/lib/api/rainfall.ts` — `downloadRainfallXlsx` + series response types. Makes 3b.8 pass.
- [ ] 3b.10 RED `consorcio-web/tests/hooks/useRainfallAnalysis.test.tsx::"useRainfallSeries exposes consistency fields"` — hook surfaces `consistent_with_snapshot`/`consistency_reason`/points from `/series`.
- [ ] 3b.11 GREEN `consorcio-web/src/hooks/useRainfallAnalysis.ts::useRainfallSeries(revisionId)`. Makes 3b.10 pass.

## Slice 4: Frontend Chart (D8)

- [ ] 4.1 RED `consorcio-web/tests/unit/RainfallAccumulationChart.test.tsx::"renders both series and both dates"` — two `Line`s (selected vs normal) + `ReferenceLine` at `comparison_end`; footer discloses `comparison_end` and `available_through` (spec: "Chart shows both dates"); mock `ResponsiveContainer` per `tests/unit/PrecipChart.test.tsx:41-42`.
- [ ] 4.2 RED `RainfallAccumulationChart.test.tsx::"renders staleness alert and re-request action when inconsistent"` — `consistent_with_snapshot: false` → curve renders + Mantine `Alert` + re-request button; absent when `true`.
- [ ] 4.3 RED `RainfallAccumulationChart.test.tsx::"re-request action handles 200 and 202"` — re-POST to `/analyses` handles a newer-revision 200 and a labelled 202 via the existing poll path (`rainfall.ts:88-99`).
- [ ] 4.4 GREEN create `components/map2d/rainfall/RainfallAccumulationChart.tsx` — `recharts` directly (not `@mantine/charts`), fed by `useRainfallSeries(revisionId)`; staleness `Alert` + re-request wiring. Makes 4.1-4.3 pass.
- [ ] 4.5 RED `RainfallAccumulationChart.test.tsx::"campaign preset reformats without a new /analyses request"` — `SegmentedControl` windows the x-axis of the same calendar-year series; no `/analyses` call fires on toggle (spec: "Preset does not change the analysis period").
- [ ] 4.6 GREEN — campaign-preset `SegmentedControl` in `RainfallAccumulationChart.tsx`. Makes 4.5 pass.
- [ ] 4.7 RED `consorcio-web/tests/unit/RainfallMetricList.test.tsx::"AnnualText includes the percentile phrase"` (create if absent) — `AnnualText` (`RainfallMetricList.tsx:63-75`) renders the percentile phrase via `rainfallFormat.ts:14-29`.
- [ ] 4.8 GREEN `RainfallMetricList.tsx::AnnualText` — add the percentile phrase. Makes 4.7 pass.
- [ ] 4.9 Extend `consorcio-web/tests/unit/RainfallDetailPanel.test.tsx` — panel mounts `RainfallAccumulationChart` for a served revision.
- [ ] 4.10 Extend `consorcio-web/tests/e2e/rainfall-v2-detail.spec.ts` — xlsx download link visible and triggers a download; chart renders with both series visible end-to-end.

## Ops: Backfill Runbook Execution + Doc-Nit Folds

- [ ] Ops.1 After slice 1 merges and the `historical` role flag is enabled, run `backfill_cli.py` for 1991 alone; verify 365 persisted intervals for `zona_cc_ampliada`.
- [ ] Ops.2 Run the remaining 1992-2020 years; verify 30/30 checkpoints `completed_at`, 0 duplicate rows on a dry re-run.
- [ ] Ops.3 Settle `RAINFALL_BACKFILL_PACE_SECONDS` from the observed 1991-run pace; adjust the `tasks.py` default if the 5s guess proves wrong (design.md Open Question).
- [ ] Ops.4 LIA-101 fold: confirm this document's chain (1 → 2a → 2b → 3a → 3b → 4) and Review Workload Forecast show no slice above 400 production lines. Doc-only — proving check: this document.
- [ ] Ops.5 LIA-003 fold: before enabling slice 2b's stale-policy requeue at scale, run the proposal's scope-population SQL (`SELECT count(DISTINCT ...) zone_scopes`, `SELECT count(*) basins FROM zonas_operativas`) against the deployed DB to confirm the small-population assumption holds.
- [ ] Ops.6 Resolve the design.md open question: whether `annual.percentile` should also suppress when `annual.selected` is `partial`; if yes, file a follow-up task against slice 2a's `compute.py` builder to inherit `partial`.

## Coverage: Delta-Spec Scenarios → Tasks/Tests

| Requirement | Scenario | Task(s) | Test |
|---|---|---|---|
| Historical Baseline Backfill | Interrupted backfill resumes | 1.11-1.12 | `test_rainfall_backfill.py::test_backfill_resumes_after_interruption_no_refetch` |
| Historical Baseline Backfill | Shared asset fetched once per year | 1.9-1.10 | `test_rainfall_backfill.py::test_backfill_dedupes_shared_asset_one_fetch_per_year` |
| Policy Thresholds for New Metrics | Complete analysis has no unthresholded metric | 2a.11-2a.12 | `test_rainfall_insights_metrics.py::test_no_metric_suppressed_as_policy_threshold_unset` |
| Summary Coheres with the Disclosed Metric States | Policy suppresses a metric raw data would have supported | 2b.1, 2b.4 | `test_mutation_targets_rainfall.py::test_summary_never_describes_policy_suppressed_metric_as_available` |
| Summary Coheres with the Disclosed Metric States | Summary and badges cannot disagree | 2b.2, 2b.4 | `test_mutation_targets_rainfall.py::test_summary_states_match_disclosed_metric_states` |
| Percentile Minimum Sample Size | February 29 rank on a small sample | 2a.4-2a.5 | `test_mutation_targets_rainfall.py::test_percentile_suppressed_feb29_small_sample` |
| Campaign Display Preset | Preset does not change the analysis period | 4.5-4.6 | `RainfallAccumulationChart.test.tsx::"campaign preset reformats without a new /analyses request"` |
| Friendly Report Export (xlsx) | Authorized export includes both sheets | 3b.1, 3b.6-3b.7 | `test_rainfall_export_xlsx.py::test_authorized_export_has_resumen_and_serie_diaria_sheets` |
| Friendly Report Export (xlsx) | Unauthorized export is denied | 3b.2, 3b.7 | `test_rainfall_export_xlsx.py::test_unauthorized_export_denied` |
| Chart Discloses Comparison Date and Freshness | Chart shows both dates | 4.1, 4.4 | `RainfallAccumulationChart.test.tsx::"renders both series and both dates"` |
| Chart Discloses Comparison Date and Freshness | Daily data corrected after the analysis was stored | 3a.2, 3a.6, 4.2, 4.4 | `test_rainfall_series_consistency.py::test_superseded_slot_reports_data_revision_moved` + `RainfallAccumulationChart.test.tsx::"renders staleness alert..."` |
| Chart Discloses Comparison Date and Freshness | Series still matches its revision | 3a.1, 3a.6 | `test_rainfall_series_consistency.py::test_untouched_intervals_report_consistent_true` |

## Mutation Targets

`policy.py`, `service.py`, `temporal.py`, `compute.py` stay registered-commented in `gee-backend/.cosmic-ray.toml:78-90` per existing repo precedent (Python-3.11 cosmic-ray availability gap, not a coverage gap — `tests/test_mutation_targets_rainfall.py` already extended by 2a.1-2a.9, 2b.1-2b.3, 2b.9-2b.10 above). No new pure module is wired uncommented into the gate; enters the gate only alongside the other three once a measured CI run exists.
