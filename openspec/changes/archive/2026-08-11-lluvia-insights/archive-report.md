# Archive Report — lluvia-insights

**Change**: `lluvia-insights` — Rainfall v2 Product Layer
**Repo**: `/home/javier/programacion/consorcio-canalero`
**Archived**: `2026-08-11` → `openspec/changes/archive/2026-08-11-lluvia-insights/`
**Artifact store**: hybrid (openspec files + Engram topics)
**Merged**: PR **#176**, squash → `main` @ `65ebb90f`
**Verification verdict**: PASS-with-notes — 0 CRITICAL · 3 WARNING · 5 SUGGESTION

---

## 1. What shipped

The change closed the spec-vs-implementation gap left by Rainfall v2: the pipeline materialized only `annual.selected`, so staff got one number with no reference. Delivered as a 6-slice feature-branch chain (1 → 2a → 2b → 3a → 3b → 4), each slice under the 400-line review budget, only the tracker branch merging to `main`.

| Slice | Delivered |
|---|---|
| 1 | Provider-asset baseline key (`scope_kind="provider_asset"`, `BASELINE_ASSET_VERSION="v1"`), `repository.baseline_cumulatives`, `tasks.backfill_baseline_range` + `backfill_cli.py`, labelled stop on `(AdapterError, CircuitOpen)` |
| 2a | `annual.normal` / `annual.percentile` (empirical Weibull rank, `MIN_BASELINE_YEARS = 20`) + `antecedents.{d7,d30,d90}` over the D6-widened `[year_start-90d, year_end)` read; 5 `RAINFALL_METRIC_POLICY` threshold entries |
| 2b | Disclosure-time `summary` (`service.rainfall_summary`, never from build-time completeness), policy revision bump to `rainfall-v2-2026-08-insights`, cross-source baseline caveat, stale-policy requeue-on-read with the 3-rung cooldown ladder |
| 3a | `series.py` — daily series with a server-side consistency pin (`consistent_with_snapshot` / `consistency_reason`), `data_revision` exposed as a snapshot root key, `GET /rainfall/analyses/{revision}/series` (read-only, enqueues nothing) |
| 3b | Staff-gated xlsx export (Resumen + Serie diaria) beside the untouched audit CSV; shared spreadsheet-formula neutralization for both exports |
| 4 | `RainfallAccumulationChart` (recharts): year-vs-normal curves, comparison-end + last-evidence-day disclosure, staleness alert, campaign display preset, `integrity_refused` rendered distinctly from `suppressed` |

**Gates at verify** (executed, not inherited): backend `2128 passed / 5 skipped`; rainfall subset `455 passed`; frontend `typecheck exit 0` (both projects); `vitest 3675 passed / 278 files`; `lint exit 0`; Playwright `9 collected` (collection only — e2e still unexecuted, V-008).

## 2. Deploy and backfill (prod, Hetzner)

- Deployed to prod: build + migrate + up, backend healthy.
- **Backfill baseline complete**: 1991 dry-run **365/365** intervals, 0 duplicates; 1992–2020 **29/29** years; total **10958/10958** intervals for `chirps-v3-final` under the `provider_asset` scope, exact span `1991-01-01 → 2020-12-31`.
- **Feature verified live**: revisions under policy `rainfall-v2-2026-08-insights` re-materialized on their own through requeue-on-read (no intervention), with normal / percentile / antecedents `available` on real numbers:
  - **2026**: 503.4 mm vs normal-to-date 511.8 → **p46.9**
  - **2025**: 1025.5 mm vs 951.2 → **p68.8**
- The same-date asymmetry that LI2A-101 corrected is observable in prod: 2026 normal-to-date 511.8 vs full-year normal 951.2.

Evidence: Engram #13714 (`sdd/lluvia-insights/deploy`); backfill log `/tmp/backfill-full.log` on the box.

## 3. Spec merge into the source of truth

Delta `specs/rainfall-analysis/spec.md` merged into `openspec/specs/rainfall-analysis/spec.md` — **1 MODIFIED + 7 ADDED requirements**, integrated in the base spec's own structure and voice rather than appended as a block.

