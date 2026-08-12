# Tasks: Lluvia Tab — Answer-First Card (Direction A)

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | ~1060 total (slice 1 ~590 = 380 src + 210 tests; slice 2 ~470 = 310 src + 160 tests) |
| 400-line budget risk | High — slice 1 is ABOVE the budget BY DESIGN (D11), and the consequence is recorded, not rounded away |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (slice 1) → PR 2 (slice 2) |
| Delivery strategy | auto-chain |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

**Review tier, per D11 (not negotiable at apply time):** slice 1 at ~590 lines is reviewed at the
FULL 4R tier (risk · resilience · readability · reliability). Splitting slice 1 further was
considered and rejected in design — the card, the folds and the reorder are ONE hierarchy change
and a half-applied hierarchy is a worse review object than a large coherent one. If the measured
diff lands under 400, the tier drops ON MEASUREMENT, not on hope. Slice 2 (~470) is likewise 4R
unless measured under 400.

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|---|---|---|---|
| 1 | Answer-first hierarchy: card + freshness + folds + controls + `PrecipChart` accordion + forced test/e2e migration (D1/D1a, D2/D2a, D3, D4, D6, D7, D10, D11) | PR 1 | base = `feat/lluvia-ux-tarjeta` (tracker). Ships and is defensible alone. Merge gates: unit suite green + O.1 (declared local run) + O.2 (bundle) |
| 2 | Technical disclosure: provenance hoist + enumerated field floor + stringify guard + summary relocation + key-driven renderer + `intensity` prune (D5, D8, D9/D9a) | PR 2 | base = PR 1 branch. Pure fold contents — slice 1 is unaffected if this slips, and it is revertible independently |

Only the tracker branch merges to `main`.

---

## Slice 1: Answer-First Hierarchy (D1/D1a, D2/D2a, D3, D4, D6, D7, D10)

All paths below are relative to `consorcio-web/`.

### Formatters and derivations (foundation — everything else imports these)

- [x] 1.1 RED `tests/unit/rainfallFormat.test.ts::"wetnessFromPercentile — every published cut-off from both sides"` — table: `0, 10, 10.4 → muy seco`; `10.6, 30, 30.4 → seco`; `30.6, 50, 69.4 → normal`; `69.6, 70, 89, 89.4 → húmedo`; `89.6, 90, 100 → muy húmedo`; plus `value: null`, `state: 'suppressed'`, `state: 'unavailable'`, `metric: undefined` → `null`. Acceptance: every boundary of D4's published table is pinned from BOTH sides, rounding included.
- [x] 1.2 GREEN `src/components/map2d/rainfall/rainfallFormat.ts` — add `RAINFALL_WETNESS`, `RainfallWetness`, `wetnessFromPercentile(metric)` and `wetnessLabel(wetness)` per the D4 cut-offs, applied to the ALREADY-rounded percentile (the same `Math.round` `percentilePhrase` uses at `rainfallFormat.ts:77`). Makes 1.1 pass.
- [x] 1.3 MOVE `lastEvidenceDay` (`RainfallAccumulationChart.tsx:153`) and `evidenceFooter` (`:178`) into `rainfallFormat.ts` as exports, docblocks carried verbatim; the chart imports them back (D10). Acceptance: the `RainfallAccumulationChart.test.tsx` block `the footer degrades honestly (JDA-104, JDB-103)` passes with ZERO edits to its assertions, and `rg -n 'function lastEvidenceDay|function evidenceFooter' src/components/map2d/rainfall` returns exactly one definition each.
- [x] 1.4 RED `tests/unit/rainfallFormat.test.ts::"deriveFreshness — the three-branch evidence gate"` — five cases from the Testing Strategy: (a) `annual.selected` available → `kind: 'evidenced'` + `Evidencia publicada hasta el {available_through − 1 day}`; (b) `state: 'suppressed'`, `reason: 'coverage_below_threshold'`, `coverage: 0.62`, provenance intact → the SAME real date, `kind: 'evidenced'`, NO no-evidence sentence; (c) `state: 'unavailable'`, `reason: 'no_data_in_disclosure_window'`, provenance carrying the `comparison_end + 1` fallback → `kind: 'no_evidence'`, `evidenceDay: null`, `Sin días con evidencia publicada en este análisis`; (d) the stripped four-field `_unavailable` shape AND an absent `annual.selected` → `kind: 'unknown'`, `Frescura no disponible en este análisis`, no date, no no-evidence claim, served `reason` carried on the result; (e) an unparseable `available_through` degrades to its own raw day instead of throwing (JDA-104).
- [x] 1.5 GREEN `rainfallFormat.ts` — `RainfallFreshness` (`kind`/`evidenceDay`/`sentence`/`reason`) + `deriveFreshness(snapshot)` implementing D1a's gate: EVIDENCE only (`provenance.available_through` served AND (`coverage > 0` OR a served numeric `value`)) → `evidenced`; `state === 'unavailable' && reason === 'no_data_in_disclosure_window'` → `no_evidence`; neither → `unknown`. Never keys on policy state. Makes 1.4 pass.
- [x] 1.6 RED `tests/unit/rainfallFormat.test.ts::"compactAntecedent"` — `31.0 → '31'`, `83.7 → '84'`, `value: null` → `'—'`, suppressed → `'—'`, `undefined` metric → `'—'`; the returned string carries NO unit (D2a).
- [x] 1.7 GREEN `rainfallFormat.ts::compactAntecedent(metric)` — one line: `Math.round(value)`, no decimals, no unit, `—` when there is no value. `formatAccumulated` is NOT touched and keeps its own call sites. Makes 1.6 pass.

