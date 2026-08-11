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
1. **LI4-004** `metricLabel('normal')` hardcodes `'Normal 1991–2020'`; a different served `baseline` would show one number under two baseline periods. Its negative assertion is scoped to one node and uses a hyphen vs the constant's en-dash, so it cannot fire. Key the label off `snapshot.baseline` and widen the assertion.
2. **Ops.5** run the scope-population SQL before enabling the stale-policy requeue at scale — the per-key cooldown is not a global bound (LIA-003).
3. **V-002** ruff gates — not executable in the verify sandbox; closed post-report by the orchestrator.

**P2 — operational (owner-gated)**
4. ~~Ops.1 / Ops.2 backfill execution~~ — **DONE 2026-08-11** (see §2).
5. ~~Ops.3 pacing constant~~ — **DONE 2026-08-11**, default retained.
6. **Ops.6 / JDA-005** two open questions: should `annual.percentile` also suppress when `annual.selected` is `partial`; and the raw-vs-normalized curve gate.
7. **V-008** execute the e2e suite with seeded credentials against a live backend (Playwright still collects but never runs).

**P3 — robustness**
8. **LI4-005** fallback on `NORMAL_CURVE_NOTICE[state]` so an unmodelled state degrades instead of crashing the panel subtree.
9. **LI4-001** drop the unreachable `echoMismatch` branch, or give `/series` an independent digest so the check has a real source.
10. **LI2A-004** three unpinned copies of `"chirps-v3-final"` (`service.RAINFALL_HISTORICAL_SOURCE`, `repository.py:657`, `compute._BASELINE_SOURCE_ID`) with no drift test.
11. **LI2A-006** document `rolling_total`'s insertion-order precondition.

**P4 — hygiene**
12. **LI4-003** campaign empty-window unit case; move the e2e campaign fixture to a past year.
13. **LI4-002** assert with a cell-level `str` or delete the dead guarded branch and its claim.
14. **LI4-006 / V-005** rewrite `XLSX_BODY` as escapes so git stops treating the spec as binary; enrol the e2e file in `tsconfig.tests.json`.
15. The 62-file TS typecheck widening — replace `tsconfig.tests.json`'s hand-list with `tests/**`; until then the ENROLMENT RULE header is the only thing keeping that gate honest.
16. **V-001** (ledger status cells understate three shipped fixes), **V-004** (`rainfallAnalysisQueryKey` now has one consumer), **V-006** (2a.11 says "4 threshold entries", code has 5), **V-007** (pin one DB shape so `test_martin_reader_grants` stops drifting). **V-003 is closed by this archive's spec merge.**

## 6. Operational runway

| Item | State |
|---|---|
| Ops.1 — 1991 dry-run, 365 intervals | **DONE 2026-08-11** — 365/365, 0 duplicates |
| Ops.2 — 1992–2020, 30/30 checkpoints, 0 dupes | **DONE 2026-08-11** — 29/29 years, 10958/10958 total |
| Ops.3 — settle `RAINFALL_BACKFILL_PACE_SECONDS` | **DONE 2026-08-11** — 5 s default held, no tuning needed |
| First 03:30 sweep after deploy | **PENDING** — the next checkpoint; confirms the current-year re-materialization cadence fires in prod |
| Ops.4 — 400-line chain confirmation (doc-only) | **OPEN** |
| Ops.5 — scope-population SQL before scaling the requeue | **OPEN** (P1) |
| Ops.6 — `partial` percentile open question | **OPEN** |

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
