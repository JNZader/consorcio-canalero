# Review ledger — `lluvia-ux-tarjeta`

Artifact store: hybrid (this file + Engram topic `sdd/lluvia-ux-tarjeta/*`).

## Design phase — Judgment Day (two blind judges, round 1)

Reviewed: `proposal.md`, `design.md`, `specs/rainfall-analysis/spec.md` against the base
capability `openspec/specs/rainfall-analysis/spec.md` and the code the design commits to.
Two independent blind judges (A and B). Their convergence satisfies adversarial
verification — no `review-refuter` fan-out was spawned.

### Convergence map

| Judge A | Judge B | Same defect? | Canonical id used below |
|---|---|---|---|
| — | UXJB-001 | B-only (BLOCKER) | UXJB-001 |
| UXJA-002 | UXJB-002 | yes — freshness absent from the card / duplicated across surfaces | UXJA-002 ≡ UXJB-002 |
| UXJA-003 | UXJB-003 | yes — "presented once" is unsatisfiable as written | UXJA-003 ≡ UXJB-003 |
| UXJA-004 | UXJB-004 | yes — D7 keyed on role, not on rendered content | UXJA-004 ≡ UXJB-004 |
| UXJA-001 | UXJB-005 | yes — the field floor is unbounded / incomplete | UXJA-001 ≡ UXJB-005 |
| — | UXJB-006 | narrower half of the same defect (`interval_*`) | folded into UXJA-001 |
| — | UXJB-008 | mechanism notes on the D7 fix | folded into UXJA-004 |
| — | UXJB-007 | unit-test migration cost | folded into UXJA-018 (D11) |
| — | UXJB-011 | soft-skip vs `requireCondition` | folded into UXJA-008 |

Five BLOCKER/CRITICAL defects survived both sweeps (one BLOCKER + four CRITICAL — the
round-1 text said "four", counting only the CRITICALs); the WARNING batch is judge-A-heavy
because judge B spent its sweep budget on them. Nothing was refuted.

### Entries

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| UXJB-001 | judgment-day | `design.md` D1/D2, Data Flow | BLOCKER | fixed | The delta's own ADDED requirement lists freshness among the four facts the answer surface must carry, and the card carried percentile + total + normal only. The always-visible surface therefore could not satisfy the requirement the same change introduced. Fixed by D1a: the panel derives freshness ONCE (`deriveFreshness`, reusing `lastEvidenceDay`) and passes it to the card, whose props contract becomes `{ snapshot, freshness }`; `rainfall-freshness` joins the card's content in the Data Flow section. |
| UXJA-002 ≡ UXJB-002 | judgment-day | `design.md` D1, D9; `RainfallAccumulationChart.tsx:303-310,450-453` | CRITICAL | fixed | Two differently-sourced dates would have described "the same" fact: the chart footer converts the LIVE `/series` `available_through`, the technical fold the STORED snapshot's. They diverge exactly in the case `rainfall-series-stale` exists to announce. Fixed by the D1a ownership table (card = the analysis, chart = the series it drew, fold = per-metric inspection over the same stored snapshot) plus D9a's rules: same source, same gate, no invented rows (round 2 added a fourth: one stringify guard for `quality` and `source_health`). The chart keeps its footer because the base requirement "Chart Discloses Comparison Date and Freshness" demands it of the chart — a different object, not a duplicate. |
| UXJA-003 ≡ UXJB-003 | judgment-day | `specs/rainfall-analysis/spec.md` ADDED "Answer-First…" | CRITICAL | fixed | "The percentile MUST be presented once" contradicted the base requirement that the chart's textual equivalent restate it, so the delta could not be satisfied and passed at the same time. Reworded to name the offending occurrence: headline required, badged metric row on the same always-visible surface forbidden, restatement inside the textual equivalent explicitly not a duplication. The scenario now asserts one headline + one textual-equivalent occurrence + no badged row above the fold. |
| UXJA-004 ≡ UXJB-004 | judgment-day | `design.md` D7; `FichaTerritorialPanel.tsx:496,523,534,606` | CRITICAL | fixed | `defaultOpen={!staff}` collapsed the public normal for a staff reader on a NON-parcela ficha — a reader who gets no v2 detail at all, so the fold hid that reader's only rainfall content, which is exactly what the modified requirement forbids. Re-keyed on the content: `defaultOpen = !v2DetailWillRender` where the predicate is the v2 detail's exact mount condition (`staff && tipo === 'parcela' && !!nomenclatura`). Two mechanism notes from UXJB-008 folded in: the `useCanAccess` call sits above the `:523`/`:534` early returns (a conditional hook would change hook count on the loading→result transition and crash the ficha), and a `key` on the section forces the remount that `CollapsibleSection.tsx:69`'s one-shot `useState(defaultOpen)` otherwise makes impossible after auth hydration. |
| UXJA-001 ≡ UXJB-005 (+UXJB-006) | judgment-day | `specs/rainfall-analysis/spec.md` MODIFIED "Metric Provenance…"; `design.md` D5/D9 | CRITICAL | fixed | "A served field MUST NOT remain unrendered" named no fields, so it could be neither satisfied nor falsified — and the design's rendered set silently omitted `interval_start`/`interval_end`, which every metric carries (`lib/api/rainfall.ts:61-62`). Narrowed to an ENUMERATED floor bound to what the snapshot serves, with `source_health` placed at the analysis (it is a snapshot root key, `lib/api/rainfall.ts:94`), a bind-when-served clause (no fabrication, no placeholders), and a clause forbidding `available_through` from being shown as evidence for a metric that has none. D5 adds `interval_*` to the never-hoisted set (they are what distinguishes d7 from d90); D9 renders them per row. |
| UXJA-007 | judgment-day | `consorcio-web/package.json:23`; `.github/workflows/` | WARNING | info | `tests/e2e/rainfall-v2-detail.spec.ts` runs in NO CI job: `test:e2e:canary` names three other spec files and no workflow runs `test:e2e:prod`. Every R4 claim rested on a suite nothing executes. Round 1 answered it by appending the spec to the canary file list — a prescription round 2 REFUTED and withdrew (see R2 `UXJA-104 ≡ UXJB-102` / `UXJA-105 ≡ UXJB-103`, which re-close the underlying observation via design D13). |
| UXJA-008 (+UXJB-011) | judgment-day | `design.md` Testing Strategy; `MapPanelShell.tsx:253` | WARNING | info | The zero-scroll criterion had no element to measure against — the sheet's scrolling body carries no testid. `MapPanelShell.tsx` added to File Changes for one added `data-testid="${testId}-sheet-body"`, and the assertion is gated with `requireCondition`, not `skipForMissingData`: a criterion that skips itself when the box it measures is missing measures nothing. Round 2 kept the gate and named the environment where `requireCondition` actually bites (D13). |
| UXJA-009 | judgment-day | `design.md` D4, Testing Strategy | WARNING | info | The boundary table covered 10 and 70 from both sides but 30 and 90 from one, so a rounding error at those two cut-offs would pass. Added 30.6, 89 and 89.4. |
| UXJA-010 | judgment-day | `design.md` D2 | WARNING | info | "values in `rightAccessory`" was the whole specification of a header the spec delta makes a contract. D2a specifies it: fixed order, unit stated once, non-available → `—` with the reason in `title`/`aria-label`, truncation behaviour at 348 px. (Round 2 corrected the formatter D2a named — see `UXJB-104 ≡ UXJA-106`.) |
| UXJA-011 | judgment-day | `design.md` D6 | WARNING | info | The controlled/uncontrolled chart shipped two behaviours of which only one would ever run. Now controlled-only with REQUIRED props; the `renderChart()` helper (`RainfallAccumulationChart.test.tsx:230`) update is listed as a slice-1 task instead of being discovered during apply. |
| UXJA-012 | judgment-day | `design.md` D6 | WARNING | info | The controls row's relationship to the snapshot gate was unstated, and the drafted placement would have rendered the campaign preset during loading/queued — a live control windowing a series that does not exist. Stated: scope/year outside the gate (unchanged), preset with the chart inside it. |
| UXJA-013 | judgment-day | `design.md` D8 | WARNING | info | `isMetricGroup` used `'metric' in value` without a `typeof` guard; a scalar under a new root key would throw `TypeError` and take down the panel — the opposite of R6's intent. Guard made total (`null`/`typeof`/`Array.isArray` before any `in`), with the crash case pinned by a unit test. |
| UXJA-014 | judgment-day | `design.md` D8; `tests/e2e/rainfall-v2-detail.spec.ts:147-148,161` | WARNING | info | "The e2e fixture is the live witness of the unknown-group fallback" was false: the fixture carries `intensity.p24h`, but the only assertion touching it is the CSV export row. Slice-2 task added to assert the raw group renders in the expanded technical fold. |
| UXJA-015 | judgment-day | `proposal.md` R4 + success criteria | WARNING | info | The testid count came from the exploration (13) and was short by `rainfall-accumulation-lag` and `rainfall-regional-estimate`; the spec also depends on `ficha-precipitacion`. Corrected to 15 + 1 in both places. |
| UXJA-016 | judgment-day | `design.md` D12 | WARNING | info | "The SUM over emitted JS … is what a first visit pays for" is false — a first visit pays the entry chunk plus its static imports, and this app lazy-loads routes. The gate stays (the sum is the only build-stable figure) but is restated as a regression tripwire, not a page-weight model. |
| UXJA-017 | judgment-day | `proposal.md` Out of Scope | WARNING | info | Exploration finding #7 (regional analysis reachable only through ONE parcel; no polígono/canal/multi-parcela/zone entry) had disappeared from the artifacts. Recorded explicitly as deferred to direction C, with what this change DOES do about it (R1 labelling) stated so the deferral is not read as a fix. |
| UXJA-018 (+UXJB-007) | judgment-day | `design.md` D11 | WARNING | info | "~330 / ~280 changed lines" had no denominator and excluded tests, while the review tier is decided on the whole diff. Restated as source + tests + total, with the forced test edits listed per file — including that two of the five moved `AnnualText` tests are NOT verbatim moves — and the consequence recorded: slice 1 is reviewed at the full 4R tier. |