### The answer card

- [x] 1.8 RED create `tests/unit/RainfallAnswerCard.test.tsx` and MOVE the five `AnnualText` tests out of `tests/unit/RainfallMetricList.test.tsx:83-156` — three verbatim (`states the percentile beside the year and the normal`, `prints the baseline period AS SERVED, in the phrase too`, `keeps a served percentile of 0 as a number, never as a missing value`) and two RE-EXPRESSED against the card's `{ snapshot, freshness }` props (`renders no value for a suppressed percentile, and never a zero`, `omits the phrase entirely when the analysis carries no percentile`). Enrol the new file in `tsconfig.tests.json` `include` in the SAME commit (the file's own ENROLMENT RULE, R3-004).
- [x] 1.9 RED `tests/unit/RainfallAnswerCard.test.tsx` — the card's own contract: `rainfall-headline` prints `Percentil {rounded}` and falls back to `Acumulado del año {value}` when no percentile is served; `rainfall-wetness` prints `Año húmedo · categoría derivada del percentil 72 de 1991-2020` (derivation AND served baseline IN the sentence) and is ABSENT when the percentile is suppressed/unavailable/`null`, with the suppression reason still displayed; `rainfall-freshness` prints `freshness.sentence` for each of the three `kind`s and carries `freshness.reason` in `title` + `aria-label` on `unknown`; `rainfall-annual-text` is present; the scope line states `Ámbito: {Zona|Cuenca}` (R1) and the comparison end; no badged `rainfall-metric-percentile` row exists anywhere in the card.
- [x] 1.10 GREEN create `src/components/map2d/rainfall/RainfallAnswerCard.tsx` — presentational, props `{ snapshot, freshness }` exactly (no hook, no query, no store), content order per the design's Data Flow: headline → wetness → `AnnualText` (moved here, testid `rainfall-annual-text` unchanged) → freshness → scope line. Root testid `rainfall-answer-card`. Makes 1.8 and 1.9 pass.
- [x] 1.11 Remove `AnnualText` from `src/components/map2d/rainfall/RainfallMetricList.tsx:67-85`. Acceptance: `rg -n 'rainfall-annual-text' src/` returns exactly ONE hit, in `RainfallAnswerCard.tsx`.

### List split

- [x] 1.12 RED `tests/unit/RainfallMetricList.test.tsx::"exclude keeps a group out of this list without dropping it from the snapshot"` — `<RainfallMetricList snapshot={s} exclude={['antecedents']} />` renders `annual` rows and NO `rainfall-metric-d*` row; the same snapshot without `exclude` renders them.
- [x] 1.13 GREEN `RainfallMetricList.tsx` — split into `RainfallMetricRow` (one metric) → `RainfallMetricGroup` (one group) → `RainfallMetricList({ snapshot, exclude?: readonly string[] })` (composition + summary). `exclude`, never `include`, so an unrecognised server group lands in the technical fold by default (R6-compatible). Makes 1.12 pass.

### Panel: order, controls, folds, freshness

- [x] 1.14 RED `tests/unit/RainfallDetailPanel.test.tsx` — five structural tests: (a) ORDER via `compareDocumentPosition` — `rainfall-answer-card` before `rainfall-accumulation-chart` before `rainfall-antecedents` before `rainfall-technical`; (b) both folds render `aria-expanded="false"` on first paint; (c) R7 witness — with EVERY fold closed, `rainfall-annual-text` is still in the document; (d) freshness derived ONCE — the card's date comes from `annual.selected.provenance.available_through`, and changing ONLY the `/series` response's `available_through` does not move it while the chart footer DOES move; (e) the collapsed `Antecedentes` header carries `7d 31 · 30d 84 · 90d — mm` — fixed d7 → d30 → d90 order, unit stated exactly once at the end, the unavailable item printing `—` with its reason in `title`/`aria-label`. No fake viewport: jsdom has no layout, so this file asserts structure only.
- [x] 1.15 GREEN `src/components/map2d/rainfall/RainfallDetailPanel.tsx` — always-mounted: announcer, header, `rainfall-controls` block (row 1 scope `SegmentedControl` when >1 choice, row 2 year `NativeSelect` at `flex: '1 1 160px'; minWidth: 0`, both OUTSIDE the snapshot gate as today), `RainfallAnswerCard`, `RainfallAccumulationChart`, export row. Folded with `CollapsibleSection defaultOpen={false}`: `Antecedentes` (testId `rainfall-antecedents`, `rightAccessory` built from `compactAntecedent`) and `Detalle técnico` (testId `rainfall-technical`, body = `RainfallMetricList exclude={['antecedents']}`). The panel calls `deriveFreshness(snapshot)` ONCE and passes the value down. Lift the campaign preset state here (`preset` + `onPresetChange`, D6). Makes 1.14 pass.
- [x] 1.16 Migrate the seven forced assertion sites in `tests/unit/RainfallDetailPanel.test.tsx` (`:268`, `:303`, `:315-317`, `:327-330`, `:336`, `:359`, `:500`): each either clicks `rainfall-technical-header` before reaching `rainfall-metrics`/`rainfall-metric-*`, or moves to the card (`:359`, `:500` reach `rainfall-annual-text`). Acceptance: `never claims parcel-level accuracy from nominal grid resolution` (`:265`) and `exposes provenance: source, nominal resolution and revision` (`:334`) stay green — they are spec scenarios, not incidental assertions.

### Chart: controlled-only preset