| Requirement | Action | Placed |
|---|---|---|
| GEE Quota Guards on Request-Path Re-enqueue and Poll | MODIFIED | in place (poll-refresh exception + 3-rung cooldown ladder; 3 scenarios → 7) |
| Percentile Minimum Sample Size | ADDED | after "Calendar-Year Comparison and Baseline" (refines the percentile baseline) |
| Campaign Display Preset | ADDED | after "Percentile Minimum Sample Size" (refines the campaign-is-not-a-period rule) |
| Summary Coheres with the Disclosed Metric States | ADDED | after "Required Rainfall Outcomes" (which introduces the summary) |
| Policy Thresholds for New Metrics | ADDED | after "Partial, Suppressed, and Unavailable Data States" (the policy gate it feeds) |
| Historical Baseline Backfill | ADDED | after "Interval Persistence on Ingest" (the persistence path it drives) |
| Chart Discloses Comparison Date and Freshness | ADDED | after "Provider Correction Supersession Within a Revision" (its second half is the disclosure consequence of a correction landing after storage) |
| Friendly Report Export (xlsx) | ADDED | after "CSV Export Parity" (same authorization boundary, CSV contract unchanged) |

Also applied at merge time:

1. **T2 amendment honored** — the disclosure requirement names the **inclusive last-evidence day** (`available_through − 1 day`) and forbids presenting the raw exclusive `available_through` as a day with evidence. Merged verbatim from the amended delta.
2. **V-003 applied** — the "Summary Coheres" scenario no longer names **CSV** among summary channels (CSV structurally carries no summary: `metric_rows_csv` projects `METRIC_GROUPS` only, never root keys). Reworded to "JSON or in the xlsx Resumen sheet", plus one sentence in the requirement body stating the CSV exclusion explicitly so a future reader cannot "fix" the wording by adding a summary to CSV and breach D7.
3. **Purpose extended by one sentence** naming what the materialized baseline now lets the capability serve (normal, percentile, antecedents, summary, CSV + xlsx exports).

**Merge decision recorded for audit**: the base requirement's paragraph explaining that the scheduled sweeps enqueue through a mechanism outside `queue_missing_analysis` was **retained** inside the MODIFIED requirement. The delta rewrote the requirement without restating that paragraph, but keeps its scenario and does not contradict it; deleting a non-contradicted precision the delta never argued against would have been a silent loss. Kept as paragraph 2, ahead of the new poll-refresh exception.

**Deliberate non-changes**: "Provisional Data and Revision Visibility" still exposes `available_through` as metadata. That is metadata exposure, not reader-facing rendering, and does not conflict with the new disclosure rule, which governs what is *presented as a day with evidence*.

## 4. Task state at archive

89 implementation tasks checked, all verified — no stale unchecked implementation task. 15 verify spot-checks (weighted toward tasks that name no test) all confirmed in code.

