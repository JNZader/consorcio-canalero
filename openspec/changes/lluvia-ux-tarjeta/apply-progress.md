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
| `npx vitest run` (full) | **279 files, 3777 tests, all passing** |
| `npm run typecheck` (both projects) | exit 0 |
| `npm run lint` | exit 0 — 3 warnings, all PRE-EXISTING (verified against the merge-base: same 3, `LayerControlsPanel.tsx` ×2 and `useMapLayerEffects.ts` cognitive complexity). A FOURTH appeared mid-apply — `RainfallDetailPanel` crossed the cognitive-complexity gate at 36 — and was fixed by extracting `ScopeControl`, not by raising the threshold |
| `playwright --list` | 10 tests collected in `rainfall-v2-detail.spec.ts`, the zero-scroll case included |
| Backend | untouched — no `pytest` run needed and none claimed |
| Docker CI (`javi-forge ci`, run by the pre-push hook) | passed on every commit through `ead8c6dd`: lint + compile + test on both runners, security scan, ghagga review |

### O.2 — bundle gate (D12), MEASURED — **FAILS by 475 bytes, and is not rounded away**

Every figure below is a clean `npm run build` followed by
`find dist/assets -name '*.js' -exec sh -c 'gzip -9 -c "$1" | wc -c' _ {} \; | paste -sd+ - | bc`,
same machine, same session.

| point | commit | gzip sum | delta vs merge-base | vs 3072 budget |
|---|---|---|---|---|
| merge-base | `550dc852` (tracker; source identical to `origin/main`) | 904643 | — | — |
| DESIGNED slice-1 scope (1.1-1.23) | `d61acbff` | 906584 | **+1941** | PASS |
| + owner defects OWN-001..003 + the colour polish | `7165f3dd` | 907163 | **+2520** | PASS |
| FINAL (+ OWN-004..010, tasks 1.27-1.30) | `4f2138da` | 908190 | **+3547** | **OVER by 475** |

**The gate did exactly what it exists for, so it is reported, not adjusted.** The slice as
DESIGNED passes with 1.1 kB of headroom. What crossed the line is the scope added after
the design was written: seven owner-driven tasks that ship real UI — a second scope-control
component, the one-step fallback query and its notice, the percentile gloss, the scope
sentence and short-source builders, the exception-only chip logic. That is new JavaScript,
and the budget was set against a scope that no longer exists.

**This is an owner/orchestrator decision, not an apply-time one.** The two honest paths:

1. **Amend the budget** for slice 1, recording that the scope grew by seven tasks after
   D12 was written. The figure to amend it to is 3547, measured, not estimated.
2. **Trim 475 bytes.** The only candidate that is not load-bearing is the derived-adjective
   colour map (`RAINFALL_WETNESS_COLORS` + `wetnessColor`), and it is worth ~100-150 bytes —
   not enough on its own, and it was explicitly requested by the review.

What was deliberately NOT done: shaving code to hit the number. Trimming a gate into
compliance is the same failure class as an unmeasured claim — it makes the gate report
what we want instead of what shipped.

### O.1 — the declared local run: NOT RUN, and not claimed

Owner-gated by the brief. It needs all five D13 preconditions (loaded catastro,
`E2E_API_BASE`, `E2E_APP_URL`, `FICHA_ENABLED=true` reaching the backend SERVICE, and a
host-reachable Martin), i.e. `docker compose up postgres backend martin` plus a dev
server. **A skipped run is a failed gate, not a pass** — this record makes no claim about
the zero-scroll criterion beyond "the case exists and collects".

## Deviations from design — each with its evidence

1. **The diff is 3647 changed lines, not ~590 (D11).** Measured:
   `22 files changed, 3297 insertions(+), 350 deletions(-)`. About 1440 of that is the ten
   owner-added tasks (1.24-1.30 plus the polish), which the estimate could not have known
   about; the remaining ~2200 is still ~3.7× D11's figure. The estimate undercounted this repo's own
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

## Deviations added by the post-design amendments

10. **D6's scope control is amended a second time**: extracted into a `ScopeControl`
    component that chooses between `SegmentedControl` and `NativeSelect`. Driven by
    OWN-001, and the extraction itself was forced by the cognitive-complexity gate.