- [x] 1.17 `src/components/map2d/rainfall/RainfallAccumulationChart.tsx` — `preset` and `onPresetChange` become REQUIRED props; delete the internal `useState` (`:281`) and the uncontrolled branch. Update `renderChart()` (`tests/unit/RainfallAccumulationChart.test.tsx:230`) into a controlled wrapper that owns the preset state, and the two preset tests in the `campaign display preset (4.5)` block (`:623`). Acceptance: all 26 `renderChart` call sites keep working through the one helper; `rainfall-campaign-preset` stays ONE instance in the chart header, inside the snapshot gate.

### Ficha: `PrecipChart` accordion (D7)

- [x] 1.18 RED `tests/unit/FichaTerritorialRainfallMount.test.tsx` (UXJB-206 — the file was missing from D11's forced-edit list) — the four existing mount cases re-expressed against the new tree (v2 detail ABOVE the fold; `ficha-precipitacion` inside `ficha-precip-fold-body`), plus the four D7 predicate cases, driving `useCanAccess` through the auth store the way `RainfallDetailPanel.test.tsx:159-166` does: staff + parcela + nomenclatura → fold CLOSED; **staff + non-parcela ficha → OPEN**; non-staff + parcela → OPEN; and a post-mount flip of the predicate REMOUNTS the section via its `key` so the default is recomputed instead of frozen by `CollapsibleSection.tsx:69`'s one-shot `useState`.
- [x] 1.19 GREEN `src/components/map2d/FichaTerritorialPanel.tsx` — `const staff = useCanAccess(['admin','operador'])` at the TOP of `PanelBody` (`:496`), ABOVE the `isLoading` return at `:523` and the `isError || !data` return at `:534` (a conditional hook changes the hook count on the loading→result transition and crashes the ficha); `const v2DetailWillRender = staff && tipo === 'parcela' && !!parcelaProps?.nomenclatura`; in the `FICHA_PRECIP_TAB` branch (`:603-613`) render `RainfallDetailPanel` FIRST, then `<CollapsibleSection key={v2DetailWillRender ? 'precip-demoted' : 'precip-primary'} title="Precipitación mensual normal (recorte de la parcela)" defaultOpen={!v2DetailWillRender} testId="ficha-precip-fold">` wrapping `PrecipChart`. Makes 1.18 pass. `CollapsibleSection.tsx` is NOT modified.

### Shell: the box the zero-scroll criterion measures against

- [x] 1.20 `src/components/map2d/MapPanelShell.tsx:253` — add `data-testid={`${testId}-sheet-body`}` to the sheet's scrolling body div. ONE attribute: no behaviour, no style, no prop. Pin it in `tests/unit/MapPanelBottomSheet.test.tsx` (the file already renders the shell with `testId="shell-under-test"` at `:361`): the body carries `shell-under-test-sheet-body` and the children render INSIDE it. For the ficha this resolves to `ficha-territorial-panel-sheet-body` (`FichaTerritorialPanel.tsx:718`).

### e2e spec + the named local run (D13)

- [x] 1.21 `tests/e2e/rainfall-v2-detail.spec.ts` — readiness sentinel switch at the five sites that wait on `rainfall-metrics` (`:412`, `:452`, `:463`, `:504`, `:552`) → `rainfall-answer-card`. The ONE content test (`operador: detalle visible…`, `:398-418`) becomes expand-then-assert: click `rainfall-technical-header`, then assert `rainfall-metrics` inside `rainfall-technical-body` (R4). Also extend `readyBody`'s `annual` with `percentile: mockMetric('percentile', 72)` so the card renders the headline branch the criterion is about — `CSV_BODY` is an independent fixture asserted with `toContain`, so parity is unaffected.
- [x] 1.22 `tests/e2e/rainfall-v2-detail.spec.ts` — new nested describe with `test.use({ viewport: { width: 390, height: 844 } })`: measure `boundingBox()` of `rainfall-answer-card` against `ficha-territorial-panel-sheet-body`'s own visible height and assert the card's bottom is inside it. Gated with `requireCondition` (NOT `skipForMissingData`): a missing sheet body means the layout under test is not there, and a criterion that skips itself when the box it measures is absent measures nothing.
- [x] 1.23 `package.json` — add ONE script beside the existing e2e scripts: `"test:e2e:rainfall": "playwright test -c tests/e2e/playwright.config.ts tests/e2e/rainfall-v2-detail.spec.ts"`. Acceptance: `test:e2e:canary` (`:23`) is byte-identical, no workflow file is touched, `gee-backend/**` is untouched (D13 — the canary allowlist is a production-safety contract).

### Owner-reported defects on the live UI (added 2026-08-11, mid-apply)

Three defects the owner found in the deployed surface, with screenshots. All three land on
surfaces slice 1 is already rewriting (the D6 controls, the queued disclosure, the D9 row), so
they are fixed HERE rather than deferred — a slice that reorders this surface and leaves a
truncated badge on it has not fixed the reader's problem. Ledger rows: `OWN-001..003`.

- [x] 1.24 RED+GREEN `rainfallFormat.ts::scopeChoiceLabel(choice, qualify)` + `scopeChoiceLabels(choices)` + `shouldUseSegmentedScope(labels)`, and the panel's scope control. Defect: the control labels each option with `RAINFALL_SCOPE_LABELS[choice.kind]`, i.e. the KIND, so every basin renders as an identical `Cuenca` (owner screenshots: `Zona | Cuenca | Cuenca`, and a Bell Ville parcel — nomenclatura 3603403896547762 — resolving to FIVE scopes, `Zona | Zona | Cuenca | Cuenca | Cuenca`). `RainfallScopeChoice` carries `{kind, id, version}` and the backend serves no display name, so the qualifier is the prettified `id`: split on `_`/`-`/space, drop a leading token that repeats the kind (`cuenca`/`zona`/`basin`/`zone`), capitalize, join — `cuenca_sur` → `Cuenca · Sur`. A choice is qualified iff its KIND appears more than once in the served set, so a lone zone stays plain `Zona`. **Component (amends D6, on the owner's five-scope evidence): `SegmentedControl` only when the choices are ≤3 AND their labels fit the panel's own width untruncated; otherwise a `NativeSelect`, the same control the year uses beside it.** Five labeled options cannot fit 348 px, and forcing them in would reproduce 1.26's defect at the container level. The `rainfall-scope-switch` testid and the `Ámbito regional` aria-label ride whichever component renders; the default stays the first served choice. Acceptance: five choices (2 zones + 3 basins) render five DISTINCT labels through the select branch; the ordinary zone+basin pair keeps the segmented control; an opaque id degrades to its own prettified text rather than disappearing.
- [x] 1.25 RED+GREEN `RainfallDetailPanel.tsx` — the queued state prints internal job labels as user copy (owner screenshot: `Análisis en preparación: role:daily, analysis_missing. Se actualiza automáticamente.`). Both the `aria-live` announcement and the `rainfall-queued` alert state ONE human sentence; the served labels move to a `data-queued-labels` attribute — machine-inspectable, never rendered text. The testid contract and the "never a silent spinner" rule are unchanged: the alert still exists, still says the analysis is being prepared, and still says it updates itself. Acceptance: with `labels: ['role:daily','analysis_missing']` the rendered text contains neither string and the attribute carries both.
### Second external UX review + owner decisions (added 2026-08-11, mid-apply)