**Archive-time reconciliation (recorded per the archive policy)**: Ops.1, Ops.2 and Ops.3 were unchecked at verify time because they were owner-gated post-merge operations. They were executed in prod on 2026-08-11 and are marked `[x]` in the archived `tasks.md` with their evidence inline (365/365 for 1991, 29/29 years for 1992–2020, 10958/10958 intervals, 0 duplicates on re-run; the 5 s pacing default held, so no `RAINFALL_BACKFILL_PACE_SECONDS` change was needed). Reason for the flip: the work is complete and proven (Engram #13714), and an archived audit trail showing it unchecked would understate shipped work. No implementation checkbox was touched.

Task 4.3 remains `[x]` and struck through as SUPERSEDED by Judgment Day Round 1 — the re-request button was implemented and then removed as structurally inert, with 3 absence tests replacing its 4 behavior tests. The box records history; the strike-through records the outcome.

## 5. Bequest — residual-risk backlog (from verify-report §7)

This is the change's inheritance. Nothing here blocked archive; all of it survives the change.

**P1 — disclosure correctness**
1. ~~**LI4-004** `metricLabel('normal')` hardcodes `'Normal 1991–2020'`~~ — **DONE 2026-08-11 (4/4 sitios, follow-up `1e38b1e3..1f3003c9`)**. First recorded DONE with **1 of 4 sites fixed** — the badged row only. The branch's own pre-PR lens caught the overclaim (`CC-001`/`CC-002`, review-ledger "Cola corta") and the remaining three were closed before the PR: `service.SUMMARY_METRIC_LABELS` (the narrative, which renders in the SAME subtree as the badge), `export.NORMAL_CURVE_LABEL` + the xlsx metric table, and the chart's suppressed-curve notice. Every label now derives from the envelope's `baseline` with a period-less honest fallback, and the regression assertion became an allowlist against `snapshot.baseline` instead of a denylist against one literal. RED captured per site.
2. ~~**Ops.5** run the scope-population SQL~~ — **DONE 2026-08-11**, small-population assumption confirmed (§10).
3. **V-002** ruff gates — not executable in the verify sandbox; closed post-report by the orchestrator.

**P2 — operational (owner-gated)**
4. ~~Ops.1 / Ops.2 backfill execution~~ — **DONE 2026-08-11** (see §2).
5. ~~Ops.3 pacing constant~~ — **DONE 2026-08-11**, default retained.
6. ~~**Ops.6**~~ — **DONE 2026-08-11**, opción 1 (`f95bf8e5`, rama `fix/rainfall-percentile-evidence-gate`): the percentile is now gated on the selected year's OWN evidence, so the ~10% band that the literal option 1 did not reach is closed too (§10). **JDA-005** (raw-vs-normalized curve gate) still open.
7. **V-008** execute the e2e suite with seeded credentials against a live backend (Playwright still collects but never runs).

**P3 — robustness**
8. ~~**LI4-005** fallback on `NORMAL_CURVE_NOTICE[state]`~~ — **DONE 2026-08-11** (§10): one `normalCurveNotice()` accessor guards both index sites. RED captured — the panel subtree rendered empty.
9. **LI4-001** drop the unreachable `echoMismatch` branch, or give `/series` an independent digest so the check has a real source.
10. **LI2A-004** three unpinned copies of `"chirps-v3-final"` (`service.RAINFALL_HISTORICAL_SOURCE`, `repository.py:657`, `compute._BASELINE_SOURCE_ID`) with no drift test.
11. **LI2A-006** document `rolling_total`'s insertion-order precondition.

**P4 — hygiene**
12. **LI4-003** campaign empty-window unit case; move the e2e campaign fixture to a past year.
13. ~~**LI4-002** vacuous test / dead guarded branch~~ — **DONE 2026-08-11** (§10): the dead `neutralize_spreadsheet_formula` wrapper over `json.dumps` removed and the false "Order matters" claim dropped; `json.dumps` itself KEPT (load-bearing — without it the cell is Python `repr`, not JSON). Test rewritten to pin the JSON envelope as the real containment, plus a cell-level `str` case.
14. ~~**LI4-006 / V-005**~~ — **DONE 2026-08-11** (§10): `XLSX_BODY` rewritten as escapes (byte-identical, verified), spec enrolled in `tsconfig.tests.json`. The enrolment immediately caught a REAL defect: `route.request()`'s `method`/`url` were destructured as properties though Playwright exposes them as METHODS, so the mock router matched nothing and would have thrown on the first intercepted call.
15. The 62-file TS typecheck widening — replace `tsconfig.tests.json`'s hand-list with `tests/**`; until then the ENROLMENT RULE header is the only thing keeping that gate honest.
16. **V-001** (ledger status cells understate three shipped fixes) and **V-007** (pin one DB shape so `test_martin_reader_grants` stops drifting) remain open. ~~**V-004**~~ — **DONE 2026-08-11** (§10): un-exported, its "two consumers" docstring corrected. ~~**V-006**~~ — **DONE 2026-08-11**: 2a.11 now reads 5, and its stale `0.9/0.8` threshold values corrected to the shipped `0.667/0.667`. **V-003 is closed by this archive's spec merge.**

## 6. Operational runway

| Item | State |
|---|---|
| Ops.1 — 1991 dry-run, 365 intervals | **DONE 2026-08-11** — 365/365, 0 duplicates |
| Ops.2 — 1992–2020, 30/30 checkpoints, 0 dupes | **DONE 2026-08-11** — 29/29 years, 10958/10958 total |
| Ops.3 — settle `RAINFALL_BACKFILL_PACE_SECONDS` | **DONE 2026-08-11** — 5 s default held, no tuning needed |
| First 03:30 sweep after deploy | **PENDING** — the next checkpoint; confirms the current-year re-materialization cadence fires in prod |
| Ops.4 — 400-line chain confirmation (doc-only) | **DONE 2026-08-11 — result NEGATIVE**, the budget was exceeded (§10) |
| Ops.5 — scope-population SQL before scaling the requeue | **DONE 2026-08-11** — small-population assumption confirmed (§10) |
| Ops.6 — `partial` percentile open question | **DONE 2026-08-11** — question was the wrong one; the real defect behind it is fixed (opción 1, `f95bf8e5`) (§10) |

Known adjacent debt, not owned by this change: celery-beat still reports a lying healthcheck.

## 7. Artifact traceability (Engram)

| Artifact | Observation | Project |
|---|---|---|
| explore | #13355 `sdd/lluvia-insights/explore` | consorcio-canalero |
| proposal | #13371 `sdd/lluvia-insights/proposal` | consorcio-canalero |
| delta spec (amended after JD R1: summary cedes + series consistency) | #13383 | consorcio-canalero |
| design — JD Round 1 fixes | #13398 | consorcio-canalero |
| design — APPROVED (JD unanimous) | #13444 | consorcio-canalero |
| tasks | #13451 `sdd/lluvia-insights/tasks` | consorcio-canalero |
| apply-progress | #13472 `sdd/lluvia-insights/apply-progress` | consorcio-canalero |
| Judgment Day apply — Round 1 fix | #13682 | javier |
| Judgment Day apply — APPROVED (2× CLEAN) | #13685 | javier |
| verify-report | #13689 `sdd/lluvia-insights/verify-report` | consorcio-canalero |
| deploy + backfill | #13714 `sdd/lluvia-insights/deploy` | javier |
| archive-report | this document + `sdd/lluvia-insights/archive` | — |

**Traceability gap, disclosed**: there is no standalone `sdd/lluvia-insights/design` topic — the design artifact lives in the repo file plus observations #13398 and #13444. Records for this change are also split across two Engram projects (`consorcio-canalero` and `javier`) because the MCP process resolves the project from a fixed cwd; the split is bookkeeping, not a content gap.

## 8. Review process record

- **9 CRITICAL-class ledger rows, all `fixed`**, each with a recorded downstream verdict (scoped re-review CLEAN, refuter adjudication, or a 2× CLEAN Judgment Day re-judge).
- **Convergence budget respected everywhere** — no review exceeded 1 fix round against a budget of 2. The pre-verify tidy was correctly not counted as a round.
- **Refuter protocol compliant**: slices 2a/2b/3a each ran exactly 1 general refuter over the merged CRITICAL list; 3b/4 had none to refute; both Judgment Day rounds used two-judge convergence, the documented exception. Slice 1's deliberate refuter skip was owned in writing, backed by a captured `UndefinedTable` reproduction rather than a plausibility claim.
- **No CRITICAL hiding as `info`** — every `info` row audited at verify.

## 9. Closure

Planned, designed under two Judgment Day rounds, implemented in 6 TDD slices, verified PASS-with-notes, merged as PR #176, deployed, backfilled and observed live. **SDD cycle complete.** The residual backlog in §5 and the open runway items in §6 are the bequest, not blockers.

## 10. Post-archive ops closure 2026-08-11

Closes the runway items left open at archive. Ops.4 and Ops.5 are settled. Ops.6 was first ESCALATED rather than closed, because answering it surfaced a defect the question was not pointed at; it was then fixed the same day and its resolution is recorded below the escalation, which is left standing as the record of how the real defect was found.

### Ops.4 — forecast vs actuals (CLOSED, result negative)

The check was to confirm no slice exceeded **400 production lines**. Performed, and **the forecast was not met.**

Measured over the merged feature commit `65ebb90f`, excluding tests, `openspec/` and `.md`:

| | Lines |
|---|---|
| Production added | **3284** |
| Production deleted | 134 |
| Per-slice forecast chain (`apply-progress.md`) | ≈1510 (~380 + ~240 + ~210+60 + ~240 + small + ~380) |

Four single FILES each exceed the 400-line slice budget on their own:

| File | Added |
|---|---|
| `gee-backend/app/domains/geo/rainfall/compute.py` | +491 |
| `consorcio-web/src/components/map2d/rainfall/RainfallAccumulationChart.tsx` | +463 |
| `gee-backend/app/domains/geo/rainfall/series.py` | +461 |
| `gee-backend/app/domains/geo/rainfall/export.py` | +348 |
| `gee-backend/app/domains/geo/rainfall/service.py` | +298 |
| `gee-backend/app/domains/geo/rainfall/repository.py` | +278 |

`apply-progress.md` recorded most slices as "within the forecast slice budget" qualitatively, without measuring the actual production diff — only slice 3a (~290 actual against a ~240 forecast) and slice 2b (+60 amendment lines over ~210) put real numbers on the record. That is how a 2x overrun stayed invisible until now: **the budget was forecast per slice and never measured per slice.**

Honest caveat: this repo deliberately embeds long rationale docstrings inside production files, so raw line counts overstate logical size. The budget was written in raw lines and is exceeded in raw lines; whether the REVIEW load was correspondingly 2x is not something a line count can settle. The useful lesson is procedural — record measured production lines per slice at apply time, or the budget is decorative.

### Ops.5 — scope-population SQL (CLOSED, assumption confirmed)

Run against prod 2026-08-11, before scaling slice 2b's stale-policy requeue:

| Measure | Value |
|---|---|
| `distinct_scopes` | 4 |
| `zonas_operativas` | 15 |
| `analysis_fingerprints` | 14 |
| `outbox_rows` | 26 |

The small-population assumption behind LIA-003 **holds**. The per-key cooldown still is not a global bound, but at a population of 4 scopes / 15 zones that ceiling is not reachable as a stampede. **Re-measure before onboarding a materially larger consortium** — this is a confirmation at today's size, not a proof of the design.

### Ops.6 — `partial` percentile (ESCALATED, then RESOLVED — see the resolution below this section)

**The question as posed cannot be answered, because its premise does not hold.** `annual.selected` is never `partial`: no path in the backend emits that state. `apply_metric_policy` (`policy.py:148-172`) returns only `available` / `suppressed` / `unavailable`, and `partial` survives in the rainfall domain only as a schema Literal (`schemas.py:29`), a preservation branch for an already-stored value (`service.py:515`) and summary labels. So "should the percentile suppress when selected is `partial`" is moot as written.

**The worry behind it is real, reachable, and worse than the question suggests.** The same-date discipline is sound where it applies: `baseline_cutoff_for` (`compute.py:121-144`) cuts the baseline at the last day the selected year actually reaches, so a year IN PROGRESS is ranked against baselines totalled through the same calendar day. A current-year percentile is the designed use case and is correct — prod's 2026 p46.9 is not a defect.

What is NOT handled is a selected year with **internal evidence gaps**. `total_value` sums only matched slots and `completeness = matched_slots / expected_slots` is derived from that same list (`compute.py:531-541`), so a year missing days is short by exactly those days' rain — and `weibull_percentile` ranks that short total against COMPLETE baselines. The design already identified this precise bias mechanism for the trailing-lag case and fixed it (`compute.py:130-136`: "cutting at the calendar date would rank a selected year that is short by the lag … biasing the percentile low"). `window_end` clips only the trailing edge; a hole in the middle produces the identical bias with no guard.

Worse, disclosure is DECOUPLED: `annual` is thresholded at 0.8 coverage, while `annual_normal`/`annual_percentile` are thresholded on the BASELINE's eligible-year fraction (≈0.667) — an entirely different quantity. So the percentile outlives the total it ranks.

Reproduced against the shipped code (30 baseline years, true selected total at p51.6):

| Days missing from the selected year | Selected total | `annual` state | Served percentile |
|---|---|---|---|
| 0% | 500.0 | available | **51.6** (truth) |
| 10% | 450.0 | **available** | **31.2** — both metrics served, ~20 points low, no caveat |
| 21% | 395.0 | suppressed (`coverage_below_threshold`) | **9.4** — served anyway |
| 30% | 350.0 | suppressed | **3.1** |

At 21% the panel's own summary reads: `Disponibles: Percentil histórico 9.4 percentil. Sin dato: Acumulado del año (suprimida: coverage_below_threshold).` A normal year is reported as one of the driest on record, next to an admission that the underlying total was too incomplete to show. The 10% band is arguably worse: nothing is suppressed, nothing is flagged, and the rank is still ~20 points low.

**Recommendation (owner decision, NOT applied here).** Two candidate fixes, in preference order:

1. Couple the percentile to the selected year's own evidence — compute it from the same coverage/completeness that gates `annual`, so a total too incomplete to disclose cannot be ranked. This closes both bands.
2. At minimum, suppress `annual.percentile` whenever the disclosed `annual.selected` is not `available`, with a distinct reason (e.g. `annual_selected_not_disclosed`). This closes the ≥21% band only and leaves the silent 10% bias open.

No code was changed for Ops.6. The finding is a disclosure-correctness defect on a shipped path and wants its own RED-first change with an owner's call on the threshold semantics.

### Ops.6 — RESOLVED 2026-08-11 opción 1, commit `f95bf8e5` (rama `fix/rainfall-percentile-evidence-gate`)

Percentil gated en doble condición — `annual.selected` pasa su gate **Y** day-completeness del año seleccionado ≥ 0.95 (el mismo piso que los años baseline para entrar a la muestra; el año rankeado es miembro). Razón nueva `selected_evidence_below_threshold`, decidida en build.

Bandas:

| Días faltantes | Resultado |
|---|---|
| 0% | `available` (intacto) |
| ~10% (0.902) | percentil suprimido con `annual` available — **la banda que la opción-1-literal no alcanzaba** |
| ~21% | ambos suprimidos |
| lag de cola (completeness 1.0 en ventana clipeada) | intacto y pineado |

`annual.normal` no afectado.
