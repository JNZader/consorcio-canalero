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

**Info bequest for tasks/verify** (final re-judge rows, non-blocking): UXJA-203 (branch-3 metric rows drop a served available_through — one reconciling clause), UXJA-204/UXJB-202 (ledger count off-by-ones — noted here, correct at source when next edited), UXJA-205 (evidenceFooter is analysis-scoped; the fold's per-metric row needs its own string, not the shared one), UXJA-206 (three base-spec line citations stale by 11 lines post-f95bf8e5), UXJB-201 (available_through must leave D5's hoistable set or the per-metric gate can't run — tasks should pin it to the rows), UXJB-203 (the card/footer strings don't name their subjects; the stale banner is the disclosure — acceptable, recorded), UXJB-205 (the spec's suppression-is-not-absence sentence over-broad vs its own scenario), UXJB-206 (FichaTerritorialRainfallMount.test.tsx missing from the forced-edit list), UXJB-207 (D9 table vs D9a rule 4 disagree on scalar source_health — rule 4 wins, table to be read accordingly).