A second review of the deployed surface, plus two owner decisions. Same rule as above: these
land on surfaces slice 1 owns, so they are fixed here. Ledger rows `OWN-004..010`.

- [x] 1.27 RED+GREEN `RainfallDetailPanel.tsx` — the ONE-STEP year fallback. When the selected year answers 202, request `Y-1` as well and DISPLAY it rather than leaving the reader an empty panel behind a spinner; the alert becomes the notice that names both years (`Mostrando {Y-1} — el análisis {Y} se está preparando y se actualizará solo.`) and carries `data-showing-year`. If `Y-1` is ALSO queued the ladder stops: no `Y-2`, ever — a fallback that keeps walking backwards turns one slow answer into a queue of them. Floor at 1991 (the selector's own oldest year). Acceptance: queued `Y` + ready `Y-1` → the previous year's analysis renders with the two-year notice; queued `Y` + queued `Y-1` → the plain queued state and exactly two DISTINCT years ever requested.
- [x] 1.28 RED+GREEN the percentile, made readable: (a) every ALWAYS-VISIBLE surface prints the same ROUNDED value (headline, gloss, phrase) while the technical row keeps the served precision — one fact, never two spellings on one screen; (b) `formatMetricValue` renders the `percentil` unit as a PREFIX (`Percentil 46.9`), because a rank is not a magnitude and `46.9 percentil` is not a phrase; (c) a dimmed gloss under the adjective, `De cada 100 años, {n} fueron más secos que este.`, absent whenever the percentile is not readable — an interpretation of a withheld number is the withheld number.
- [x] 1.26b REFINEMENT — chips are EXCEPTION-ONLY and in full Spanish: an available, definitive metric shows NO chip; a provisional or fallback-fed value shows exactly `Dato provisorio`; a non-available state shows its state word. The metadata line says `Fuente alternativa`, never `FALLBACK`. **The row's TEXT now always states `Estado: {word}`** — the chip is presentation, the text is the contract, and dropping a chip must never drop a served field (D9).
- [x] 1.29 The card's evidence footer is a CLOSED set: the cut date (inside the accumulation phrase), the scope explanation, and a SHORT source (`CHIRPS (satelital)`). Coverage and completeness are NOT on the card — a permanent `Cobertura: 100%` is noise on every healthy analysis, and a degraded one already surfaces through the state machinery. Full provenance stays in the technical fold.
- [x] 1.30 Copy refinements from the second review: (a) the accumulation phrase states its CUT DATE (`Acumulado hasta el {día}`, from `freshness`, never the clock) and degrades to `Acumulado parcial del año {Y}` with no date; (b) `annual.normal` says `al mismo período` while still naming the served baseline; (c) the card explains the regional estimate by NAME (`Estimación para la cuenca Rio Tercero, que contiene esta parcela.`); (d) the `aria-live` region becomes VISUALLY HIDDEN — it restated whatever was already on screen, printing the queued sentence twice; (e) its ready wording separates the two dimensions (`Análisis {Y} disponible · Alcance: {scope}`); (f) the fold title and the public chart are de-jargonized (`Lluvia histórica mensual`, `Total anual histórico (parcela)`) with NO frozen period, because the normals' period is server-driven; (g) the queued alert was VERIFIED already blue/informative — no change was needed and none was made.

- [x] 1.26 RED+GREEN `RainfallMetricList.tsx` — state badges fragment in the 380 px panel (owner screenshot: `PROVISIO… FALLB… DISPONI…`). A truncated badge is worse than no badge: it is unreadable AND it looks like data. ONE badge per row, carrying the state WORD only (`Disponible`/`Parcial`/`Suprimida`/`No disponible`); the reason moves to its own line (`Motivo: …`) and `Provisional`/`Fallback` become plain markers on the metadata line. The row wraps instead of squeezing. Acceptance: a row with all three markers renders exactly one `[data-metric-state]` element whose text is a full vocabulary word with no ellipsis, and the reason, `Provisional` and `Fallback` are all still reachable as text.

---

## Slice 2: Technical Disclosure (D5, D8, D9/D9a) — base = slice 1

- [ ] 2.1 RED `tests/unit/rainfallFormat.test.ts::"hoistProvenance"` — (a) all-equal fixture → every candidate field `shared`, `perMetric` empty; (b) MIXED fixture (metric A `revision: 'policy-v2'`, metric B `provenance.source_id: 'chirps-v3-prelim'`) → those two stay `perMetric`, the other **six** hoist; (c) a metric served in the stripped four-field `_unavailable` shape is EXCLUDED from the comparison set, so an otherwise-identical set still hoists all eight; (d) an all-stripped set yields an empty `shared`.
- [ ] 2.2 GREEN `rainfallFormat.ts` — `PROVENANCE_FIELD`, `RainfallProvenanceHoist`, `hoistProvenance(metrics)`: per-field, `shared` iff the set is non-empty and every metric's value is strictly equal. **Candidate set = `source_id`, `source_class`, `method`, `nominal_resolution`, `aggregation`, `spatial_scope`, `freshness` + metric-level `revision` — EIGHT fields. `available_through` is PINNED TO THE ROWS and leaves the hoistable set (UXJB-201): it is the input of the per-metric evidence gate (D9a rule 2), and a hoisted date cannot be gated per metric.** `coverage`, `completeness`, `interval_start`, `interval_end` are never hoisted (D5). Metrics without `provenance` are excluded from the comparison set. Makes 2.1 pass. *(Consequence recorded rather than rounded away: D5's "nine fields"/"other seven" figures counted `available_through`; with it pinned to the rows the numbers are eight and six. Same decision, corrected arithmetic.)*
- [ ] 2.3 RED+GREEN `rainfallFormat.ts::stringifyUnknownFields(value)` + `tests/unit/rainfallFormat.test.ts::"object fields never print [object Object]"` — D9a rule 4, ONE guard with TWO callers (`quality`, `source_health`): a plain object → `k=v; k=v` in key order for SCALAR values only; `null`, arrays, nested objects and functions SKIPPED (never coerced); a non-object input (bare string/number/boolean) printed as itself; zero pairs → the caller renders NO line. **Where D9's table and D9a rule 4 disagree on a scalar `source_health`, rule 4 wins (UXJB-207): a scalar prints as itself, not as a `k=v` pair.**
- [ ] 2.4 RED+GREEN `rainfallFormat.ts::metricEvidenceLine(metric)` + tests — the PER-METRIC evidence statement (UXJA-205: `evidenceFooter` is analysis-scoped — `…en este análisis` — and MUST NOT be reused on a metric row). Same `lastEvidenceDay`, same three-branch gate applied to the metric's OWN fields: `coverage > 0` or a served numeric value → `Evidencia publicada hasta el {day}`; `unavailable` + `no_data_in_disclosure_window` → `Sin días con evidencia publicada para esta métrica`; neither → `null`, and the row renders no evidence line at all. Tests pin all three branches plus the policy-suppressed counterexample (a suppressed metric with real coverage prints its real date).
- [ ] 2.5 RED `tests/unit/RainfallDetailPanel.test.tsx::"the enumerated field floor is reachable with one disclosure control"` — with every disclosure expanded, each metric shows `interval_start`/`interval_end`, coverage, completeness, quality, discrepancies, temporal state, revision, `fallback_used` and its provenance as `shared ∪ row`; the shared block (`rainfall-provenance-shared`) states it covers ALL displayed metrics of BOTH folds; a snapshot serving `source_health` renders it ONCE at the fold's foot; a snapshot not serving it renders no placeholder.
- [ ] 2.6 RED `tests/unit/RainfallDetailPanel.test.tsx::"an unserved field renders no line, and a stripped metric renders only its state"` — D9a rule 3: no `—`, no empty label, no `null` placeholder for an unserved field; a metric in the stripped four-field shape renders state + reason and NOTHING else (no provenance, no coverage, no evidence line).
- [ ] 2.7 GREEN `RainfallMetricList.tsx` — render the shared provenance block (`rainfall-provenance-shared`) at the top of the technical fold with its own wording ("Vale para todas las métricas mostradas"), and per D9's table add to each row: `Frescura`, the `metricEvidenceLine` result, `Intervalo: {interval_start} → {interval_end}`, `Completitud {n}%` beside `Cobertura`, `Calidad:` and `Discrepancias:` — each bound ONLY when served. Antecedent rows print only what DIVERGES from the shared block. Makes 2.5 and 2.6 pass.
- [ ] 2.8 GREEN `RainfallMetricList.tsx` — ONE dimmed snapshot-level line at the fold's foot, `Estado de fuentes: …` through `stringifyUnknownFields`, rendered only when present AND when the guard yields output. Never repeated per metric (`source_health` is a snapshot root key, `lib/api/rainfall.ts:94`). Relocate `rainfall-summary` to sit under the shared block, inside the technical fold.
- [ ] 2.9 RED `tests/unit/RainfallMetricList.test.tsx::"isMetricGroup is total"` + `::"an unknown group renders under its raw key"` — an extra root key that is a string, a number, `null`, an array or `{}` renders NO group and does not THROW (`'metric' in "texto"` is a `TypeError`); a genuinely unknown metric-shaped group renders under its RAW key with raw metric labels (`metricLabel ?? key`), and no served metric is omitted.
- [ ] 2.10 GREEN `RainfallMetricList.tsx` — key-driven renderer: iterate the snapshot's OWN root keys, known keys first in `GROUP_TITLES` order, then any other entry passing `isMetricGroup(value)` titled `GROUP_TITLES[key] ?? key`. `isMetricGroup` does `null`/`typeof`/`Array.isArray` checks BEFORE any `in`. Deny-list the non-group root keys: `analysis_revision_id`, `data_revision`, `scope`, `regional_estimate`, `year`, `comparison_end`, `baseline`, `summary`, `source_health`, `metric_policy`. With the guard in place, delete the `intensity` entry from `GROUP_TITLES` (`RainfallMetricList.tsx:32`) and the 8 intensity labels from `RAINFALL_METRIC_LABELS` (`rainfallFormat.ts:21-28`). Makes 2.9 pass.
- [ ] 2.11 RED `tests/unit/RainfallDetailPanel.test.tsx::"nothing served disappears"` — with EVERY disclosure expanded, the rendered `rainfall-metric-*` key set equals the union of the snapshot's group keys, and each metric carries its state, reason and provenance (success criterion 4).
- [ ] 2.12 `tests/e2e/rainfall-v2-detail.spec.ts` — the missing unknown-group WITNESS (D8): expand `rainfall-technical-header`, then assert the fixture's `intensity` group (`:147-148`) renders inside `rainfall-technical-body` under its RAW key with the raw `p24h` metric key. The CSV assertion at `:161` is NOT touched — `P24h (mm en 24 h)` lives in the mocked `CSV_BODY` (the BACKEND's export label), so pruning the front-end labels cannot move it.
- [ ] 2.13 DOC `specs/rainfall-analysis/spec.md` (this change's delta) — add ONE reconciling clause to the MODIFIED "Metric Provenance and State Metadata" requirement (UXJA-203): the enumerated floor's `available_through` entry is satisfied by the metric's evidence statement, so a metric whose evidence cannot be established (the gate's third branch) renders NO date rather than the raw window bound. No scenario is added, removed or reworded. Proving check: reviewer diff of the delta file.