11. **`PrecipChart.tsx` is edited, and it is NOT in the design's File Changes table.**
    Copy only — the headline label and the inner heading (OWN-005). No behaviour, no
    props, no testids. Listed here because a file outside the declared blast radius is
    exactly the thing a reviewer should be told about rather than discover.

12. **The one-step fallback adds a SECOND `useRainfallAnalysis` call.** Recorded because
    it has a visible side effect the design never contemplated: while the previous year is
    displayed, the export buttons, the chart and both folds all describe THAT year. That
    is correct — they describe what is on screen — and it is precisely the kind of thing
    that becomes a bug report if nobody wrote it down.

13. **The announcer is now `VisuallyHidden`.** The design assumed a visible dimmed status
    line; it duplicated every state already on screen. The `aria-live` contract, the
    testid and the announced text are unchanged.

## Fix round 1 of 2 — the full-4R CRITICALs (2026-08-12)

Scope: `review-ledger.md` rows **R3-001** and **R4-001** ONLY (one defect, two faces —
the visible surface and the `aria-live` region). The eight WARNING/SUGGESTION rows are
`info` and were deliberately left alone, R4-002 included.

The defect: `gaveUp` appeared in neither `snapshot` nor `canFallBack`, while the queued
block that owned the `Mostrando {Y-1}` notice AND `data-showing-year` was gated on
`!gaveUp`. Once the poll budget ran out the panel kept a fully rendered Y-1 card, chart
and export row under a year selector reading Y, beside an alert naming neither year — and
the announcer, testing `showingFallback` first, kept promising an auto-update after
polling had permanently stopped.

| step | evidence |
|---|---|
| RED | 2 new tests written first: **2 failed / 34 passed** in `RainfallDetailPanel.test.tsx`. Observed messages: the terminal alert carried `Análisis no disponible aún. Se agotó…` with no year, and the live region still read `…El análisis 2026 se está preparando.` |
| GREEN | **36/36** in that file, then **279 files / 3779 tests** across the suite (was 3777) |

What changed in `consorcio-web/src/components/map2d/rainfall/RainfallDetailPanel.tsx`:
`fallbackTerminalSentence()` (one terminal sentence naming both years, no promise), the
terminal alert extracted to `UnavailableAlert` carrying that sentence plus
`data-showing-year` when a fallback is on screen, and the announcer's `showingFallback`
branch handling `gaveUp` explicitly with the same sentence + `Puede reintentar
manualmente.`

**The extraction was forced by the complexity gate, again.** The two added branches took
the panel to 32 (max 30) — a FOURTH lint warning. Fixed by extracting the alert, exactly
as `ScopeControl` was extracted during the apply; the threshold was not touched. Lint is
back to the 3 pre-existing warnings. An intermediate attempt (extracting the announcer
effect into a pure function) bought ZERO headroom and was reverted: Biome scores nested
function bodies separately, so moving the effect's branches out of the component does not
lower the component's score. Recorded because the next person will try it too.

### Bundle after the fix round (same D12 method, same machine and session)

| point | gzip sum | delta vs merge-base `550dc852` (904643) | vs the amended 3547 budget |
|---|---|---|---|
| pre-fix (source of `4f2138da`, rebuilt now) | 908190 | +3547 | at the amended budget — and it REPRODUCED the recorded figure byte for byte |
| post-fix | **908422** | **+3779** | **OVER by 232** |

232 bytes for one sentence builder, one extracted alert component and one announcer
branch. Measured and reported, not shaved — trimming a gate into compliance is the same
failure class the apply record already refused once.

## Push status

Commits through `ead8c6dd` were pushed to `origin` BEFORE the interruption (both branches;
the pre-push `javi-forge ci` ran full Docker CI and passed). The final commits — `4f2138da`
and this record — are LOCAL, per the orchestrator's instruction to leave pushing to a full
environment.

---

# Apply progress — slice 2 (technical disclosure, D5/D8/D9/D9a)

Branch: `feat/lluvia-ux-02-disclosure`, stacked on `feat/lluvia-ux-01-jerarquia` at
`d91e6f51` (the post-fix, review-CLOSED slice-1 head). Frontend-only; `gee-backend/**` and
`.github/workflows/**` untouched.

**Status: 13/13 slice-2 tasks complete (2.1-2.13).** Strict TDD throughout — every task
carrying a RED flag was executed RED first and the failure was OBSERVED before the
implementation existed.