**Status normalization (applied in round 2).** Round 1 wrote `fixed` on every WARNING row. The canonical contract reserves the fix → re-review loop for BLOCKER/CRITICAL and records WARNING/SUGGESTION once with status `info`; the eleven rows above are therefore `info`, whatever edit they happened to receive. Only the five BLOCKER/CRITICAL rows keep `fixed`.

### Question adjudications

| Q | Question | Resolution | Authority |
|---|---|---|---|
| Q1 | D3 — does "printed once" forbid the percentile's restatement inside `rainfall-annual-text`? | No — but round 1 closed it on a FABRICATED authority: "Chart Discloses Comparison Date and Freshness" (`openspec/specs/rainfall-analysis/spec.md:464-468`) governs the series' two dates and says nothing about the percentile or a textual equivalent. Re-closed in round 2 on this change's own "Progressive Disclosure Without Data Loss", which now requires the equivalent to stay COMPLETE — ranking included — for readers who cannot see the plot (R2 `UXJA-103 ≡ UXJB-106`). | both judges (UXJA-003 ≡ UXJB-003), authority corrected in round 2 |
| Q2 | D4 — are 10/30/70/90 approved as published, user-visible vocabulary? | Ratified 2026-08-11: ≤10 muy seco · 11-30 seco · 31-69 normal · 70-89 húmedo · ≥90 muy húmedo, over the ALREADY-rounded percentile, no label when suppressed. Judge-endorsed as stable given the ~3-point Weibull step; the design now discloses the n-variability (3.125 points at n=30, 4.545 at n=20) and pins every boundary from both sides. | owner, endorsed by both judges |
| Q3 | D2 — is `Antecedentes` collapsed on desktop too? | Ratified 2026-08-11: collapsed at every size, values visible in the collapsed header. Judge condition attached and now met: the header's content is specified (D2a) rather than left to implementation. | owner + UXJA-010 |
| Q4 | D9 — should the delta state that a field with no producer renders only when present? | Yes, and generalised: the floor is now enumerated and bound to what the snapshot serves, `source_health` is placed at the analysis level, and fabrication/placeholders are forbidden. The narrow question about one field was a symptom of the unbounded clause behind UXJA-001 ≡ UXJB-005, and is closed by the same edit. | both judges (UXJA-001 ≡ UXJB-005, UXJB-006) |

### Surfaces both judges verified clean (no finding — do not re-litigate)

- **R7 / textual equivalent**: moving `AnnualText` above the first fold is structurally correct; `CollapsibleSection.tsx:113` unmounts its body when closed, and the design's placement is what keeps the equivalent out of that region.
- **D5 hoist semantics**: per-field, strict equality over a non-empty set, `coverage`/`completeness` never hoisted — satisfies both halves of the success criterion, and `shared ∪ row` preserves inspectability.
- **D10 `lastEvidenceDay` reuse**: the exclusive→inclusive conversion and its single-implementation rule are correct; verified against `compute.py:339,455`.
- **R5 / no new dependency**: `CollapsibleSection` + recharts only; no route, no backend, no contract change.
- **Rollback**: frontend-only render-tree change, slice 2 revertible independently; no flag, correctly justified.
- **The `null` ≠ 0 discipline** carried into the card, the adjective and the collapsed header.

### Round outcome

Round 1 of the design-phase convergence budget. Five BLOCKER/CRITICAL entries and the
WARNING batch addressed in this round, in the artifacts only — no application code was
touched. BLOCKER/CRITICAL status: `fixed`. WARNING status: `info` (normalized in round 2).
Nothing is `open`.

Scoped re-judge input: this ledger plus the artifact diff (`design.md`,
`specs/rainfall-analysis/spec.md`, `proposal.md`, this file).

## Design phase — Judgment Day (two blind judges, round 2 — FINAL)

Scoped re-judge of the round-1 fix diff against this ledger. Two blind judges again (A
and B); their convergence satisfies adversarial verification, so no `review-refuter`
fan-out was spawned. Round 2 is the LAST round of the convergence budget: anything not
closed here is reported to the user as open.

### Convergence map

| Judge A | Judge B | Same defect? | Canonical id used below |
|---|---|---|---|
| UXJA-101 | UXJB-101 | yes — the freshness gate conflates policy suppression with evidence absence | UXJA-101 ≡ UXJB-101 |
| UXJA-104 | UXJB-102 | yes — the canary append breaks a production-safety allowlist | UXJA-104 ≡ UXJB-102 |
| UXJA-105 | UXJB-103 | yes — the same wiring would not have executed one assertion | UXJA-105 ≡ UXJB-103 |
| UXJA-102 | UXJB-107 | yes — "derived once for the whole view" conflates two subjects | UXJA-102 ≡ UXJB-107 |
| UXJA-103 | UXJB-106 | yes — the percentile rule rests on a citation that says no such thing | UXJA-103 ≡ UXJB-106 |
| UXJA-106 | UXJB-104 | yes — D2a's collapsed header cannot come from `formatAccumulated` | UXJB-104 ≡ UXJA-106 |
| — | UXJB-105 | B-only (WARNING) — `source_health` had no render rule | UXJB-105 |
| — | UXJB-108 | B-only (WARNING) — the D7 predicate under degraded v2 states | UXJB-108 |
| A's nit | UXJB-109 | yes — D7's ":606, same three conjuncts" is a wrong citation | UXJB-109 |
| — | UXJB-110 | B-only (WARNING) — the hoist's comparison set is unguarded | UXJB-110 |
| UXJA-107 | — | A-only (WARNING) — antecedent provenance had no stated home | UXJA-107 |

