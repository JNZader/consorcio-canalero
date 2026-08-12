# Apply progress — `lluvia-ux-tarjeta`, slice 1 (answer-first hierarchy)

Branch: `feat/lluvia-ux-01-jerarquia`, based on `feat/lluvia-ux-tarjeta` (tracker) at
`550dc852`, itself based on `origin/main` @ `a2435144`. Mode: hybrid (this file + Engram
topic `sdd/lluvia-ux-tarjeta/apply-progress`). Frontend-only; `gee-backend/**` and
`.github/workflows/**` untouched.

**Status: 30/30 slice-1 tasks complete (1.1-1.30), plus O.2. O.1 is owner-gated and NOT
run.** Strict TDD throughout — every task carrying a RED flag was executed RED first, with
the failure captured before the implementation existed.

> **Record correction.** The first version of this file was committed at `ead8c6dd`
> claiming "26/26 complete", which was true at that moment and stopped being true the same
> day: a second external UX review and two owner decisions added tasks 1.27-1.30 and
> refined 1.26. The numbers below (test counts, bundle delta, diff size) are RE-MEASURED
> for the final state rather than carried over. Nothing here is inherited from the earlier
> record without being re-run.

## Commits

| SHA | Tasks | What |
|---|---|---|
| `550dc852` | — | `docs(sdd)` — the change artifacts (on the TRACKER branch) |
| `ae13520f` | 1.1-1.7 | wetness, freshness and compact-antecedent formatters; `lastEvidenceDay`/`evidenceFooter` move |
| `a57dc3b4` | 1.8-1.10 | `RainfallAnswerCard` + its suite; `AnnualText` moves |
| `d0f7ecb9` | 1.12-1.13 | row/group/list split with `exclude` |
| `1bcb446b` | 1.11, 1.14-1.17 | the panel reorder, folds, freshness-once, controlled preset |
| `cd0d8e3d` | 1.18-1.19 | the ficha `PrecipChart` fold keyed on `v2DetailWillRender` |
| `d61acbff` | 1.20-1.23 | sheet-body testid, e2e sentinel + expand + zero-scroll, npm script |
| `99fec0e9` | 1.24-1.26 | the three owner-reported live-UI defects (OWN-001..003) |
| `7165f3dd` | polish | semantic colour on the derived adjective, word-first |
| `ead8c6dd` | — | `docs(sdd)` — the FIRST apply record (superseded by this one) |
| (final) | 1.27-1.30, 1.26b | the second UX review + the two owner decisions (OWN-004..010) |

## TDD cycle evidence

Every row's RED was OBSERVED, not asserted. Command in each case:
`npx vitest run <file>` before the implementation existed.

| Task | RED (observed failure) | GREEN | REFACTOR |
|---|---|---|---|
| 1.1 → 1.2 | 20 failures, `wetnessFromPercentile is not a function` | 27 passed | cut-offs table extracted to one const object |
| 1.3 | n/a (MOVE) | 28 chart tests pass with ZERO assertion edits; `rg` finds exactly one definition of each moved function | `isoDay` moved with them rather than duplicated |
| 1.4 → 1.5 | 5 failures, `deriveFreshness is not a function` | 34 passed | branch sentences routed through `evidenceFooter` so the copy has one home |
| 1.6 → 1.7 | 2 failures, `compactAntecedent is not a function` | 34 passed | — |
| 1.8/1.9 → 1.10 | file failed to load: `Failed to resolve import .../RainfallAnswerCard` | 20 passed | `readablePercentile` extracted — the headline and the adjective share one gate |
| 1.12 → 1.13 | 1 failure: `rainfall-metric-d7` still rendered under `exclude` | 27 passed (list + panel) | — |
| 1.14 → 1.15/1.16 | 6 failures (order, fold state, R7 witness, freshness-once, accessory, one-click reveal) | 28 passed | `expandFold` helper — the five forced sites share one seam |
| 1.18 → 1.19 | 6 failures (fold body, order, three predicate cases, post-mount flip) | 9 passed | — |
| 1.20 | n/a (one attribute) | 17 passed | — |
| 1.24 (formatters) | 12 failures, `scopeChoiceLabel`/`scopeChoiceLabels`/`shouldUseSegmentedScope`/`metricStateLabel` not functions | 46 passed | labelling split into per-choice + per-set, so the set rule is testable alone |
| 1.24/1.25 (panel) | 2 failures (5 identical options; raw job labels in copy) | 31 passed | `QUEUED_SENTENCE` const — the alert and the announcer cannot drift |
| 1.26 | 2 failures, no `[data-metric-state]` element | 39 passed | reason and flags relocated rather than deleted |
| 1.27 | 3 failures (no previous-year request, no two-year notice, no `data-showing-year`) | 34 panel tests passed | the notice reuses the ONE queued alert instead of adding a second block that states the same pending fact twice |
| 1.28 | failures on `Percentil 46.9` (suffix rendered), and no `rainfall-percentile-gloss` | 25 card + 12 list tests passed | the `percentil` prefix is a table entry, not a branch, so the next non-magnitude unit is data |
| 1.26b | 2 failures (chip on an available row, `Fallback` instead of Spanish) | 39 passed | `stateChip` extracted — the exception rule is one function with one test |
| 1.29/1.30 | 5 failures across card, panel and PrecipChart (old copy pinned) | 279 files / 3777 tests | `ScopeControl` extracted, which also took the panel back under the complexity gate |

