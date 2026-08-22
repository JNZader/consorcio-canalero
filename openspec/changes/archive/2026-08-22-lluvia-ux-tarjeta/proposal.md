# Proposal: Lluvia Tab — Answer-First Card (Direction A)

## Intent

The Lluvia tab accreted four slices (public normals, v2 detail, insights, materialization) without ever being designed as one screen. It opens on 30-year CLIMATE context (`PrecipChart`) instead of this year's answer; the percentile — the only number that answers "¿llovió mucho?" — is typographically equal to everything else and printed twice (`RainfallMetricList.tsx:84,89` + its own row); the provenance line repeats verbatim on all six rows (`RainfallMetricList.tsx:70-72`, ~25-30% of list height); and a whole set of served fields is never rendered although `specs/rainfall-analysis/spec.md:156` requires them on displayed metrics — the exploration counted five (`source_health`, `discrepancies`, `completeness`, `provenance.freshness`, `quality`); the row actually prints only `source_id`, `nominal_resolution`, `coverage` and `revision` (`RainfallMetricList.tsx:61`) plus three badges, so `available_through`, `interval_start`, `interval_end`, `source_class`, `method`, `aggregation` and `spatial_scope` are missing too. On a 390 px phone at sheet `medio` the reader scrolls past ~200 px of context before reaching any answer.

This is a hierarchy change, not a rewrite. The honesty engineering (disclosure states, `null` ≠ 0, exclusive→inclusive `lastEvidenceDay`, solid-vs-dashed) is high quality and is reused verbatim.

## Scope

### In Scope

- **Answer card first**: percentile headline + accumulated + normal-to-date + freshness, with one derived adjective.
- **Chart always visible** directly under the card (`RainfallAccumulationChart`).
- **Antecedents collapsed but valued**: d7/d30/d90 numbers visible in the collapsed header, not hidden behind it.
- **Technical section (collapsed)**: provenance consolidated to ONE block (which is where the missing provenance keys land); `summary` demoted here; the remaining served-but-unrendered fields — freshness, `available_through`, `interval_start`/`interval_end`, completeness, quality, discrepancies and the analysis-level `source_health` — rendered as plain rows.
- **`PrecipChart` demoted** to a collapsible — collapsed by default only when the v2 detail actually renders beside it, open otherwise (for anyone whose only rainfall content it is, staff included).
- **Controls consolidated**: scope + year in one block under the header, the campaign preset beside the chart it windows (today they sit ~300 px apart with the metric list between them).
- **Prune dead `intensity` display chrome** (`RainfallMetricList.tsx:28-33`); make the group renderer key-driven so a future group cannot be silently dropped.
- **Presentational split**: card/list/chart stay dumb components with state in hooks, so direction C can lift them onto a page without rework.

### Out of Scope

- `/lluvia` page (direction C) — `spec.md:11` says the system MUST NOT create a dedicated Rainfall v2 page in this release; C needs its own change plus a spec delta. Pre-committed as the home of the event catalogue.
- **Exploration finding #7 — the entry point contradicts the scope.** The analysis is explicitly REGIONAL (the backend refuses parcel/geometry compute), yet the only way to reach it is by selecting ONE parcel: there is no entry from a polígono, a canal, a multi-parcela selection or a zone. This change does not fix that, and cannot: an entry point that is not a parcel ficha is a new surface, which is direction C. What this change does do is stop the mismatch from MISLEADING the reader — the card states `Ámbito: Zona/Cuenca` and the demoted public chart says *recorte de la parcela* (R1), so the two are no longer readable as one number about one parcel. **Deferred to C**, explicitly, not forgotten: C owns the non-parcel entry points along with the event catalogue.
- Multi-year fan-out (direction B), public exposure of v2, any backend / data-contract / metric / route change.

## Scope Decision