---

## Ops

- [ ] O.1 Execute the DECLARED LOCAL RUN of design D13 for `tests/e2e/rainfall-v2-detail.spec.ts`, as a slice-1 merge gate, with ALL FIVE preconditions satisfied and each one evidenced:
  1. catastro dataset loaded (otherwise `clickFixtureParcela`'s tile gate skips);
  2. `E2E_API_BASE=http://localhost:8000` (otherwise `probeFichaAvailability` soft-skips every test);
  3. `E2E_APP_URL=http://localhost:5173` (this is what turns `requireCondition` from a skip into a FAILURE — `strictGate.ts`);
  4. **`FICHA_ENABLED=true` reaching the BACKEND SERVICE** — `app/config.py:124` defaults it to `False` and no compose/env file in the repo sets it, so without it the probe returns `'off'`;
  5. **Martin reachable from the browser's host** — the compose service is docker-network-only, while the SPA resolves tiles from `VITE_MARTIN_URL || 'http://localhost:3000'`; use a compose override publishing `3000` or point `VITE_MARTIN_URL` at a reachable Martin.

  ```
  FICHA_ENABLED=true docker compose up -d postgres backend
  docker compose up -d martin   # + the host route of precondition 5
  npm --prefix consorcio-web run dev
  E2E_APP_URL=http://localhost:5173 E2E_API_BASE=http://localhost:8000 npm --prefix consorcio-web run test:e2e:rainfall
  ```

  Acceptance: the run EXECUTES — a report showing every test in the describe RUN (not skipped), the zero-scroll case among them, and all 15 rainfall testids plus `ficha-precipitacion` resolving. A skipped run is a FAILED gate, not a pass. **The verify phase MUST confirm this executed end-to-end (an executed check, not an inspected one) — the three-strikes history of this gate (canary → preview → local) earns it.** CI does not gate this criterion and this change does not claim it does.
- [ ] O.2 Bundle gate per D12, ONCE PER SLICE at the gate (not per commit): `npm --prefix consorcio-web run build`, then `find consorcio-web/dist/assets -name '*.js' -exec sh -c 'gzip -9 -c "$1" | wc -c' _ {} \; | paste -sd+ - | bc` on the merge-base and on the slice head. Acceptance: delta ≤ 3072 bytes, RECORDED as a number in the apply record (an unmeasured bundle claim is the defect this gate exists for). The sum is a regression tripwire, not a page-weight model.

---

## Coverage: Delta-Spec Requirements and Scenarios → Tasks/Tests

| Requirement | Scenario / MUST | Task(s) | Test |
|---|---|---|---|
| Metric Provenance and State Metadata | MUST: enumerated floor rendered, reachable by at most ONE disclosure control | 2.2, 2.7 | `RainfallDetailPanel.test.tsx::"the enumerated field floor is reachable with one disclosure control"` |
| Metric Provenance and State Metadata | MUST: source health rendered ONCE for the analysis, never per metric | 2.8 | same test (`source_health` once at the fold's foot) |
| Metric Provenance and State Metadata | MUST: unserved field never fabricated, never a placeholder | 2.6, 2.7 | `RainfallDetailPanel.test.tsx::"an unserved field renders no line…"` |
| Metric Provenance and State Metadata | MUST: `available_through` never shown as evidence for a metric that has none; suppression ≠ absence | 2.4, 2.13 | `rainfallFormat.test.ts::"metricEvidenceLine — three branches"` |
| Metric Provenance and State Metadata | MUST: consolidation allowed only on identical source/resolution/revision; divergence surfaces at the metric | 2.1, 2.2, 2.7 | `rainfallFormat.test.ts::"hoistProvenance"` |
| Metric Provenance and State Metadata | Displayed metric exposes complete provenance | 2.2, 2.7, 2.8 | `RainfallDetailPanel.test.tsx::"the enumerated field floor…"` |
| Metric Provenance and State Metadata | An enumerated field is not served | 2.6, 2.7 | `RainfallDetailPanel.test.tsx::"an unserved field renders no line…"` |
| Metric Provenance and State Metadata | The disclosure window has a value but nothing was published | 2.4 | `rainfallFormat.test.ts::"metricEvidenceLine — three branches"` (empty-window branch) |
| Metric Provenance and State Metadata | A policy-suppressed metric keeps its freshness | 2.4 (+1.4/1.5 at analysis level) | `rainfallFormat.test.ts::"metricEvidenceLine…"` (suppressed counterexample) + `::"deriveFreshness…"` case (b) |
| Metric Provenance and State Metadata | Gridded result is viewed from a parcel ficha | 1.10, 1.16 | `RainfallDetailPanel.test.tsx::"never claims parcel-level accuracy from nominal grid resolution"` (`:265`, kept green) |
| Metric Provenance and State Metadata | Metadata cannot be established | 2.6, 2.7 | `RainfallDetailPanel.test.tsx::"…a stripped metric renders only its state"` |
| Metric Provenance and State Metadata | Homogeneous displayed set consolidates provenance once | 2.1, 2.2, 2.7 | `rainfallFormat.test.ts::"hoistProvenance"` case (a) |
| Metric Provenance and State Metadata | Divergent metric keeps its own provenance | 2.1, 2.2, 2.7 | `rainfallFormat.test.ts::"hoistProvenance"` case (b) |
| Metric Provenance and State Metadata | Two normals of different scope are shown together | 1.9, 1.10, 1.19 | `RainfallAnswerCard.test.tsx` (scope line `Ámbito: Zona`) + `FichaTerritorialRainfallMount.test.tsx` (fold title *recorte de la parcela*) |
| Authenticated Technical Rainfall Detail | MUST NOT create a dedicated Rainfall v2 page | all (no route added) | absence check: `rg -n "'/lluvia'" src/routes` returns nothing |
| Authenticated Technical Rainfall Detail | MUST: public normal readable with no disclosure control when it is the reader's only rainfall content | 1.18, 1.19 | `FichaTerritorialRainfallMount.test.tsx::"staff + non-parcela ficha → fold OPEN"` |
| Authenticated Technical Rainfall Detail | Authorized staff opens technical detail | 1.15, 1.16 | `RainfallDetailPanel.test.tsx::"renders the technical detail for staff (operador)"` (`:219`) + e2e `operador: detalle visible…` |
| Authenticated Technical Rainfall Detail | Unauthenticated visitor views public rainfall content | 1.18, 1.19, 1.21 | e2e `puerta de autorización: anónimo NO ve el detalle de lluvia` (`ficha-precipitacion` visible, fold open) |
| Authenticated Technical Rainfall Detail | Authenticated user without technical authorization requests detail | 1.18, 1.19 | e2e `puerta de autorización: ciudadano…` + `FichaTerritorialRainfallMount.test.tsx::"non-staff + parcela → OPEN"` |
| Authenticated Technical Rainfall Detail | Non-technical reader lands on the rainfall area | 1.18, 1.19 | `FichaTerritorialRainfallMount.test.tsx` D7 predicate cases |
| Answer-First Rainfall Presentation Hierarchy | MUST: percentile + selected-year total + normal-to-date + freshness all on the ALWAYS-VISIBLE surface | 1.5, 1.9, 1.10, 1.15 | `RainfallAnswerCard.test.tsx` (headline, `AnnualText`, `rainfall-freshness`) |
| Answer-First Rainfall Presentation Hierarchy | MUST: percentile is the typographic headline, NO badged row on the always-visible surface | 1.9, 1.10, 1.15 | `RainfallAnswerCard.test.tsx::"no badged percentile row on the card"` + 1.16 (the badged row now lives in the technical fold) |
| Answer-First Rainfall Presentation Hierarchy | MUST: freshness derived ONCE PER SUBJECT; divergence disclosed, never averaged | 1.5, 1.14, 1.15 | `RainfallDetailPanel.test.tsx::"freshness is derived once per subject"` |
| Answer-First Rainfall Presentation Hierarchy | MUST: the freshness claim keys on EVIDENCE, never on policy state | 1.4, 1.5 | `rainfallFormat.test.ts::"deriveFreshness — the three-branch evidence gate"` |
| Answer-First Rainfall Presentation Hierarchy | MUST NOT introduce a page, multi-year fan-out, public v2 exposure, backend/contract change or a new dependency | all | absence checks: no `package.json` dependency delta, `gee-backend/**` untouched, `.github/workflows/**` untouched |
| Answer-First Rainfall Presentation Hierarchy | Answer is visible without scrolling on a phone | 1.14, 1.20, 1.22, O.1 | unit: order + both folds collapsed; e2e: `rainfall-answer-card` box vs `ficha-territorial-panel-sheet-body` (`requireCondition`) |
| Answer-First Rainfall Presentation Hierarchy | Percentile is not duplicated (reworded) | 1.8, 1.9, 1.10, 1.15 | `RainfallAnswerCard.test.tsx` (headline once + the phrase inside `rainfall-annual-text` + no badged row) |
| Answer-First Rainfall Presentation Hierarchy | Freshness is on the answer surface, derived once per subject | 1.5, 1.14 | `RainfallDetailPanel.test.tsx::"freshness is derived once per subject"` |
| Answer-First Rainfall Presentation Hierarchy | An analysis with no published evidence | 1.4, 1.5, 1.9 | `rainfallFormat.test.ts::"deriveFreshness…"` case (c) + card branch test |
| Answer-First Rainfall Presentation Hierarchy | The year's value is suppressed by policy but its evidence exists | 1.4, 1.5, 1.9 | `rainfallFormat.test.ts::"deriveFreshness…"` case (b) |
| Answer-First Rainfall Presentation Hierarchy | Freshness cannot be established | 1.4, 1.5, 1.9 | `rainfallFormat.test.ts::"deriveFreshness…"` case (d) + the card's `title`/`aria-label` reason |
| Derived Interpretive Rainfall Label | MUST: derived ONLY from the served percentile, with published cut-offs, presented as derived | 1.1, 1.2, 1.9, 1.10 | `rainfallFormat.test.ts::"wetnessFromPercentile…"` + `RainfallAnswerCard.test.tsx` (`rainfall-wetness` sentence) |
| Derived Interpretive Rainfall Label | Label at a published cut-off boundary | 1.1, 1.2 | `rainfallFormat.test.ts::"wetnessFromPercentile — every published cut-off from both sides"` |
| Derived Interpretive Rainfall Label | Label is shown as derived | 1.9, 1.10 | `RainfallAnswerCard.test.tsx` (`categoría derivada del percentil 72 de 1991-2020`) |
| Derived Interpretive Rainfall Label | Percentile is suppressed | 1.1, 1.9, 1.10 | `rainfallFormat.test.ts` (`null` on suppressed) + `RainfallAnswerCard.test.tsx` (no label, reason displayed) |
| Progressive Disclosure Without Data Loss | MUST: a collapsed section shows its key values in the collapsed header | 1.6, 1.7, 1.14, 1.15 | `rainfallFormat.test.ts::"compactAntecedent"` + `RainfallDetailPanel.test.tsx` accessory test |
| Progressive Disclosure Without Data Loss | MUST: the visible chart's textual equivalent stays rendered, outside any collapsible, and COMPLETE (ranking included) | 1.8, 1.10, 1.14 | `RainfallDetailPanel.test.tsx` R7 witness + the moved percentile-phrase tests |
| Progressive Disclosure Without Data Loss | MUST: every served metric group rendered, unknown ones with a visible fallback title | 2.9, 2.10, 2.12 | `RainfallMetricList.test.tsx::"isMetricGroup is total"` / `::"an unknown group renders under its raw key"` + the e2e witness |
| Progressive Disclosure Without Data Loss | Collapsed section still carries its numbers | 1.6, 1.7, 1.14 | `RainfallDetailPanel.test.tsx` accessory test (order, unit once, `—` + reason) |
| Progressive Disclosure Without Data Loss | Visible chart keeps its textual equivalent | 1.10, 1.14 | `RainfallDetailPanel.test.tsx::"R7 witness — every fold closed"` |
| Progressive Disclosure Without Data Loss | Unknown metric group is served | 2.9, 2.10, 2.12 | `RainfallMetricList.test.tsx` + e2e `intensity` raw-key assertion |
| Progressive Disclosure Without Data Loss | Nothing served disappears | 2.11 | `RainfallDetailPanel.test.tsx::"nothing served disappears"` |

**Coverage summary**: 26 delta scenarios (9 + 4 + 6 + 3 + 4) and 13 requirement-level MUST rows — all mapped. No delta scenario and no design decision is left without a task.

## Constraint Coverage (R1–R7)

| # | Where it is discharged |
|---|---|
| R1 | 1.9/1.10 (card `Ámbito: Zona/Cuenca`) + 1.19 (fold title *recorte de la parcela*) |
| R2 | 1.1/1.2 (single pure function, published cut-offs, boundary tests) |
| R3 | 1.3 (one `lastEvidenceDay`), 1.5 (no re-derivation), 1.10 (`null` never rendered as 0), 1.14 (R7 witness) |
| R4 | 1.16 (unit expand-before-assert — the CI-gated half), 1.21 (e2e sentinel + expand), O.1 (executed local run) |
| R5 | no dependency delta in `package.json` (checked at 1.23 and O.2) |
| R6 | 2.9/2.10 (total guard BEFORE the prune) + 2.12 (e2e witness) |
| R7 | 1.10/1.11 (`AnnualText` above the first fold) + 1.14 (witness with every fold closed) |

## Suites and Gates NOT Touched (D13, and stated so nobody re-proposes them)

- `tests/accessibility/a11y.spec.ts` — audits public routes and never authenticates, so it never reached this panel. No delta. `tests/ui/CollapsibleSection.test.tsx` already pins `aria-expanded`/`aria-controls`/`role="region"` for the primitive, which is reused unchanged.
- `test:e2e:canary` and `CANARY_READ_ONLY_SPECS` (`gee-backend/tests/test_ci_workflow_contracts.py:815-859`) — a production-safety allowlist. Untouched.
- `.github/workflows/**` — no new job, no e2e step (`test_ci_workflow_contracts.py:799-808` forbids the strings anyway). `gee-backend/**` untouched.