### Entries

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| UXJA-101 ≡ UXJB-101 | judgment-day | `design.md` D1a, D9a rule 2, Data Flow; `specs/rainfall-analysis/spec.md` ADDED + MODIFIED | CRITICAL | fixed | Round 1's gate keyed the no-evidence branch on `annual.selected` being `available`/`partial` — a POLICY state. `apply_metric_policy` (`policy.py:166-167`) suppresses a metric for `coverage_below_threshold` while `_normalize_metric` (`service.py:493,518`) keeps its `coverage`, `provenance` and `interval_*` intact, so a 62 %-coverage year would have printed "Sin días con evidencia publicada" directly above a chart footer declaring evidence through the same day: two visible surfaces contradicting each other on one screen. Replaced with a three-branch EVIDENCE gate — `coverage > 0` (or a served numeric value) → the real date; `state === 'unavailable' && reason === 'no_data_in_disclosure_window'` (`compute.py:649-650`) → the no-evidence sentence; neither (absent, or `service._unavailable`'s stripped four-field shape at `service.py:466-472`) → a third, indeterminate sentence that asserts neither. `deriveFreshness` returns the branch (`kind`) so nothing keys on sentence text. D9a rule 2 inherits the same gate per metric; the delta gains "suppression is not absence" in both requirements plus two scenarios (policy-suppressed keeps its freshness; freshness cannot be established). |
| UXJA-104 ≡ UXJB-102 | judgment-day | `design.md` D13 + File Changes; `proposal.md` R4 + Affected Areas; `gee-backend/tests/test_ci_workflow_contracts.py:815-859` | CRITICAL | fixed | The round-1 prescription — append the spec to `test:e2e:canary` — widens `CANARY_READ_ONLY_SPECS`, the allowlist whose own docstring says adding a spec "must break this list on purpose", and would have dragged `gee-backend/**` into a change whose File Changes table promises it is untouched. WITHDRAWN: `package.json`'s canary script is unchanged, no workflow is touched, and the reasoning is recorded in the new D13 so nobody re-proposes it. |
| UXJA-105 ≡ UXJB-103 | judgment-day | `design.md` D13, Testing Strategy; `proposal.md` success criteria 1 and 6 | CRITICAL | fixed | The same append would also have been INERT: `gotoAndOpenFicha` probes `E2E_API_BASE ?? localhost:8000`, the canary passes no `E2E_API_BASE` (its own contract test forbids it), so `skipForMissingData` skips every test in the describe — a green job asserting nothing, which is the defect UXJA-007 named. The prescribed replacement (a `vite preview` step in `frontend.yml`) was evaluated and refuted on evidence: `clickFixtureParcela` needs a real `parcelas_catastro` tile `200` from Martin plus a reachable backend, neither of which a preview serves, so it skips identically — and `test_ci_workflow_contracts.py:799-808` forbids the strings `test:e2e` / `tests/e2e` / `PLAYWRIGHT_BASE_URL` in `frontend.yml`, making it a `gee-backend` change too. D13 states what verifies what instead: R4 is CI-gated at the unit layer (`RainfallDetailPanel.test.tsx`), the zero-scroll `requireCondition` case runs in a declared local environment (`E2E_APP_URL` + `E2E_API_BASE` against `docker compose up postgres backend martin`) as a slice-1 merge gate, named by one added npm script, and the artifacts now say plainly that CI does not gate zero-scroll. |
| UXJA-102 ≡ UXJB-107 | judgment-day | `specs/rainfall-analysis/spec.md` ADDED "Answer-First…"; `design.md` D1a | CRITICAL | fixed | "Derived once for the analysis rather than per rendering surface" and the scenario's "converted once for the whole view" forbade the chart footer the base requirement mandates — the delta contradicted itself in the same paragraph that D1a's ownership table resolves correctly. Scoped by SUBJECT: one derivation per subject (analysis → card + fold, from the stored snapshot; series → chart, from the series response), two derivations for the SAME subject forbidden, divergence disclosed rather than averaged. The scenario now asserts both statements. D1a's heading and lead sentence say "once per subject" instead of "nothing below converts a date again", which the chart always contradicted. |
| UXJA-103 ≡ UXJB-106 | judgment-day | `specs/rainfall-analysis/spec.md` ADDED + "Progressive Disclosure…"; `design.md` D3, Q1; `proposal.md` Approach 1 | CRITICAL | fixed | The percentile rule cited "Chart Discloses Comparison Date and Freshness" as requiring the textual equivalent to restate the percentile. It does not: `openspec/specs/rainfall-analysis/spec.md:464-468` governs the comparison end date and the last day with evidence for the plotted series, and mentions neither the percentile nor a textual equivalent. The delta rested a MUST NOT on a sentence that does not exist. Re-grounded on this change's own "Progressive Disclosure Without Data Loss", which now requires the equivalent to remain COMPLETE — stating the facts the plot conveys visually, ranking included, so a non-visual reader gets the same information, not a subset. The fabricated citation is removed from all four sites and the round-1 Q1 adjudication is annotated instead of quietly rewritten. |
| UXJB-104 ≡ UXJA-106 | judgment-day | `design.md` D2a, Interfaces, Testing Strategy | WARNING | info | D2a claimed the header's values are "rounded by the same `formatAccumulated` the rows use"; that function is `value.toFixed(1) + ' ' + unit` (`rainfallFormat.ts:56-58`), i.e. `31.0 mm` — a decimal and three repeated units in a 348 px slot. A one-line `compactAntecedent` (`Math.round`, no unit, `—` when absent) is defined instead, the rows keep `formatAccumulated`, the width note is recomputed from the actual string (26 chars, 29 with three-digit values — the old "~24" omitted the trailing unit), and the unavailable-LAST case (`… 90d — mm`) is accepted explicitly with the reason carried in `aria-label`. |
| UXJB-105 | judgment-day | `design.md` D9 table, D9a rule 4 | WARNING | info | `source_health` is typed `unknown` and had a row but no render rule, so an object would have printed `[object Object]` — the failure `quality` already has a guard for. One stringify guard now serves both: scalar pairs in key order, `null`/arrays/nested objects skipped rather than coerced, a non-object input printed as itself, zero pairs → no line (rule 3). |
| UXJB-108 | judgment-day | `design.md` D7 | WARNING | info | `v2DetailWillRender` is true even when the v2 detail renders only a queued/error/unavailable state, so the public chart collapses under a thin detail. Adjudicated CONFINED and accepted: the fold header stays visible, so the public normal is one click away, and the spec clause protects the reader for whom it is the ONLY content. Keying on rendered richness would make the default flap with a poll's answer. No predicate change; the trade is now recorded in D7 instead of being discovered later. |
| UXJB-109 (+ A's nit) | judgment-day | `design.md` D7 code block; `FichaTerritorialPanel.tsx:606`, `RainfallDetailPanel.tsx:133` | WARNING | info | The comment claimed ":606 — same three conjuncts". Only two live there (`tipo === 'parcela' && parcelaProps?.nomenclatura`); the staff conjunct is `if (!canAccess) return null` inside `RainfallDetailPanel.tsx:133`. The predicate is correct and unchanged; the citation now names both homes, so whoever implements it can verify the claim instead of trusting it. |
| UXJB-110 | judgment-day | `design.md` D5 | WARNING | info | `hoistProvenance` compared the whole displayed set, including metrics served in `service._unavailable`'s stripped shape (`service.py:466-472`), which carry no provenance at all — one rejected metric would make every field diverge and put six identical provenance blocks back on the rows, defeating the decision. D5 now excludes provenance-less metrics from the comparison set (the same total-guard discipline D8 applies) and renders their stripped state per D9a rule 3; the empty-set case falls out of the same rule. |
| UXJA-107 | judgment-day | `design.md` D5 | WARNING | info | The shared block was scoped "de esta sección" while the antecedents live in a DIFFERENT fold, leaving their provenance homeless. Stated explicitly: the block covers ALL displayed metrics of BOTH folds and says so; antecedent rows print only divergent fields. The at-most-one-control floor holds because the control need not be the same one for every field — a reading now written into the delta sentence rather than inferred. |
| — (info nit, no judge id) | judgment-day | `design.md` D8 deny-list; `service.py:201-221` | SUGGESTION | info | `metric_policy` is a root key of the server's own envelope and is copied through by `normalize_snapshot`, though `RainfallAnalysisSnapshot` does not declare it. The total guard rejects it correctly today (thresholds and strings are not metric-shaped), so listing it changes no behaviour; it is listed because "the guard happens to reject it" is weaker than "we know this key and it is not a group". |

### Round outcome — FINAL

Round 2 of 2. Five CRITICAL entries fixed and the six WARNING/SUGGESTION entries recorded
at `info`, in the artifacts only — no application code was touched in either round. The
two items round 1 did not truly resolve are re-closed here: UXJA-007 (the e2e spec runs
nowhere) via `UXJA-104 ≡ UXJB-102` + `UXJA-105 ≡ UXJB-103` and design D13, and the Q1
authority via `UXJA-103 ≡ UXJB-106`.

**Nothing is `open`.** One deviation from the round-2 prescription is recorded rather than
hidden: the prescribed replacement wiring (a `vite preview` e2e step in `frontend.yml`) was
refuted on evidence during the fix and replaced by the declared-local-environment gate of
D13, because the spec's ficha preamble soft-skips without a backend and live catastro
tiles, and `test_ci_workflow_contracts.py:799-808` forbids the required strings in
`frontend.yml` anyway. The verification claim the prescription was protecting — that no
assertion in these artifacts rests on a suite nothing runs — is met by D13's what-verifies-what
table, which names the one criterion CI does NOT gate instead of implying it does.

Convergence budget for the design phase is now spent.

## Design JD — terminal verdict + post-JD housekeeping (2026-08-11)

**Final re-judge: A NOT CLEAN (UXJA-201 open) · B CLEAN.** The contradiction was resolved by orchestrator execution, per this project's precedent: Judge A's two blocking facts verified against the tree (`app/config.py:124` `ficha_enabled: bool = False`; no `FICHA_ENABLED` in any compose/env file; the martin service is docker-network-only with no published host port). **JUDGMENT: ESCALATED** at the convergence budget's end, with UXJA-201 the sole open item.

**Post-JD housekeeping (owner-approved "dale", same pattern as lluvia-insights' pre-verify tidy — explicitly NOT a review round):** D13's declared local run gained the two missing preconditions as items 4 and 5 (FICHA_ENABLED reaching the backend service; a host-reachable Martin via port override or VITE_MARTIN_URL), citing the previous change's own apply record where both blockers were first documented. UXJA-201 → `fixed (post-JD housekeeping)`. Also fixed in the same edit: the D11 stale figure ~540→~590 (UXJA-202≡UXJB-204).

**Ledger row added in the verify phase (V-009).** UXJA-201 was the sole open item at the convergence budget's end and was resolved in prose only — no table row, while every other finding of that weight got one. A resolution recorded exclusively in narrative is the one a future reader has to reconstruct, and an escalation is the last finding that should require reconstruction:

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| UXJA-201 | judgment-day | `design.md:271` (D13 declared local run) with `gee-backend/app/config.py:124` and the `docker-compose.yml` martin block | CRITICAL | fixed | The design's declared local e2e environment listed THREE preconditions while the tree imposes FIVE. Two blockers were verified against the tree by orchestrator execution, not accepted on the judge's word: (a) `ficha_enabled: bool = False` at `app/config.py:124`, with no `FICHA_ENABLED` in any compose or env file in the repo — so `probeFichaAvailability` returns `'off'` and EVERY test in the spec soft-skips; (b) the `martin` compose service publishes no host port while the SPA resolves tiles from `VITE_MARTIN_URL \|\| 'http://localhost:3000'` — so `clickFixtureParcela` never gets its `parcelas_catastro` 200 and the zero-scroll case skips. A declared environment that cannot produce a green is a gate that reports skips as passes, which is this criterion's three-strikes failure mode (canary → preview → local) for the third time. **Fixed** by adding both as explicit preconditions 4 and 5 of D13 (`design.md:271`) and to task O.1 (`tasks.md:132-137`), each citing the previous change's own apply record (`openspec/changes/archive/2026-08-07-lluvia-v2/apply-progress.md:245`) where both blockers were first documented. The fix is DOCUMENTARY, and that is the whole point of the distinction the verify phase preserves: naming the preconditions is what makes O.1 executable, it is not the same thing as executing it. O.1 remains unchecked and V-001 remains OPEN. |

**Escalation resolved → the design proceeds to tasks.** The verify phase MUST confirm the declared run actually executes end-to-end with the five preconditions (the three-strikes history of this gate — canary, preview, local — earns it an executed check, not an inspected one).

## Apply phase — owner-reported defects on the live UI (2026-08-11)

Not a review round: three defects the OWNER found on the deployed surface, with
screenshots, while slice 1 was being applied. Recorded here because they are fixes to
the same surfaces slice 1 rewrites, and because "the owner looked at it" is the one
verification channel no lens replaces. Folded into slice 1 as tasks 1.24-1.26 rather than
deferred: a slice that reorders this surface and leaves an unusable control on it has not
fixed the reader's problem.

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| OWN-001 | owner | `RainfallDetailPanel.tsx` scope control | CRITICAL | fixed | The control labelled every option with `RAINFALL_SCOPE_LABELS[choice.kind]`, i.e. the KIND. Screenshot 1: `Zona \| Cuenca \| Cuenca`. Screenshot 2, escalating it: a Bell Ville parcel (nomenclatura 3603403896547762) resolves to FIVE scopes and rendered `Zona \| Zona \| Cuenca \| Cuenca \| Cuenca` — a control that cannot be operated correctly, only guessed at. `RainfallScopeChoice` is `{kind,id,version}` with no served display name, so the qualifier is the prettified `id`, applied per SET (a choice is qualified iff another choice shares its kind, so the ordinary zone+basin pair keeps reading `Zona \| Cuenca`). **Amends D6 on the component**: five segments cannot fit the panel's 348 px, so `SegmentedControl` is used only at ≤3 choices whose labels fit a character budget derived from that width, and above it the control is the `NativeSelect` the year already uses. Forcing five segments into one row would have reproduced OWN-003 at the container level. Tasks 1.24; `scopeChoiceLabel` / `scopeChoiceLabels` / `shouldUseSegmentedScope` in `rainfallFormat.ts` with their own boundary tests, plus two panel tests (five-choice select branch, two-choice segmented branch). |
| OWN-002 | owner | `RainfallDetailPanel.tsx` queued alert + `aria-live` | CRITICAL | fixed | Backend job identifiers were pasted into user copy: `Análisis en preparación: role:daily, analysis_missing. Se actualiza automáticamente.` Both the alert and the announcement now state ONE human sentence, and the served labels move to a `data-queued-labels` attribute — still inspectable, no longer addressed to a person. The "never a silent spinner" rule is intact: the alert still exists, still names what is happening and still promises the update the poll delivers. Consequence recorded rather than rounded away: a label that HAPPENS to be human (`Procesando base histórica`, in the e2e fixture) also stops rendering. The alternative — a heuristic that renders "human-looking" labels — passes `role:daily` the day the backend adds a space to it. Task 1.25. |
| OWN-003 | owner | `RainfallMetricList.tsx` metric row | CRITICAL | fixed | Three badges per row (`Provisional`, `Fallback`, and a state badge carrying `describeMetricState` — the state AND its reason) competed for one `nowrap` row in the 380 px panel and all three ellipsized: `PROVISIO… FALLB… DISPONI…`. A truncated badge is worse than none — unreadable, and still looking like data. ONE badge now, carrying the state WORD via the new `metricStateLabel`; the reason gets its own `Motivo:` line and the two flags become plain markers on the metadata line; the row wraps instead of squeezing. Nothing is dropped — every fact is still on the row, in full words. Falsified in jsdom by the CONTENT BOUND that makes truncation unreachable (exactly one `[data-metric-state]` element, whose text is a full vocabulary word), NOT by a faked pixel measurement — jsdom has no layout and the test says so. Task 1.26. |

## Apply phase — second external UX review + owner decisions (2026-08-11)

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| OWN-004 | external UX review | `RainfallAnswerCard.tsx` `AnnualText` | CRITICAL | fixed | `Año 2026: 503.4 mm` reads as a CLOSED annual total. In August it is eight months of accumulation, and a reader quoting it at an asamblea would be quoting a number that does not exist. The phrase now states its cut: `Acumulado hasta el {día}`, where the day is the analysis' own last day WITH evidence — taken from the `freshness` value the panel already derived, NEVER from the browser clock, which knows nothing about what the provider published. With no evidence day it degrades to `Acumulado parcial del año {Y}`: no fabricated date, and still no claim of a closed year. `annual.normal` is the normal accumulated TO THE SAME DATE, so it now says `al mismo período` while still naming the served baseline (RISK-001). Task 1.30(a)(b). |
| OWN-005 | external UX review | `FichaTerritorialPanel.tsx` fold title, `PrecipChart.tsx` | CRITICAL | fixed | Two "normal" numbers one fold apart — ~913 mm and ~512 mm — differing on BOTH period (full-year historical vs to-date) and scope (parcel clip vs zone/basin), with neither label naming either dimension. A reader compares them as if only one differed and reads the gap as rainfall. Now: the card states its cut date and its scope by name, the fold title reads `Lluvia histórica mensual (recorte de la parcela)`, and the public chart's headline reads `Total anual histórico (parcela)`. **No period is frozen in either title**: the normals' period is server-driven (`dataset.periodo`, printed by `precip-fuente`), and hardcoding `1991-2020` in a title would be the RISK-001 defect this repo has already paid for twice. Tasks 1.30(b)(f). |
| OWN-006 | external UX review | `RainfallDetailPanel.tsx` announcer | WARNING | fixed | The `aria-live` region was VISIBLE and restated whatever was already on screen, so `Análisis en preparación` printed twice, one line apart. It is now `VisuallyHidden`: still in the accessibility tree, still `aria-live="polite"`, still the same sentence — it simply stops being a second visible copy of the state it announces. Its ready wording also separated its two dimensions (`Análisis {Y} disponible · Alcance: {scope}`), because `…disponible para Zona 2026` runs scope and year together into something that reads like a place called "Zona 2026" and a listener has no layout to disambiguate it with. Task 1.30(d)(e). |
| OWN-007 | external UX review | `RainfallDetailPanel.tsx` queued alert | — | **not a defect — verified** | Reported as "red/alarming". VERIFIED against this branch: the queued alert is already `color="blue" variant="light"` (informative), and the only yellow alert is the TERMINAL gave-up state, which is a different fact. No change made and none claimed. The red the review saw is either the deployed build predating this slice, or the analysis-error text. Recorded rather than silently "fixed", because agreeing with a report that the code contradicts is how a real defect gets papered over. |
| OWN-008 | owner decision | `RainfallDetailPanel.tsx` | CRITICAL | fixed | An empty panel behind a spinner is a worse answer than last year's data. While the selected year is queued the panel now also requests `Y-1` and DISPLAYS it, with the alert becoming the notice that names both years and a `data-showing-year` attribute. **Exactly ONE step**: if `Y-1` is also queued the ladder stops — a fallback that keeps walking backwards turns one slow answer into a queue of them — and the year floor is 1991, the selector's own oldest option. **Side-effect recorded, not hidden**: the export buttons, the chart and the folds all read the DISPLAYED snapshot, so while the fallback is on screen they export and plot `Y-1`. That is correct (they describe what the reader is looking at) and it is exactly the kind of thing that becomes a bug report if it is not written down. Task 1.27. |
| OWN-009 | owner decision | `rainfallFormat.ts`, `RainfallAnswerCard.tsx` | WARNING | fixed | The percentile was unreadable three ways at once: the row rendered `46.9 percentil` (a rank is not a magnitude, so the unit is a PREFIX in Spanish — `Percentil 46.9`), the card said `Percentil 47` beside it (one fact, two spellings, on one screen), and neither told a reader what a percentile IS. Now every always-visible surface uses the same ROUNDED value while the technical row keeps the served precision, and a dimmed gloss reads `De cada 100 años, {n} fueron más secos que este.` — absent whenever the percentile is not readable, because an interpretation of a withheld number is the withheld number. Task 1.28. |
| OWN-010 | owner decision | `RainfallMetricList.tsx` | WARNING | fixed | Refines OWN-003. Chips are EXCEPTION-ONLY: an available, definitive metric shows none, a provisional or fallback-fed value shows exactly `Dato provisorio`, a non-available state shows its state word — full Spanish, never the wire token `FALLBACK` (the metadata line says `Fuente alternativa`). **The row's text now always states `Estado: {word}`**, which is the part that keeps this honest: the chip is presentation, the text is the contract, and dropping a chip must never drop a served field the enumerated floor requires (D9). The card's evidence footer is likewise closed to cut date + scope + short source, with coverage deliberately absent — a permanent `Cobertura: 100%` is noise on every healthy analysis. Tasks 1.26b, 1.29. |

**Info bequest for tasks/verify** (final re-judge rows, non-blocking): UXJA-203 (branch-3 metric rows drop a served available_through — one reconciling clause), UXJA-204/UXJB-202 (ledger count off-by-ones — noted here, correct at source when next edited), UXJA-205 (evidenceFooter is analysis-scoped; the fold's per-metric row needs its own string, not the shared one), UXJA-206 (three base-spec line citations stale by 11 lines post-f95bf8e5) — **DISCHARGED in the verify phase (V-008)**: the delta preamble's surviving stale citation, `spec.md:596` for "Intensity, Peak, and Duration Outcomes", was corrected to `:607` after locating the requirement heading live in `openspec/specs/rainfall-analysis/spec.md` rather than by re-applying the +11 arithmetic — the offset was the symptom, the heading is the fact, UXJB-201 (available_through must leave D5's hoistable set or the per-metric gate can't run — tasks should pin it to the rows), UXJB-203 (the card/footer strings don't name their subjects; the stale banner is the disclosure — acceptable, recorded), UXJB-205 (the spec's suppression-is-not-absence sentence over-broad vs its own scenario), UXJB-206 (FichaTerritorialRainfallMount.test.tsx missing from the forced-edit list), UXJB-207 (D9 table vs D9a rule 4 disagree on scalar source_health — rule 4 wins, table to be read accordingly).

## Slice 1 — full-4R code review (2026-08-12, diff 550dc852..18f6a1f6, ~3647 lines)

Four lenses in parallel (risk / readability / reliability / resilience), 2-sweep budget each. Risk returned an EMPTY ledger (authz boundary unchanged, no unsafe sinks, no policy-suppression leak, no PII — the cadastral nomenclatura in tasks.md is a public field, not personal data). Reliability and resilience independently converged on the SAME defect. Refutation: full-4R protocol, 3 batched refuters (correctness / exploitability-impact / reproducibility) over the merged CRITICAL list; vote 2-of-3 required to refute.

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| R3-001 | reliability | `consorcio-web/src/components/map2d/rainfall/RainfallDetailPanel.tsx:268-269,417,432-443,450-465,467` | CRITICAL | fixed | `snapshot = primarySnapshot ?? fallbackSnapshot` has no `gaveUp` term while the queued block owning the `Mostrando {Y-1}` notice + `data-showing-year` is gated on `!analysis.gaveUp`. After the 12×5s poll budget the panel renders the full Y-1 card/chart/export under a year selector reading Y beside a contradictory "Análisis no disponible aún" alert, with the substitution notice removed. Ordinary slow-analysis path; no test reaches the intersection (all gaveUp tests mock every year queued; fallback tests never exhaust the budget). **Refuter votes: correctness STANDS (every mechanical claim verified file:line; correction — the chart still prints `Acumulado {Y-1} vs. normal`, so the state is a self-contradicting panel, not a silent misattribution), reproducibility STANDS (full static reachability trace, state stable — `queuedPolls` ref never decrements), impact REFUTED (three surviving year attributions; argues WARNING-class). 1-of-3 → STANDS.** Severity kept CRITICAL per protocol; impact calibration recorded. |
| R4-001 | resilience | same file `:417,432,441,450-465` with `:257-258,268-269,271-299,382` | CRITICAL | fixed | Same defect + the announcer effect tests `showingFallback` before `analysis.gaveUp` (`:273` vs `:277-279`), so the terminal announcement is unreachable while a fallback snapshot is on screen: the `aria-live` region re-asserts "se está preparando" after polling permanently stopped and never announces the terminal state the visible alert shows — against the file's own contract at `:8-11` and `:78`. **Refuter votes: correctness STANDS, reproducibility STANDS, impact REFUTED. 1-of-3 → STANDS.** |
| R4-002 | resilience | `RainfallDetailPanel.tsx:257-258` with `useRainfallAnalysis.ts:139-142` | WARNING | info | `canFallBack` requires `!analysis.isError`: one failed background poll (TanStack keeps `data`, sets error) disables the fallback query and unmounts card/chart/exports until the next successful poll ~5s later — the degraded path collapses exactly under transient network failure, aria-live churning per flip. |
| R2-001 | readability | `RainfallMetricList.tsx:175-179`, `RainfallDetailPanel.tsx:531-533` | WARNING | info | Comments claim the R6 unknown-group catch-all is present; the code iterates a hardcoded 3-key `GROUP_TITLES` include-list, so an unknown root key renders NOWHERE. The key-driven renderer is slice-2 scope (D8); the comments state future capability as present fact. |
| R2-002 | readability | `RainfallDetailPanel.tsx:291` vs `RainfallAnswerCard.tsx:153`, panel `:185,194-195` | WARNING | info | One concept, three words: control says `Ámbito regional`, card says `Ámbito:`, aria-live says `Alcance:` — the divergent surface is the one a screen-reader user cannot cross-reference. Unguarded drift (no test pins `Alcance`). |
| R2-003 | readability | `RainfallAnswerCard.tsx:142,172-174` | WARNING | info | Percentile rounding re-implemented inline (`Math.round(readable.value ?? 0)`) bypassing rainfallFormat.ts which owns the rule in 3 places and documents it as load-bearing; changing the rule desynchronizes headline from gloss/phrase. `readablePercentile` discards its own non-null narrowing, forcing a `?? 0` whose only output is a plausible-looking `Percentil 0`. |
| R2-004 | readability | `rainfallFormat.ts:177-184` | WARNING | info | `scopeSentence` doc denies coupling to `scopeChoiceLabel` then `split(' · ')`s its output — parsing the other formatter's presentation. Changing the private separator emits `la zona — sur` mid-sentence, type-safe and test-silent. |
| R3-002 | reliability | `RainfallDetailPanel.tsx:96-115` | WARNING | info | Collapsed-antecedents state disclosure rests on `aria-label`/`title` on a nameless `<span>` (name-prohibited generic role, ARIA 1.2); NVDA/JAWS likely never announce it. Test asserts attribute presence, not announcement. D2a's guarantee untested and likely false. |
| R2-005 | readability | `RainfallDetailPanel.tsx:69-72` | SUGGESTION | info | `EARLIEST_YEAR = 1991` documented as the selector's floor, but `YEAR_OPTIONS` uses the magic literal `CURRENT_YEAR - 1990`; the two agree by coincidence. |
| R3-003 | reliability | `RainfallDetailPanel.tsx:63,255-257` | SUGGESTION | info | The 1991 fallback-ladder floor is untested: no test selects 1991 and asserts no 1990 request is issued. |

### Fix round 1 of 2 — R3-001 + R4-001 (2026-08-12)

Both CRITICAL rows are ONE defect with two faces (visible surface + `aria-live`), so
they were fixed together. Strict TDD: the two intersection tests were written first and
observed RED (2 failed / 34 passed in `RainfallDetailPanel.test.tsx`), then GREEN
(36/36) with no other test touched.

- **The tests** (`consorcio-web/tests/unit/RainfallDetailPanel.test.tsx`, describe "the
  one-step year fallback"): `keeps a terminal disclosure naming BOTH years once polling
  gives up on the fallback` and `announces the terminal fallback state instead of
  re-promising an update`, over a shared `giveUpWithFallbackOnScreen()` helper that
  combines the per-year mock (ready for Y-1, queued for Y) with `maxQueuedPolls: 2` —
  the intersection neither the gaveUp tests nor the fallback tests reached.
- **The visible surface**: the terminal alert now carries the substitution when a
  fallback is on screen — `Mostrando el análisis {Y-1}. El análisis {Y} no está
  disponible aún.` (`fallbackTerminalSentence`) — and `data-showing-year` moved onto it,
  so the attribute survives wherever a fallback snapshot renders. The non-fallback copy
  is unchanged, the retry button stays, and no auto-update is promised after polling has
  stopped. The alert became its own `UnavailableAlert` component: the two added branches
  pushed the panel to cognitive complexity 32 (max 30) and this repo's precedent is to
  extract, never to raise the threshold (the same move that produced `ScopeControl`).
- **The announcer**: the `showingFallback` branch handles `gaveUp` explicitly instead of
  leaving it unreachable, with the SAME terminal sentence the alert states plus `Puede
  reintentar manualmente.` — the `:78` contract (alert and live region say the same
  thing) now holds in the intersection too. The pre-gaveUp fallback announcement is
  untouched.
- **Not touched**: R4-002 and the seven other `info` rows. R4-002's `isError` window (a
  failed background poll unmounts both alerts while the fallback card stays) is
  adjacent to this fix but is a different, WARNING-severity defect and stays `info`.

Gates: `npx vitest run` 279 files / **3779** tests all passing (was 3777; +2 new);
`npm run typecheck` exit 0 on both tsconfigs; `npm run lint` back to the **3**
pre-existing warnings (the 4th, introduced by this fix, was extracted away, not waived).
Bundle (same D12 method, same machine/session): pre-fix rebuild reproduced `908190`
exactly, post-fix `908422` → **+3779 vs the merge-base `550dc852` (904643)**, i.e. 232 B
over the amended 3547 budget. Measured and reported, not shaved.

### Slice 1 — scoped re-review of fix round (2026-08-12, inputs: ledger + `git show 0d3961b1` only)

R3-001 → **verified** (terminal alert names both years, `data-showing-year` present on every state that renders a fallback snapshot; pinned by 2 intersection tests, 36/36 ×3 identical runs). R4-001 → **verified** (announcer dispatches on `gaveUp` inside the `showingFallback` branch with the alert's own sentence; full 6-branch trace shows no surviving auto-update promise after polling stops; dep array covers every value read). No new BLOCKER/CRITICAL — refutation not applicable. Bundle post-fix 3779 accepted in design.md D12 second reading.

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| R3-004 | reliability | `RainfallDetailPanel.tsx:316-317` (untouched line) | WARNING | info | Coupling note: the `isError` term in `canFallBack` is what makes R3-001's disclosure coverage TOTAL (under error the card unmounts rather than rendering undisclosed) — the R4-002 window and this fix's completeness are coupled. A future edit to `canFallBack` can silently reopen R3-001; check this row first. |

**Slice 1 review verdict: CLOSED — 0 open findings. 2 CRITICAL fixed+verified in 1 fix round (budget: 2), 9 info bequeathed.**

## Slice 2 — full-4R code review, first pass (2026-08-12, diff feat/lluvia-ux-01-jerarquia..e9d8ebd1, 1212/53 lines)

Four lenses in parallel, 2-sweep budget. **Risk: EMPTY ledger** (root keys are a CLOSED server-side allow-list — `SNAPSHOT_ROOT_KEYS` enforced at service.py:668 — so the raw-key renderer only ever titles server-authored names; formula injection unreachable, exports are server-rendered where the sanitizer lives; no authz change — every newly disclosed field already traveled in the same operator-only payload; fixtures PII-clean). Refutation: 3 batched refuters over the single CRITICAL candidate; vote 2-1 STANDS (correctness + reproducibility stands, impact refuted).

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| S2R3-001 | reliability | `consorcio-web/src/components/map2d/rainfall/RainfallMetricList.tsx:423` with `rainfallFormat.ts:661` | CRITICAL | open→fixed (see fix round) | Shared block asserts "Vale para todas las métricas mostradas, en este plegable y en Antecedentes" (universal over the DISPLAYED set) while `hoistProvenance` compares only `metrics.filter(m => m.provenance !== undefined)`. A stripped metric (backend `_unavailable`, service.py:466-472, reachable PER-METRIC per _normalize_metric :479-518) is displayed but never compared → the block over-claims scope, against the delta spec's fabrication clause (spec.md:13,15 — the "discharges the entry" language is scoped to `available_through` only). Design contradiction UXJB-110 (design.md:96) vs UXJA-107 (design.md:98), unreconciled. **The defective state was already instantiated by a green test** (RainfallDetailPanel.test.tsx:1145 constructs the mixed snapshot and never asserts the block's claim). Refuter calibration: excluded rows are ALWAYS value-less and self-identifying (`—`/`Estado: No disponible`/`Motivo:`), so no number can be mis-sourced — the defect is the sentence, not the hoist. |
| S2R4-001 | resilience | `RainfallMetricList.tsx:423` | WARNING | info→fixed (discharged by same fix) | Same sentence false in two reachable states: (a) stripped-but-displayed metrics (the CRITICAL above at WARNING framing); (b) "y en Antecedentes" names a fold not on screen when the snapshot serves no antecedents. |
| S2R3-002 | reliability | `RainfallMetricList.tsx:423` | SUGGESTION | info→fixed (discharged by same fix) | The no-antecedents wording case, untested. |
| S2R2-001 | readability | `RainfallMetricList.tsx:169,173` | WARNING | info | Wire enums printed raw (`Clase de fuente: estimated_satellite`, `Ámbito espacial: zone`) while the same module owns the Spanish vocabularies the card uses one scroll above (`SOURCE_CLASS_WORDS` → `satelital`, `RAINFALL_SCOPE_LABELS` → `Zona`). Same fact, two words, one panel. Not the D8 raw-key rule — these labels EXIST and are used elsewhere on the same surface. |
| S2R2-002 | readability | `RainfallMetricList.tsx:98-105` | SUGGESTION | info | `GROUP_TITLES` and `KNOWN_GROUP_ORDER` are two hand-maintained lists of the same keys; drift consequence is a silent reordering. |
| S2R2-003 | readability | `design.md:356-366` | SUGGESTION | info | Interfaces block omits four shipped exports (`PROVENANCE_FIELDS`, `provenanceFieldValue`, `stringifyUnknownFields`, `metricEvidenceLine`); behaviour designed, record incomplete — same standard deviation #3 applied to `snapshotMetrics`. |

Verified clean across lenses (recorded, not reassurance): no throwing path in any new formatter (the total guard REMOVES a crash path — `'metric' in "texto"` TypeError now unreachable); deny-list matches the backend allow-list exactly; hoist at 0/1/all-stripped/partial never hoists on partial evidence; both folds build the hoist from the same `snapshotMetrics` so they cannot disagree; slice-1 assertions still bind (no vacuity); single-source formatters confirmed by grep; `_unavailable` drops `revision` too, so the exclusion cannot hide a divergent revision.

## Slice 2 — full-4R code review, fix round 1 of 2 (2026-08-12)

Only the verified CRITICAL was fixed. The refuter vote on it was 2-1 STANDS, with the
impact calibration that shaped the fix: the excluded rows are ALWAYS value-less and
self-identifying (`—` + `Estado: No disponible` + `Motivo: …`), so no number can be
mis-sourced — the defect is the SENTENCE over-claiming its scope, not data corruption.
So the sentence was fixed and the comparison set was left exactly as designed.

Strict TDD: both assertions were written first and observed RED (2 failed / 42 passed in
`RainfallDetailPanel.test.tsx`), then GREEN (44/44). No other test touched.

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| S2R3-001 | reliability | `consorcio-web/src/components/map2d/rainfall/RainfallMetricList.tsx:423` with `rainfallFormat.ts:661` | CRITICAL | fixed | The shared block said "Vale para todas las métricas mostradas, en este plegable y en Antecedentes." — a claim over the DISPLAYED set — while `hoistProvenance` compares only metrics WITH provenance (UXJB-110). A stripped metric (`_unavailable`: metric/value/state/reason, `service.py:479-518`, reachable PER METRIC) is displayed in the folds the sentence names and was never compared, so the block over-claimed its own scope (delta fabrication clause, `spec.md:13,15`), and design.md:96 (exclusion) contradicted design.md:98 (universal wording) with no reconciliation. **Fixed** by deriving the sentence from what was actually compared: `sharedProvenanceScope(everyDisplayedCompared, namesAntecedents)` keeps the universal wording when the exclusion removed nothing and emits `Vale solo para las métricas con procedencia servida, …` otherwise. Hoist untouched. Pinned by `an unserved field renders no line, and a stripped metric renders only its state`. |
| S2R4-001(b) | resilience | `RainfallMetricList.tsx:423`, `RainfallDetailPanel.tsx:570` | WARNING | fixed | **Discharged for free by the same sentence, same owner.** The `y en Antecedentes` clause is now conditional on a non-empty `antecedents` group — the exact condition that mounts the fold — so the block never points the reader at a control that is not on screen. Pinned by the new test `the shared block names Antecedentes only when that fold is on screen`. |
| S2R3-002 | reliability | same | WARNING | fixed | Same discharge as S2R4-001(b): the fold-naming half of the block's claim is now derived, not asserted. |
| S2R3-005 | reliability | `consorcio-web/src/lib/api/rainfall.ts:69` | WARNING | info | **Bequest, deliberately NOT fixed here (type ripple unknown).** `provenance: RainfallProvenance` is declared REQUIRED while the backend serves stripped shapes without it (`service.py:479-518`), which is why every test constructing that state needs an `as unknown as RainfallMetric` cast — a type that lies, with the cast as its only witness. A truthful `provenance?: RainfallProvenance` is a follow-up: it would force every reader of `.provenance` to be re-checked, which is exactly the audit the type is currently suppressing. Found by the reproducibility refuter. |

Gates: `npx vitest run` 279 files / **3808** tests all passing (was 3806; +2 new);
`npm run typecheck` exit 0 on both tsconfigs; `npm run lint` **3** warnings — the same
pre-existing three, none added. Bundle (D12 method, same machine/session): post-fix
**910172** vs the slice-2 base `908422` → **+1750 against the 3072 budget** (the pre-fix
slice-2 delta was +1643, so this fix costs **+107 B**: one small builder function and the
prop that carries its output).

### Slice 2 — scoped re-review of fix round (2026-08-12, inputs: ledger + `git show fa14e827` only)

S2R3-001 → **verified**. Both axes derive from the right facts: the comparison boolean is computed over the SAME `displayed` variable fed to the hoist, with the predicate character-for-character identical to the hoist's own membership rule (no second source of truth); the antecedents axis combines the group's existence under the total `isMetricGroup` guard with the `exclude` term. Render-state enumeration on the touched lines covers six states with the sentence TRUE in every one (all-stripped → block returns null, no claim made; a stripped metric confined to `annual` → narrows globally, an UNDER-claim, never an over-claim). S2R4-001(b) and S2R3-002 → **verified**, genuinely discharged: `namesAntecedents` is the only producer of the string `Antecedentes` in that block, and the new test asserts both directions in one render. 44/44 in the file, typecheck exit 0, no `any` and no cast in the new prop wiring. No new defect on fix-touched lines.

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| S2RR-001 | reliability | `consorcio-web/tests/unit/RainfallDetailPanel.test.tsx:1065` (untouched) | WARNING | info | The true/true branch is pinned by a PREFIX assertion, so deleting the `y en Antecedentes` clause from the positive branch keeps all three tests green. The exact-string discipline the two new assertions use is not applied to the branch that names the other fold. Cheap follow-up: tighten to the full sentence. |
| S2RR-002 | reliability | `RainfallMetricList.tsx:503` | WARNING | info | The `exclude?.includes('antecedents') === true` conjunct is unpinned — the only caller always passes it, so no test can distinguish it from `true`. A component-level test with `exclude` omitted would pin it. |
| S2RR-003 | reliability | `RainfallDetailPanel.tsx:570` vs `RainfallMetricList.tsx:120-131` (untouched) | SUGGESTION | info | Two predicates decide "is there an antecedents fold": `Object.keys(...).length > 0` vs `isMetricGroup`. A malformed non-empty group mounts the fold while `namesAntecedents` is false → under-claim. Wire-shape violation only, and the failure mode is silence, never a false claim — does not reopen S2R3-001. |
| S2RR-004 | reliability | `RainfallMetricList.tsx:420-427` | SUGGESTION | info | Spanish register matches the panel's voice; the separator branch is grammatical in all four combinations. No wording defect. |

**Slice 2 review verdict: CLOSED — 0 open findings. 1 CRITICAL fixed+verified in 1 fix round (budget: 2), 2 info rows discharged by the same fix, 7 info bequeathed (incl. S2R3-005: `rainfall.ts:69` declares `provenance` REQUIRED while the backend serves stripped shapes without it — type ripple unknown, follow-up).**

## Apply phase — Judgment Day (two blind judges, round 1)

Two blind judges reviewed the apply-phase diff independently. **Convergence: 0 confirmed** —
the judges did not converge on any BLOCKER/CRITICAL. **1 suspect** (UXJA2-001, judge A only)
was triaged by the orchestrator against `spec.md:165-171` and the code, **CONFIRMED on
evidence**, and then **owner-approved for fix**. Everything else is `info` and does not
enter the fix loop.

Process note: judge B's Skill Resolution was **fallback-path** — `react-19` was read, while
`typescript` and `playwright` were not resolvable at that worktree path. Recorded because a
lens that ran with a partial standard set is a fact about the review, not a footnote.

### Judge A

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| UXJA2-001 | judgment-day | `consorcio-web/src/components/map2d/rainfall/RainfallAnswerCard.tsx:112,150` | CRITICAL | fixed | The delta scenario "The year's value is suppressed by policy but its evidence exists" (`spec.md:165-171`) requires as its THIRD `THEN` clause that "the suppressed total is shown by state and reason, never as a number and never as zero". The card implemented the first two clauses only: a suppressed `annual.selected` rendered as `Acumulado hasta el {día}: —` via `AnnualText:112` (`formatMetricValue` → `—`), with NO state word and NO reason anywhere on the always-visible surface. The `withheld` branch at `:150` that renders `describeMetricState(...)` was scoped to `snapshot.annual.percentile` ONLY. The percentile twin's own test comment (`tests/unit/RainfallAnswerCard.test.tsx:199-204`) states this exact clause as an always-visible-surface obligation, so the asymmetry was an omission, not an adjudication. **Fixed by symmetry with the percentile**: a dimmed line `{metricLabel('selected')}: {describeMetricState(selected)}` renders adjacent to the percentile's withheld line, under the SAME readability predicate — the helper `readablePercentile` was generalized to `readableMetric` and is now the single predicate both lines consult, so "withheld" cannot come to mean two different things on one card. The `—` inside `AnnualText` stays: that is the VALUE slot, and the new line is the state + reason. Pinned in both directions by two new tests. |
| UXJA2-002 | judgment-day | `RainfallAnswerCard.tsx:198-208` | WARNING | info | assessment=**real**. The freshness reason rides ONLY on `title` / `aria-label` of a Mantine `Text` that renders a generic role; under ARIA 1.2 that element is name-prohibited, so assistive tech may not expose the reason at all. Same mechanism class as the known `R3-002`, but a DISTINCT element and a distinct delta clause ("with the served reason reachable"). Not fixed: the reason remains reachable through the technical fold, so the clause is satisfied by another surface. |
| UXJA2-003 | judgment-day | `RainfallAnswerCard.tsx:135` with `rainfallFormat.ts:140-147` | WARNING | info | assessment=**real**. `shortSource(selected ?? normal ?? percentile)` coalesces with `??`, which only falls through on `null`/`undefined`. A STRIPPED four-field metric is truthy and carries no provenance, so it wins the coalesce and `shortSource` returns `null`: the card renders NO `Fuente:` line even when `normal`/`percentile` carry full provenance. Failure mode is SILENCE, never a false claim — which is why it is info and not a fix. |

### Judge B

No BLOCKER and no CRITICAL.

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| UXJB2-001 | judgment-day | `RainfallMetricList.tsx:154-162` | WARNING | info | assessment=**real**. `stateChip` labels `Dato provisorio` when `temporal_state === 'provisional'` **OR** `fallback_used`, so a FINAL metric fed by an ordered fallback carries a provisional chip while the same row's text prints `Estado temporal: final` + `Origen: fuente alternativa` — a row that contradicts itself. Owner-ratified copy per task 1.26b / OWN-010, therefore RECORDED and not reopened. Pinned by `RainfallMetricList.test.tsx:220-236`, so a future fix moves the test with it. |
| UXJB2-002 | judgment-day | `RainfallDetailPanel.tsx:570` with `RainfallMetricList.tsx:99-109` | WARNING | info | assessment=**theoretical**. The antecedents fold is the ONE path that reaches `RainfallMetricRow` WITHOUT the total `isMetricGroup` guard, so a non-metric-shaped entry reaches `formatMetricValue`'s `.toFixed(1)` and throws, taking down the panel subtree — the crash class D8's guard made unreachable everywhere else, still reachable here. Wire-shape violation only. Distinct from `S2RR-003`, which flagged the UNDER-CLAIM consequence of the same predicate mismatch. |
| UXJB2-003 | judgment-day | `RainfallDetailPanel.tsx:104-158` | WARNING | info | assessment=**theoretical**. `AntecedentAccessory` iterates the hardcoded `ANTECEDENT_ORDER` and `flatMap`s away anything else, so an antecedent key outside `d7`/`d30`/`d90` is absent from the collapsed header the delta makes a MUST. The include-list-vs-key-driven lesson from slice 2 was applied to `RainfallMetricList` and not to this surface. Unreachable today; the value is reachable one click in. |

### Judgment Day fix round 1 — what shipped

Strict TDD on UXJA2-001: two tests written FIRST and observed **RED** (1 failed / 34 passed
in `RainfallAnswerCard.test.tsx`), then **GREEN** (35/35 in the file; 279 files / **3810**
tests in the full suite). Both directions are pinned: a suppressed total states its state +
reason, and a HEALTHY total adds NO such line — the assertion that fails an "always render
it" fix, which would have put a permanent `Disponible` next to every good number.

Gates: `npx vitest run` 279 files / 3810 tests all passing; `npm run typecheck` exit 0 on
both tsconfigs; `npm run lint` **3** warnings — the same pre-existing three, none added.
Bundle (D12 method, same machine/session): **910207** vs the slice-2 base `908422` →
**+1785 against the 3072 budget** (PASS, 1287 B of headroom). The pre-fix delta was +1750,
so this fix costs **+35 B**: one predicate rename, one derived value and one dimmed line.
Nothing was shaved to reach it.

**Judgment Day verdict: 0 open findings. 1 CRITICAL confirmed + fixed in 1 fix round
(budget: 2); 5 info rows recorded (3 assessed real, 2 theoretical), none blocking.**

### Apply phase — Judgment Day re-judge (round 1, scoped: ledger + `git show 7a2944e1` only)

**Both judges converged: UXJA2-001 → `verified`.** Judge A enumerated the whole state × value space (no suppressed total without a state line, no healthy total with one); judge B checked the same matrix against the BACKEND contract (`schemas.py:52-58` forbids `available` with a null value and requires a reason on `suppressed`/`unavailable`), closing the only false-positive shape at the server, not in the UI. Both confirmed the `readablePercentile` → `readableMetric` rename is a pure rename (body byte-identical, one other call site, zero percentile behavior change) and that the two tests pin both directions non-vacuously (the default fixture serves a healthy `selected`, so an unconditional render would print `Acumulado del año: Disponible` and fail).

**The raw-wire-token question, judged on evidence by both — NOT an OWN-002 re-introduction.** OWN-002 was composed backend JOB identifiers (`role:daily, analysis_missing`) in a status sentence addressed to a person; its fix moved queue labels to a data attribute. Here the token is a per-metric contract `reason` inside the state sentence the delta itself demands, produced by pre-existing owner-adjudicated machinery (`describeMetricState`, OWN-003), already rendered in the identical shape by the UNTOUCHED percentile twin (`:200-204`, asserted verbatim by a pre-existing test at `RainfallAnswerCard.test.tsx:202-204`) and by `RainfallMetricList.tsx:302` `Motivo: {reason}`. The delta's "reason" is satisfied literally; the residual is legibility.

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| UXJA2R-001 ≡ UXJB2R-001 | judgment-day | `RainfallAnswerCard.tsx:163-164,206-210` | CRITICAL | verified | Both judges independently verified the delta's third THEN is rendered on the always-visible surface by state and reason, never as a value; predicate symmetric with the percentile through ONE shared helper, so "withheld" cannot diverge between the two lines. |
| UXJA2R-002 ≡ UXJB2R-002 | judgment-day | `RainfallAnswerCard.tsx:208` and untouched twin `:202`, `rainfallFormat.ts:769-775` | WARNING | info | assessment=real. `coverage_below_threshold` is English snake_case in Spanish copy — satisfied literally, not legibly. No reason-vocabulary map exists anywhere in the frontend, and translating THIS line alone would break the symmetry UXJA2-001 demanded. **Correct scope for the follow-up: one `RAINFALL_REASON_LABELS` inside `describeMetricState`, which fixes the card, the panel row and the aria-labels in a single edit.** |
| UXJA2R-003 ≡ UXJB2R-004 | judgment-day | `tests/unit/RainfallAnswerCard.test.tsx:207-231` | SUGGESTION | info | Both judges found the same gap: the positive fixture is `state: 'unavailable'` while the delta scenario says *suppressed*. Same predicate, same `describeMetricState` branch → behaviorally covered, but the canonical state word is not pinned on this line. One `it.each` over both states closes it. |
| UXJA2R-004 | judgment-day | `RainfallAnswerCard.tsx:146-151` (UNTOUCHED) | WARNING | info | assessment=real, first-pass signal, no new round. The headline still uses a hand-written `selected.value !== null` instead of `readableMetric`, so the ONE-predicate rule the fix's own comment claims was applied to the two withheld lines and not to the headline above them. No delta violation (`—` is neither a number nor zero), and judge B verified the leak is closed at the server contract (`formatMetricValue` is state-blind but the validator guarantees a null value for withheld states). |
| UXJB2R-005 | judgment-day | `RainfallAnswerCard.tsx:163-164` | WARNING | info | assessment=theoretical. `state: 'partial'` + `value: null` is wire-legal and renders `Acumulado del año: Parcial` — state word, no reason (the helper appends reasons only for suppressed/unavailable). Outside the delta clause's scope and better than the bare dash it replaces; identical on the pre-existing percentile line. |
| UXJB2R-003 | judgment-day | `RainfallAnswerCard.tsx:132` | SUGGESTION | info | Rename verified byte-identical; zero behavioral surface. |

**JUDGMENT: APPROVED ✅** — apply phase, 1 CRITICAL fixed and verified by both judges in 1 fix round (budget: 2). 0 open findings. Info bequest carried to verify/archive.

## Verify phase (2026-08-12)

**Verdict: PASS-with-notes.** A read-only verify agent re-derived the change's claims against
the tree, then a single writer closed the record findings and measured the one gate the
read-only sandbox could not. The code verdict is CLEAN: the 3810-test figure reproduced
digit-for-digit, all 26 delta scenarios trace to a named test, the review ledger closes with
zero open findings across four rounds, and hygiene is clean (26 commits, zero AI attribution,
`consorcio-web/public/version.json` in no commit).

**What the verify phase actually found was the RECORD, not the code** — nine of the ten
findings are figures in the artifacts that disagree with the runs that produced them. That is
worth stating plainly rather than filing as trivia: this change's whole argument is that a
measured number beats an asserted one, and an apply record whose own arithmetic drifts is the
same failure class one level up. Every one of them is now corrected AGAINST THE RUN, never
against the other document.

### Executed evidence (verify phase, on `feat/lluvia-ux-02-disclosure` head)

| gate | command | result |
|---|---|---|
| unit suite | `npx vitest run` (full) | **279 files / 3810 tests passed**, exit 0 — reproduces the recorded figure exactly |
| typecheck | `npm run typecheck` | exit 0 (both tsconfigs) |
| lint | `npm run lint` | exit 0, **3 warnings** — the same three pre-existing cognitive-complexity warnings, none added |
| e2e collection | `npx playwright test -c tests/e2e/playwright.config.ts --list` | **89 tests in 10 files**; **10 tests** in `rainfall-v2-detail.spec.ts`, the zero-scroll case among them. COLLECTED, NOT EXECUTED |
| bundle (D12) | `rm -rf dist` → `npm run build` → `find dist/assets -name '*.js' -exec sh -c 'gzip -9 -c "$1" \| wc -c' _ {} \; \| paste -sd+ - \| bc` | **910207** vs slice-2 base `908422` → **+1785 / 3072 — PASS**, 1287 B headroom. **Reproduced the recorded figure byte for byte.** |

Method note, recorded because it is a trap the next person will hit: `npx playwright test --list`
WITHOUT `-c tests/e2e/playwright.config.ts` collects zero tests and exits 1, because from
`consorcio-web/` it sweeps the vitest suites too and dies on `vi.mock` outside a vitest runner.
The bare invocation looks like a broken e2e suite and is not one.

### Findings

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| V-001 | verify | `tasks.md` O.1 · `design.md:271` (D13) | CRITICAL | **open** | **The declared local e2e run has still never been executed, so the zero-scroll success criterion is asserted by nobody.** The case exists and collects (10 tests in the spec), which is the only thing any record here claims. It is owner-gated and all three blocking preconditions were re-verified live in this phase, not inherited: (1) `gee-backend/app/config.py:124` — `ficha_enabled: bool = False`; (2) `rg FICHA_ENABLED` over the tree returns NOTHING outside `openspec/` — no compose file, no env file, no example sets it, so `probeFichaAvailability` returns `'off'` and every test in the spec soft-skips; (3) `docker-compose.yml:345-351` — the `martin` service publishes NO host port by deliberate design (its own comment: host 3000 is taken by another stack on this box), while the SPA resolves tiles from `VITE_MARTIN_URL \|\| 'http://localhost:3000'`, so `clickFixtureParcela` never gets its `parcelas_catastro` 200. **This stays OPEN and is not softened.** A skipped run is a failed gate; archiving with it closed would record a zero-scroll criterion no run has ever asserted, which is exactly the third repetition of this gate's own three-strikes history (canary → preview → local). |
| V-002 | verify | `apply-progress.md` (JD fix section) · `review-ledger.md:328` | WARNING | **closed** | Both sites recorded GREEN as `36/36` for `RainfallAnswerCard.test.tsx`; measured is **35**. The record's own RED line refutes it arithmetically — `1 failed / 34 passed` is 35 tests, and a fix that adds no test cannot make the file grow to 36. Corrected to `35/35` at both sites. |
| V-003 | verify | `tasks.md` O.2 | WARNING | **closed** | O.2 sat unchecked claiming it waited on "an owner decision: amend the budget to 3547, or trim". That decision was MADE and is recorded at `design.md:229` (amendment to the measured 3547) and `design.md:231` (second reading, +3779/908422 accepted as slice-1 final). O.2 rewritten to carry both readings plus the slice-2 measurement and checked. |
| V-004 | verify | `apply-progress.md` JD fix gate table | WARNING | **closed** | The bundle figure was UNMEASURED by the read-only verify sandbox. Re-run here by the exact D12 method: **910207, reproducing the recorded figure byte for byte** — the third independent reproduction of a D12 figure in this change. Recorded as verify-confirmed. |
| V-005 | verify | `apply-progress.md` slice-2 gates | WARNING | **closed** | Slice-2 head test count read 3807 while `review-ledger.md:275` reads 3806. The ledger's chain 3806 → 3808 → 3810 lands on the verified terminal 3810; 3807 does not. Corrected to **3806** (and the flake paragraph's echo of the same figure with it), making the +27 delta from the 3779 slice-1 head explicit. |
| V-006 | verify | `apply-progress.md:65` | WARNING | **closed** | The three pre-existing lint warnings were named as "`LayerControlsPanel.tsx` ×2 and `useMapLayerEffects.ts`". Verified live, the real three are `src/components/map2d/LayerControlsPanel.tsx:397`, `src/components/report-form/useReportFormSubmission.ts:48`, `src/components/map2d/useMapLayerEffects.ts:95`. The slice-2 record already had it right; slice 1's was corrected to match the run. Consequence worth naming: a mis-attributed baseline is how a NEW warning gets absorbed as "one of the known three". |
| V-007 | verify | `design.md:385` | WARNING | **closed** | The Testing-strategy row still said the hoist "still hoists all NINE fields" after the eight-field amendment. `apply-progress` deviation #1 named only `design.md:362` as stale, so this second site survived the correction. Corrected to EIGHT, and the deviation entry now records that it under-counted its own blast radius by one site. |
| V-008 | verify | `specs/rainfall-analysis/spec.md:3` (delta preamble) | WARNING | **closed** | The preamble cited base spec `:596` for "Intensity, Peak, and Duration Outcomes"; the requirement heading actually lives at **`:607`**, located live in `openspec/specs/rainfall-analysis/spec.md` rather than by re-applying the known +11 offset — the offset is the symptom, the heading is the fact. This is bequest item **UXJA-206**, now marked discharged at its bequest entry. |
| V-009 | verify | `review-ledger.md:143-145` | WARNING | **closed** | UXJA-201 — the design-JD escalation and the SOLE open item at the convergence budget's end — was resolved in prose with no ledger table row, while every other finding of that weight got one. A proper row was added with id/lens/location/severity/status/evidence, recording both verified blocking facts and stating explicitly that the fix is DOCUMENTARY: naming the preconditions is what makes O.1 executable and is not the same as executing it. |
| V-010 | verify | `consorcio-web/public/version.json` | SUGGESTION | **closed** | Confirmed absent from all 26 commits, and confirmed again for this verify commit: the file is build-generated, is dirty in the worktree after the D12 rebuild, and was NOT staged. `.claude/` likewise. |

**Verify verdict: PASS-with-notes. Nine of ten findings closed in this commit. ONE remains
open — V-001 — and it is owner-gated, not agent-closable.** The code is verified; the
outstanding item is a RUN that has not happened, and no amount of inspection substitutes for
it. Do not archive this change while V-001 is open without recording, in the archive itself,
that the zero-scroll criterion ships unasserted.