- **Mode**: **Selective**
- **Justification**: The incoming scope is right in kind but mixes two different jobs — *rearranging what is already rendered* (the owner's actual pain) and *surfacing the fields never rendered before* (a spec-compliance debt nobody is feeling). Both stay in, ordered so slice 1 (answer card, fold, accordion, controls) ships and is defensible alone, and slice 2 (technical disclosure) can slip without leaving slice 1 broken. Two cuts are made now: `discrepancies` / `source_health` ship as plain text inside the technical fold, **not** as a new badge/colour vocabulary — a full state UI for a usually-empty field is the expensive tail; and C / B / public exposure are held, blocked by `spec.md:11` and `spec.md:19-25` and by an event catalogue that does not exist yet.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `rainfall-analysis` — **presentation-only** delta: (a) provenance MAY be presented once for the displayed set when `source_id`, `nominal_resolution` and `revision` are identical, provided per-metric divergence and inspectability survive (`spec.md:154-163`); (b) answer-first hierarchy plus the derived-adjective labelling rule; (c) progressive disclosure MUST NOT hide a visible chart's textual equivalent. Data, state, export and provenance *content* requirements are unchanged.

## Approach

1. New presentational `RainfallAnswerCard` fed by the existing snapshot plus a freshness value the panel derives once per subject; the percentile becomes the headline and is not repeated as a badged row on the same always-visible surface. `AnnualText` keeps its role as the chart's textual equivalent — including its restatement of the percentile, which the delta's "Progressive Disclosure Without Data Loss" requires so the equivalent stays complete for readers who cannot see the plot — and stays outside any collapsed region.
2. `RainfallMetricList` splits: valued-but-collapsed antecedents + a technical block that hoists the shared provenance and keeps divergent fields on the row.
3. Reuse `components/ui/CollapsibleSection.tsx` for every fold — it already carries `aria-expanded` / `aria-controls` / `role="region"`, and the repo explicitly rejected Mantine `Accordion` for map chrome (file header, lines 20-23). No `Spoiler`, no new dependency.
4. `FichaTerritorialPanel` (tab mount, lines 238-255 / 603-613) reorders: detail first, `PrecipChart` accordion last.

## Constraints (numbered — carried from exploration; violation = defect)

| # | Constraint |
|---|---|
| R1 | The two "normal" numbers come from different pipelines (CHIRPS normals raster clipped to parcel vs `annual.normal` at zone scope). If they land near each other they MUST be labelled distinctly ("normal de la zona" vs "normal de la parcela"). |
| R2 | The headline adjective ("año seco") is derived ONLY from the served percentile with published cut-offs and is labelled as derived. No re-derivation from raw data. |
| R3 | Accessibility already won is untouchable: `aria-live` announcer, chart `role="img"` + `describePlottedWindow`, textual equivalent, solid-vs-dashed, `lastEvidenceDay` reused not re-derived, `null` never rendered as 0. |
| R4 | `CollapsibleSection` unmounts its body when closed. The **15** rainfall e2e testids plus `ficha-precipitacion` (`tests/e2e/rainfall-v2-detail.spec.ts`) either stay reachable or the spec is updated to expand first — in this same change. The exploration's count of 13 was short by `rainfall-accumulation-lag` and `rainfall-regional-estimate`. That spec runs in NO CI job and this change does not wire it into one: the canary allowlist is a production-safety contract, and the spec would soft-skip on a runner regardless (its ficha preamble needs a reachable backend and live catastro tiles). R4 is therefore gated in CI at the UNIT layer (`RainfallDetailPanel.test.tsx` expands each fold), with the e2e spec kept correct and run in a declared local environment — design D13 states which claim each layer covers. |
| R5 | No new library. `CollapsibleSection` + recharts (already loaded) only. |
| R6 | Pruning `intensity` MUST NOT create a silent drop: the renderer iterates the snapshot's own group keys with a title lookup and a visible fallback. |
| R7 | A visible chart's textual equivalent MUST NOT be moved behind a collapsed fold (unmount = no equivalent for screen readers). |

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `consorcio-web/src/components/map2d/rainfall/RainfallDetailPanel.tsx` | Modified | Order, control block, mounts the card |
| `consorcio-web/src/components/map2d/rainfall/RainfallAnswerCard.tsx` | New | Headline card (presentational) |
| `consorcio-web/src/components/map2d/rainfall/RainfallMetricList.tsx` | Modified | Group split, provenance hoist, `intensity` pruned |
| `consorcio-web/src/components/map2d/rainfall/rainfallFormat.ts` | Modified | Adjective from percentile; dead intensity labels |
| `consorcio-web/src/components/map2d/FichaTerritorialPanel.tsx` | Modified | Tab body order; `PrecipChart` into a fold |
| `consorcio-web/src/components/map2d/MapPanelShell.tsx` | Modified | One added `data-testid` on the sheet's scrolling body — the box the zero-scroll criterion is measured against |
| `consorcio-web/src/components/ui/CollapsibleSection.tsx` | Reused | No change expected |
| `consorcio-web/tests/e2e/rainfall-v2-detail.spec.ts` | Modified | Expand-then-assert for folded testids; zero-scroll case; unknown-group assertion |
| `consorcio-web/package.json` | Modified | ONE added script (`test:e2e:rainfall`) naming the declared local run; the `test:e2e:canary` allowlist is NOT touched |
| `.github/workflows/**`, `gee-backend/tests/test_ci_workflow_contracts.py` | Untouched | No CI wiring: the canary allowlist and the frontend-workflow e2e guard stay as they are (design D13) |
| `gee-backend/**`, `useRainfallAnalysis.ts`, `lib/api/rainfall.ts` | Untouched | No contract change |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Folded content breaks e2e (unmount on close) | High if missed | R4 is a first-class task; run the e2e spec before the layout is called done |
| Provenance hoist flattens a divergent metric (fallback/revision) | Med | Hoist only fields equal across the displayed set; assert with a mixed-source fixture |
| Derived adjective drifts from the served percentile | Med | Single pure function, cut-offs published in the artifact, unit-tested at boundaries |
| Diff exceeds the 400-line review budget | Med-High | Two slices, chained PRs; slice 1 shippable alone |

## Rollback Plan

Frontend-only render-tree rearrangement: revert the commit(s) and the previous tree is restored exactly. No backend, no migration, no API/contract change, no data written. Slice 2 is revertible independently of slice 1.

## Dependencies

- None new. Reuses `CollapsibleSection`, recharts, `rainfallFormat`, `useRainfallAnalysis`, `lastEvidenceDay`.

## Success Criteria

- [ ] At 390×844 with the sheet at `medio`, a staff user sees percentile + accumulated + the last day with evidence with **zero scroll**. Verified by the `requireCondition`-gated e2e case (element box against the sheet body's visible height, failing rather than skipping when that box is absent), run in the declared local environment of design D13 as a slice-1 merge gate — CI does not gate it, and this criterion does not claim it does. Its structural precondition (card before chart before folds, both folds collapsed) IS gated in CI, in the unit layer.
- [ ] Clicks to the first analytic number ≤ today (today: tab click + scroll; target: tab click, no scroll).
- [ ] The provenance string renders **once** when all displayed metrics share source, resolution and revision; a divergent metric still shows its own.
- [ ] No datum visible today disappears — folded, never deleted; asserted by expanding every disclosure and diffing the rendered metric set against the snapshot fixture.
- [ ] Bundle delta ≤ +3 kB gzip, measured.
- [ ] Suites green at the pre-change baseline (unit ≈3675, a11y suite intact, all 15 rainfall e2e testids plus `ficha-precipitacion` resolving in the declared local run of D13; the CI-gated half of that is the unit layer).