## Gates

| Gate | Result |
|---|---|
| `npx vitest run` (full) | **279 files, 3763 tests, all passing** |
| `npm run typecheck` (both projects) | exit 0 |
| `npm run lint` | exit 0 — 3 warnings, all PRE-EXISTING (verified against the merge-base: same 3, `LayerControlsPanel.tsx` ×2 and `useMapLayerEffects.ts` cognitive complexity) |
| `playwright --list` | 10 tests collected in `rainfall-v2-detail.spec.ts`, the zero-scroll case included |
| Backend | untouched — no `pytest` run needed and none claimed |

### O.2 — bundle gate (D12), MEASURED

    merge-base  feat/lluvia-ux-tarjeta        904643 bytes (gzip -9 sum over dist/assets/*.js)
    head        feat/lluvia-ux-01-jerarquia   907163 bytes
    delta                                      +2520 bytes    budget 3072 → PASS

Both figures come from a clean `npm run build` on each branch, same machine, same session.

### O.1 — the declared local run: NOT RUN, and not claimed

Owner-gated by the brief. It needs all five D13 preconditions (loaded catastro,
`E2E_API_BASE`, `E2E_APP_URL`, `FICHA_ENABLED=true` reaching the backend SERVICE, and a
host-reachable Martin), i.e. `docker compose up postgres backend martin` plus a dev
server. **A skipped run is a failed gate, not a pass** — this record makes no claim about
the zero-scroll criterion beyond "the case exists and collects".

## Deviations from design — each with its evidence

1. **The diff is 2853 changed lines, not ~590 (D11).** Measured:
   `19 files changed, 2527 insertions(+), 326 deletions(-)`. Roughly 646 of that is the
   owner amendments and the polish, which the estimate could not have known about; the
   remaining ~2200 is still ~3.7× D11's figure. The estimate undercounted this repo's own
   docblock convention — `rainfallFormat.ts` alone grew 405 lines, most of it the WHY that
   every function here carries. **Consequence, not rounded away: the FULL 4R review tier
   stands, and it stands on measurement.** Nothing about the slice boundary changed; the
   design's argument for not splitting further (a half-applied hierarchy is a worse review
   object) is unaffected by the count.

2. **D6's scope control is amended: `SegmentedControl` only at ≤3 fitting choices, else a
   `NativeSelect`** (task 1.24, ledger OWN-001). Evidence: an owner screenshot of a Bell
   Ville parcel (nomenclatura 3603403896547762) resolving to FIVE scopes. Five segments
   cannot fit the panel's 348 px, so keeping the segmented control would have reproduced
   OWN-003 at the container level. The `rainfall-scope-switch` testid and the
   `Ámbito regional` aria-label ride whichever component renders, so no contract moved.

3. **`isoDay` moved out of the chart with `lastEvidenceDay`** (task 1.3). D10 names only
   the two functions, but `isoDay` is `lastEvidenceDay`'s only dependency and the chart
   needs it too (`comparisonEndDay`). Leaving a copy behind would have been a second
   implementation inside the decision whose entire point is that there is one.

4. **The D11 "three tests move verbatim" figure was not achievable, and the reason
   matters.** `prints the baseline period AS SERVED` swept `rainfall-metrics` for ≥4
   period strings across FOUR surfaces; after the split two of those surfaces are on the
   card and two on the list. Moving it whole would have deleted the list-side detector
   (LI4-004/CC-002 paid for it). It is SPLIT: the card sweeps the card for ≥2, the list
   sweeps the list for ≥2, each still asserting the rendered set equals `snapshot.baseline`
   in either dash spelling. No surface lost its detector.

5. **Only 5 of D11's 7 forced assertion sites needed an edit.** `:359` and `:500` reach
   `rainfall-annual-text`, which moved to the always-mounted card — so they pass unchanged.
   That is the design's own prediction ("or moves to the card"), and the honest count is 5.

6. **`tsconfig.tests.json` needed `src/types/tabler-icons.d.ts`.** Not in any task. The
   panel now imports `CollapsibleSection` → `./icons`, which deep-imports
   `@tabler/icons-react/dist/esm/icons/*.mjs`; that project overrides `include` with a
   hand-maintained list, so the ambient wildcard was outside the program and typecheck
   produced 190 TS7016 errors pointing at `icons.tsx` — a file nowhere near the change.
   Same failure mode as the `vite-env.d.ts` entry already beside it.

7. **`rainfallFormat.test.ts` and `FichaTerritorialRainfallMount.test.tsx` enrolled in
   `tsconfig.tests.json`.** The first is new contract surface; the second is UXJB-206 from
   the info bequest. Both are rainfall contract tests and the file's own ENROLMENT RULE
   requires it.

8. **`RAINFALL_SCOPE_LABELS` moved to `rainfallFormat.ts`.** The panel and the card both
   name a scope, and the spec requires two normals of different scope to be labelled with
   their own — two copies of that vocabulary is how one of them drifts.

9. **OWN-002 also silences a label that HAPPENS to be human.** The e2e fixture serves
   `Procesando base histórica`, which no longer renders. Recorded rather than patched: a
   heuristic for "human-looking labels" passes `role:daily` the day the backend puts a
   space in it.

## Author counterexample self-check

| Category | Evidence | Result |
|---|---|---|
| Null / absence | `value: null`, absent `annual.selected`, absent `annual` group, the stripped four-field `_unavailable` shape, absent percentile, absent antecedents, empty group, unserved reason — each has a test; `null` is never rendered as `0` on any of the three new surfaces (card, accessory, badge row) | Pass |
| Boundaries | The D4 cut-off table pinned from BOTH sides including 30.4/30.6, 69.4/69.6, 89/89.4/89.6; a served percentile of 0 survives as data; `shouldUseSegmentedScope` tested at 1, 2, 3-fitting, 3-overflowing and 5 choices | Pass |
| Concurrency / idempotency | N/A — no new async work, no new writer. The one ordering hazard IS covered: the post-mount `useCanAccess` flip remounts the fold via its `key` instead of freezing a pre-hydration default | Pass |
| Malicious input / security | No new input surface and no authorization change: the render gate stays inside `RainfallDetailPanel` and the backend remains the boundary. The D7 predicate reads the store as a LAYOUT hint only — the e2e's anonymous and ciudadano cases still assert `rainfall-detail` has count 0 | Pass |
| Partial failure / recovery | Queued, gave-up, analysis error, series error, series loading and export error paths all still render and are still tested; an unparseable `available_through` degrades to its raw day instead of throwing (JDA-104), now covered at the analysis level too | Pass |
| State / tenancy / time | The exclusive→inclusive day conversion has ONE implementation with three callers; the card's date provably comes from the snapshot and does not follow the series (test (d)); no timezone round-trip was added | Pass |

## Push status

Not pushed from here. See the return summary — the branches are local.