## Commits

| SHA | Tasks | What |
|---|---|---|
| `0ef63412` | 2.1-2.4 | `hoistProvenance`, `stringifyUnknownFields`, `metricEvidenceLine` |
| `52cf6b15` | 2.9-2.10 | key-driven group renderer + total `isMetricGroup`, then the `intensity` label prune |
| `eb8c0861` | 2.5-2.8, 2.11 | shared provenance block, enumerated field floor on the rows, `source_health` line, summary relocation |
| (final) | 2.12-2.13 | e2e unknown-group witness + the delta-spec reconciling clause + this record |

## TDD cycle evidence

Command in each case: `npx vitest run <file>` before the implementation existed.

| Task | RED (observed failure) | GREEN |
|---|---|---|
| 2.1 → 2.2 | 15 failed / 46 passed — `hoistProvenance is not a function` (with 2.3/2.4's `stringifyUnknownFields`/`metricEvidenceLine`, written in the same RED batch) | 61/61 in `rainfallFormat.test.ts` |
| 2.3 | same batch — `stringifyUnknownFields is not a function` | same 61/61 |
| 2.4 | same batch — `metricEvidenceLine is not a function` | same 61/61 |
| 2.9 → 2.10 | 2 failed / 14 passed — `intensity` rendered under its OLD Spanish title with the label `P24h (mm en 24 h)`, and the unknown-key group did not render at all | 114/114 across list + format + panel |
| 2.5/2.6/2.11 → 2.7/2.8 | 6 failed / 37 passed — no `rainfall-provenance-shared`, no `rainfall-source-health`, no `Intervalo`/`Completitud`/`Calidad`/`Estado temporal` lines, the stripped row still reached `provenance.source_id`, and the summary sat below the groups | 121/121 across the three rainfall files |
| 2.12 | n/a (e2e, not executed here — `--list` collects it) | 10 tests collected in the spec |
| 2.13 | n/a (DOC) | one added clause, no scenario touched |

## Gates

| Gate | Result |
|---|---|
| `npx vitest run` (full) | **279 files, 3807 tests, all passing** (slice-1 head was 3779 — +28 new) |
| `npm run typecheck` | exit 0 on both tsconfigs (`tsc --noEmit` + `tsconfig.tests.json`) |
| `npm run lint` | exit 0 — **3 warnings, all PRE-EXISTING** (`LayerControlsPanel.tsx`, `useMapLayerEffects.ts`, `useReportFormSubmission.ts`). No new one: `RainfallMetricList` stayed under the cognitive-complexity gate because the metadata lines were extracted into named line-builders instead of being inlined as ternaries |
| `npx playwright test --list` | 10 tests collected in `rainfall-v2-detail.spec.ts` |
| Docker CI (`javi-forge ci`, pre-commit hook) | passed on every commit: lint + compile + test on both runners |
| Backend | untouched — no `pytest` run needed and none claimed |

**One flake seen and chased down rather than waved away**: the first full-suite run had
`SugerenciasPanel.test.tsx > creates internal topic and submits management update` time out
at 10 s. Re-run alone: 7/7 green; re-run of the whole suite: 3807/3807 green. It is a
`userEvent` test hitting its own timeout under parallel load, in a file this slice does not
touch. Recorded because "it passed the second time" is only honest when you say it was
measured twice.

### O.2 — bundle gate (D12), MEASURED — **PASSES with 1429 bytes of headroom**

Same method, same machine, same session: clean `npm run build`, then
`find dist/assets -name '*.js' -exec sh -c 'gzip -9 -c "$1" | wc -c' _ {} \; | paste -sd+ - | bc`.

| point | commit | gzip sum | delta vs base | vs 3072 budget |
|---|---|---|---|---|
| slice-2 base (slice-1 post-fix head) | `d91e6f51` | 908422 | — | — |
| slice-2 head | `eb8c0861` | **910065** | **+1643** | **PASS** (1429 to spare) |

The base was REBUILT and re-measured here rather than carried over, and it reproduced the
recorded 908422 byte for byte — the same cross-check the slice-1 fix round ran.

The figure is a NET: task 2.10 deletes eight metric labels and a group-title entry, and
that deletion offsets part of what 2.7/2.8 add (the shared block, the six new metadata
line-builders, the three new formatters). Nothing was shaved to reach it and nothing was
padded: the measurement is what the slice weighs.

## Deviations from design — each with its evidence

1. **`available_through` leaves the hoistable set, so D5's field counts change from
   nine/seven to EIGHT/six.** This is the recorded arithmetic correction from tasks 2.2 and
   UXJB-201, executed rather than re-argued: the field is the INPUT of the per-metric
   evidence gate, and a date hoisted into a block that "vale para todas las métricas"
   cannot be gated per metric. `PROVENANCE_FIELD` therefore has eight entries and
   `design.md`'s Interfaces block, which still lists `AVAILABLE_THROUGH`, is stale on that
   one line. Same decision, corrected arithmetic.

2. **`RainfallDetailPanel.tsx` is edited, and slice 2's File Changes row does not list it.**
   Two lines of substance: it imports `hoistProvenance` + `snapshotMetrics` and passes the
   hoist to the antecedents `RainfallMetricGroup`. Without it D5's "antecedent rows print
   only what DIVERGES from the shared block" would be unimplementable — the antecedents
   fold mounts the group directly, not through the list — and those rows would repeat a
   block that already covers them, which is the six-identical-provenance-blocks defect one
   fold over. Listed here because a file outside the declared blast radius is what a
   reviewer should be told about rather than discover.

3. **`snapshotMetrics(snapshot)` is a new export of `RainfallMetricList.tsx`**, not in the
   Interfaces block. It is the group-detection logic (`renderedGroups` → `isMetricGroup`)
   reused to answer "which metrics does the shared block speak for", and it lives beside
   that logic on purpose: computing the comparison set with a second, hand-rolled key list
   is how the block and the renderer end up disagreeing about what is displayed.

4. **The spec-scenario test `exposes provenance: source, nominal resolution and revision`
   was MIGRATED, not kept byte-identical.** Slice 1's task 1.16 promised it would stay
   green untouched; slice 2's own hoist is what changes it. It now asserts the three fields
   inside the expanded technical fold (`shared ∪ row`) instead of inside one row. Asserting
   the row alone would now be asserting that the consolidation the requirement explicitly
   PERMITS did not happen — the test would be pinning the opposite of the spec.

5. **`metricLabel('duration')` no longer returns `'Duración del evento'`**, and the unit
   test that pinned it was re-expressed against the rule that actually governs now:
   degrade to the raw key. Forced by the 2.10 prune. The e2e CSV assertion is untouched and
   was verified to be a different string with a different owner — `P24h (mm en 24 h)` comes
   from the mocked `CSV_BODY`, i.e. the BACKEND's export label.

6. **Two fields of the enumerated floor needed a line that did not exist: temporal state
   and `fallback_used`.** Slice 1 rendered them only in the exceptional case (the
   `Provisional` / `Fuente alternativa` markers), so a `final`, non-fallback metric left
   two served fields unrendered while the delta requires every carried field. Added as one
   contract line, `Estado temporal: {state} · Origen: fuente primaria|alternativa`, on the
   same principle OWN-010 already established for the state chip: the marker is
   presentation, the text is the contract. Cost, stated: on an exceptional row the fact
   appears twice, once coloured and once in the contract line.

7. **`R2-001` (info) is discharged as a side effect, deliberately.** The comments in
   `RainfallMetricList.tsx` and `RainfallDetailPanel.tsx` claimed the R6 catch-all was
   present while the code iterated a hardcoded three-key list. Task 2.10 makes the claim
   true; both comments were rewritten to describe the mechanism that shipped rather than
   the one that was coming. `R3-004`'s coupling note was respected: `canFallBack` was not
   touched.

## Author counterexample self-check

| Category | Evidence | Result |
|---|---|---|
| Null / absence | The stripped four-field shape (no provenance, no coverage, no intervals) renders state + reason and nothing else, pinned by its own test asserting the ABSENCE of nine labels plus `undefined`/`null`/`NaN`; empty `quality` and empty `discrepancies` render no line; an unserved `source_health` renders no placeholder; an empty hoist renders no block | Pass |
| Boundaries | The hoist is pinned at all-equal, mixed, one-stripped, all-stripped and empty sets; `stringifyUnknownFields` at scalar, nested, array, `null`, function and zero-pair inputs; `metricEvidenceLine` at all three branches plus the policy-suppressed counterexample | Pass |
| Concurrency / idempotency | N/A — no new async work, no new writer, no new state. Every function added is pure and every render path is a function of the served snapshot | Pass |
| Malicious input / security | No new input surface and no authorization change. The one hardening is the opposite direction: `isMetricGroup` is total over `unknown`, so a scalar or `null` under a new root key is ignored instead of throwing `TypeError` and taking the panel down | Pass |
| Partial failure / recovery | A metric rejected by contract/policy/quality no longer poisons the hoist (it leaves the comparison set), so one rejection cannot collapse the consolidation for every other metric | Pass |
| State / tenancy / time | The exclusive→inclusive day conversion still has ONE implementation; `metricEvidenceLine` reuses `lastEvidenceDay` rather than re-deriving it, and its sentence is metric-scoped so it cannot be confused with the analysis-scoped one | Pass |

## Not run, and not claimed

O.1 (the declared local e2e run of D13) remains owner-gated and was NOT executed here, so
task 2.12's assertion is COLLECTED but not EXECUTED. A skipped run is a failed gate, not a
pass; this record claims only that the witness exists and that the spec collects.

## Push status

Not pushed. Every commit is LOCAL, per the orchestrator's instruction to leave pushing to a
full environment (the worktree's pre-push hook is broken and `--no-verify` was not used).

## Judgment Day fix round 1 (2026-08-12) — UXJA2-001, the suppressed annual total

One owner-approved fix, one file of source and one file of tests.

**What was wrong**: the delta scenario "The year's value is suppressed by policy but its
evidence exists" (`spec.md:165-171`) has THREE `THEN` clauses; the card implemented two.
A suppressed `annual.selected` printed `Acumulado hasta el {día}: —` and nothing else —
no state word, no reason — while the percentile's identical situation got a full
`Percentil histórico: Suprimida: {motivo}` line on the same always-visible surface. The
`withheld` branch existed; it was scoped to the percentile only.

**What shipped** (`consorcio-web/src/components/map2d/rainfall/RainfallAnswerCard.tsx`):

- `readablePercentile` → `readableMetric` (`:65`). ONE predicate, consulted by both lines.
  A second, hand-written readability test for the total is how the two lines would start
  disagreeing about what "withheld" means — the same single-source rule the slice already
  paid for with `snapshotMetrics`.
- `withheldSelected` (`:156-157`), derived exactly like `withheld` is.
- The new dimmed line (`:198-202`), placed ADJACENT to the percentile's so the two read as
  one family: `Acumulado del año: No disponible: coverage_below_threshold`.
- The `—` inside `AnnualText` is untouched on purpose. That is the VALUE slot and the value
  is unknown; the new line is the STATE and the reason. Removing the dash would have
  removed the only thing telling the reader a number was expected there.
- The file header's "what this card refuses to do" clause now says metric, not percentile.

**Strict TDD, both directions** (`consorcio-web/tests/unit/RainfallAnswerCard.test.tsx`):
`states a withheld selected total by state and reason, never as a number` and `adds no
state line when the selected total is readable`. Written first, observed RED (1 failed /
34 passed), then GREEN (36/36 in the file). The negative test is the one that matters most:
it fails the lazy "just always render the state" fix, which would have parked a permanent
`Disponible` beside every healthy number — precisely the noise the closed evidence footer
was designed to refuse.

| gate | result |
|---|---|
| `npx vitest run` (full suite) | 279 files / **3810** tests, all passing (was 3808; +2 new) |
| `npm run typecheck` | exit 0 on both tsconfigs |
| `npm run lint` | **3** warnings — the same pre-existing three, none added |
| bundle (D12 method) | **910207** vs slice-2 base `908422` → **+1785 / 3072** — PASS, 1287 B of headroom. This fix costs **+35 B** over the +1750 pre-fix delta. Measured, not shaved. |

The five remaining judgment-day findings are `info` and were NOT touched: three assessed
real (freshness reason on a name-prohibited role, the `??` coalesce that lets a stripped
metric swallow the `Fuente:` line, the provisional chip on a final-with-fallback row that
is owner-ratified copy) and two theoretical (the unguarded antecedents row path, the
hardcoded `ANTECEDENT_ORDER` in the collapsed header). Each is recorded in
`review-ledger.md` with its evidence, and none of them blocks.
