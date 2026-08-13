# Design: Lluvia Tab — Answer-First Card (Direction A)

Upstream: `openspec/changes/lluvia-ux-tarjeta/proposal.md` (owner-approved), Engram `sdd/lluvia-ux/explore` (#13726). Mode: hybrid.

## Technical Approach

A render-tree rearrangement of the staff Lluvia surface. `RainfallDetailPanel` stays the ONLY stateful node (scope, year, campaign preset, export, announcer, render gate) and the only place a derived fact is computed; every new or reshaped child is a pure function of its props — `snapshot` plus, for the card, the `freshness` value the panel derives once — with no hook, no store and no query. That is what makes direction C (a `/lluvia` page) a re-mount instead of a rewrite. No new dependency, no route, no backend or contract change (R5). Delivered as two chained PRs; slice 1 is shippable and defensible alone.

Verified constraints driving the design: `CollapsibleSection.tsx:113` unmounts its body when closed (→ R7/R4); `openspec/specs/rainfall-analysis/spec.md:11` forbids a dedicated page; `compute.py:476-656` emits ONLY `annual` + `antecedents` (no `intensity`, no `source_health`) → R6; `compute.py:339,455` build `provenance.available_through` from the EXCLUSIVE window end, same semantics the chart's `lastEvidenceDay` already converts.

## Architecture Decisions

### D1 — Component architecture

**Choice**: new presentational `RainfallAnswerCard.tsx` (props: `{ snapshot, freshness }` — two values, no hook, no query). `RainfallMetricList.tsx` splits into `RainfallMetricRow` → `RainfallMetricGroup` (one group) → `RainfallMetricList` (composition + provenance block + summary), the last one gaining `exclude?: readonly string[]`. Container state stays in `RainfallDetailPanel`.
**Rejected**: card reading `useRainfallAnalysis` itself (couples it to the floating panel, kills C); card re-deriving freshness from the snapshot on its own (a second derivation of the fact R3 forbids re-deriving); one mega-component with layout flags (untestable branches).
**Rationale**: the C-migration constraint is a props contract, not an intention, and `freshness` is a plain value — the card stays a pure function of its props and re-mounts onto a `/lluvia` page unchanged. `exclude` (not `include`) lets the technical fold say "everything the card and the antecedents fold did not already show", so a new server group lands in the fold by default instead of nowhere (R6-compatible).

**D1a — freshness is derived once PER SUBJECT** (closes the spec floor "freshness as the last day with evidence" for the answer surface). There are exactly two subjects on this surface, and each is converted exactly once: the stored ANALYSIS — `RainfallDetailPanel` calls `deriveFreshness(snapshot)` ONCE and passes the result down, so nothing below it converts the analysis' date again — and the plotted SERIES, converted once by the chart that owns the `/series` response and describes the line it drew. "Once for the whole view" would be the wrong rule: it would force one number to stand for two different objects that can legitimately disagree.

| surface | what it states | source | why it is not a duplicate |
|---|---|---|---|
| card (`rainfall-freshness`, always visible) | the stored ANALYSIS' last day with evidence | `annual.selected.provenance.available_through` via `lastEvidenceDay`, gated on the EVIDENCE gate below (never on policy state) | required by the answer-first requirement: the reader must know how fresh the numbers ABOVE it are, without opening anything |
| chart footer `rainfall-accumulation-dates` + `role="img"` label | the plotted SERIES' comparison end and last evidenced day | the `/series` response (live) | required by base spec "Chart Discloses Comparison Date and Freshness" — a statement about the drawn line, a different object |
| technical fold (D9) | the per-metric `provenance.available_through` of each metric | the same stored snapshot, same `lastEvidenceDay` | provenance inspectability per metric; NOT a third derivation and NOT a second source (see D9a) |

The two visible sentences agree whenever the served series still matches the revision; they can only disagree in the case `rainfall-series-stale` already announces directly above the footer (`RainfallAccumulationChart.tsx:298-301`, pin inconsistency or `data_revision` echo mismatch). The card therefore names its subject ("de este análisis") and the chart footer keeps naming the series — the divergence is disclosed, never silently averaged into one number.

**The gate keys on EVIDENCE, never on policy state.** It is load-bearing in both directions, and each direction is a defect this repo has already produced once:

- **Never a stamped fallback.** `compute._disclosure_window` falls back to `comparison_end + 1 day` when the analysis published zero intervals, so `available_through` alone is never proof that evidence exists (the JDB-103 defect, already fixed once in the chart).
- **Never "no evidence" for a metric that has some.** The tempting converse — print the date only when `annual.selected` is `available`/`partial` — is a different defect: suppression is a statement about whether the NUMBER may be shown, not about whether days were measured. `apply_metric_policy` returns `suppressed` / `coverage_below_threshold` for a metric whose coverage is real but below the served threshold (`policy.py:166-167`), and `_normalize_metric` blanks only `value`, keeping that metric's `coverage`, `provenance` and `interval_*` intact (`service.py:493,518`). `coverage_below_threshold` ≠ no data.

So the gate reads the EVIDENCE facts that survive normalization, and nothing else:

| branch | condition on the served (post-normalization) `annual.selected` | the card prints |
|---|---|---|
| evidenced | `provenance.available_through` is served AND `coverage > 0` (a served numeric `value` is the same fact and satisfies the branch too) | `Evidencia publicada hasta el {lastEvidenceDay(available_through)}` |
| empty window | `state === 'unavailable' && reason === 'no_data_in_disclosure_window'` — the ONE server fact meaning the disclosure window published nothing (`compute.py:649-650`) | `Sin días con evidencia publicada en este análisis` |
| indeterminate | neither: `annual.selected` is absent, or it was served in `service._unavailable`'s STRIPPED four-field shape (`metric`/`value`/`state`/`reason` only — `service.py:466-472`), which carries no `provenance` and no `coverage` | `Frescura no disponible en este análisis`, with the served `reason` in `title` + `aria-label`. No date (there is no source for one) and no no-evidence claim (nothing proves the window was empty) |

`deriveFreshness` returns WHICH branch it took (`kind`, in the Interfaces block), so the card, the fold and the tests key on a discriminator instead of matching a sentence.

**Why the two visible sentences cannot contradict each other, under THIS gate.** Take the case that breaks the state-keyed version: a year with 62 % coverage, below the served policy floor. The server suppresses `annual.selected` (`coverage_below_threshold`) but keeps its `coverage: 0.62` and its real `available_through`; the `/series` response still carries the evidenced days, so the chart footer prints `2026-02-09`. A state-keyed card would print `Sin días con evidencia publicada en este análisis` directly above a chart declaring evidence through 2026-02-09 — one screen asserting both that no day has evidence and that days do. Under the evidence gate the card takes the `evidenced` branch and prints the same 2026-02-09 (the value is still withheld — that is the suppression — but the freshness is stated), so the contradiction is not reachable. The only divergence left is the disclosed one described above the table: a served series that no longer matches its revision.

### D2 — Fold structure and the R7 guarantee

**Choice**: always-mounted: announcer, header, controls row, **answer card**, **accumulation chart**, export row. Folded with `CollapsibleSection defaultOpen={false}`: `Antecedentes` (values in `rightAccessory`), `Detalle técnico`. `AnnualText` MOVES into `RainfallAnswerCard`, keeping `data-testid="rainfall-annual-text"`.
**Rejected**: an always-mounted `hidden`-attribute variant of `CollapsibleSection` (a second collapse semantics in a shared primitive, for one caller); leaving `AnnualText` in the metric list (it would ride into the fold and unmount → R7 violation, the chart loses its textual equivalent for screen readers).
**Rationale**: R7 is satisfied structurally — the equivalent lives above the first fold, so no fold state can remove it. The primitive stays untouched (proposal approach §3).

**D2a — the collapsed `Antecedentes` header, specified** (the spec delta requires the numbers to survive the collapse, so the accessory is a contract, not a decoration):

- Content: `7d 31 · 30d 84 · 90d 12 mm`, in the fixed order d7 → d30 → d90.
- **The values come from a new `compactAntecedent(metric): string`, NOT from `formatAccumulated`.** The first draft said "rounded by the same `formatAccumulated` the rows use", which was simply false: `formatAccumulated` is `value.toFixed(1) + ' ' + unit` (`rainfallFormat.ts:56-58`), so it yields `31.0 mm` — a decimal the header has no room for and a unit repeated three times. `compactAntecedent` is one line and its own decision: `Math.round(value)` (no decimals — a tenth of a millimetre is not a fact anyone reads off a collapsed header), no unit, `—` when there is no value to state. The rows keep `formatAccumulated` unchanged; the two formatters have different jobs and one call site each.
- The unit is stated ONCE, at the END of the accessory (`… mm`), never per value — three units inside a ~26-character string is what makes the header unreadable at 348 px.
- A metric that is not `available` prints `—` (never `0`, per "Partial, Suppressed, and Unavailable Data States") and the accessory carries its reason in `title` + `aria-label` on that item, so the state is reachable without expanding.
- **The unavailable-LAST case is deliberate, not an oversight**: `7d 31 · 30d 84 · 90d — mm` reads oddly and is accepted. The alternatives are worse — moving the unit before the `—` reintroduces per-value units, and dropping it when the last metric is absent makes the unit's position depend on data, so a reader cannot learn where to look. The `—` item's `aria-label` carries the reason, so what a screen reader hears is the state, not the dash.
- Width: the accessory is `Text size="xs"` with `truncate` inside the header's right slot. The example above is **26 characters**; three-digit antecedents (`7d 310 · 30d 840 · 90d 120 mm`) make it **29**. Both fit beside a short title at 348 px; a longer title truncates the accessory, and the values stay in the DOM for the accessibility tree. (The earlier "~24 characters" was counted without the trailing unit.)

**Owner ratification (2026-08-11)**: `Antecedentes` starts COLLAPSED at every size, desktop included, with the values visible in the collapsed header. A 380 px floating card pays the same scroll cost as the 390 px sheet, and one behaviour is one thing to test. This closes the open question that asked whether desktop should differ.

### D3 — Where the percentile is printed

**Choice**: headline `Percentil 72` (large) in the card + the same percentile inside `rainfall-annual-text`. The badged `rainfall-metric-percentile` ROW moves into the technical fold.
**Rejected**: dropping the percentile from `AnnualText` (regresses tasks 4.7/4.8 and R3 — the textual equivalent must answer "wet or dry?" without the chart).
**Rationale**: today's duplication is *headline-less fragment + badged row on the same visible surface*. After the change the visible surface carries the answer once as a headline and once inside the accessible sentence that exists precisely to restate it in text; the badged row — the redundant one — is one click away, not deleted. The delta now says exactly this instead of "presented once": the badged row on the always-visible surface is forbidden, and the restatement inside the chart's textual equivalent is required by THIS change's own "Progressive Disclosure Without Data Loss", which now demands the equivalent be complete — the ranking is a fact the plot shows visually, so a sentence that drops it is a partial equivalent for exactly the readers it exists for. The base "Chart Discloses Comparison Date and Freshness" is NOT the authority here and never was: it governs the two DATES disclosed alongside the plotted series (`openspec/specs/rainfall-analysis/spec.md:464-468`) and says nothing about the percentile or about a textual equivalent.

### D4 — Derived adjective (R2)

**Choice**: pure `wetnessFromPercentile(metric) → RainfallWetness | null` in `rainfallFormat.ts`, applied to the value **already rounded** by the same `Math.round` `percentilePhrase` uses. Published cut-offs (integers, symmetric around 50):

| rounded percentile | label |
|---|---|
| `p ≤ 10` | muy seco |
| `11 ≤ p ≤ 30` | seco |
| `31 ≤ p ≤ 69` | normal |
| `70 ≤ p ≤ 89` | húmedo |
| `p ≥ 90` | muy húmedo |

Rendered as `Año húmedo · categoría derivada del percentil 72 de 1991-2020` (`rainfall-wetness`) — the derivation and the served baseline are IN the sentence, never colour-only. No adjective at all when the percentile is absent, `value === null`, or `state ∈ {suppressed, unavailable}`.
**Rejected**: terciles 33/67 (a Weibull rank over ~31 samples moves in ~3-point steps — already documented in `percentilePhrase` — so a tercile boundary flips the WORD on a one-sample move); BoM deciles 20/40/60/80 (four boundaries in the busy middle, same instability); re-deriving wetness from `annual.selected` vs `normal` (forbidden by R2).
**Rationale**: 30/70 is the US Drought Monitor's operational abnormally-dry / wet-mirror threshold and 10/90 are deciles 1 and 10 — established vocabulary, not invented. The wider neutral band makes the label move LESS often than the number it describes. Rounding first is load-bearing: percentile 69.6 prints "Percentil 70", so the label must be "húmedo" or the card contradicts itself.

**Owner ratification (2026-08-11)**: the cut-offs above (≤10 / 11-30 / 31-69 / 70-89 / ≥90, applied to the ALREADY-rounded percentile, no label when the percentile is suppressed) are approved as published, user-visible vocabulary. This closes the open question that held slice 1.

**Disclosed instability (n-variability)**: the label tracks the SERVED percentile, and the served percentile is a Weibull rank over a discrete sample, so the label can move when the baseline's eligible-year count changes even if the year's rain did not. The rank step is `100 / (n + 1)`: **3.125 points at n = 30** (a full 1991-2020 baseline) and **4.545 points at n = 20** (the eligibility floor) — the worst case. A year sitting within one step of a cut-off can therefore change adjective on a baseline that gained or lost one eligible year. Two consequences, both taken deliberately:

1. This is exactly why the boundaries are 10/30/70/90 and not terciles: a 4.5-point step crossing a 40-point-wide neutral band is a rare event, while the same step crossing a 33/67 boundary is a coin flip.
2. The sentence already states its own derivation (`categoría derivada del percentil 72 de 1991-2020`), so a reader who sees the word move can see the number and the baseline that moved it. No extra caveat copy is added — the design records the property here, and the boundary unit tests pin it.

### D5 — Provenance hoist (slice 2)

**Choice**: **per-field** hoist over the displayed set. `hoistProvenance(metrics) → { shared, perMetric }`; a field is `shared` iff the set is non-empty and every metric's value is strictly equal. Candidate fields: the 8 `provenance` keys + metric-level `revision`. One block at the top of the technical fold; each row prints ONLY the non-hoisted fields, plus `coverage`, `completeness`, `interval_start` and `interval_end`, which are per-metric by definition and never hoisted.

**The comparison set is guarded exactly like D8's renderer.** A metric served WITHOUT provenance — `service._unavailable`'s stripped four-field shape (`service.py:466-472`), which is what a contract/policy/quality rejection produces — is EXCLUDED from the set `hoistProvenance` compares, and renders its stripped state per D9a rule 3 (state + reason, no provenance lines). Including it would make every field diverge against a metric that carries none, collapsing the hoist to zero shared fields and putting six identical provenance blocks back on the rows — the exact defect this decision exists to remove, triggered by one unrelated metric being rejected. The set may end up empty (every metric stripped); then there is no shared block at all, which rule 3 already covers.

**Scope of the shared block, and why one control still reaches everything** (this is what the delta's "reachable by operating at most one disclosure control" buys): the block covers ALL displayed metrics of BOTH folds — annual and antecedents — and says so in its own words ("Vale para todas las métricas mostradas"), not "de esta sección". The antecedent rows themselves print only what DIVERGES from it. The at-most-one-control floor holds either way, because the control need not be the same one for every field: opening the technical fold alone (one control) exposes the shared block, which carries the antecedents' shared provenance; opening the antecedents fold alone (one control) exposes their values, states and any divergent field. No field requires opening two folds, and the antecedent rows are not left provenance-homeless — which is what the first draft, with a block scoped to "esta sección", quietly did.
**Amendment (2026-08-12, slice-2 fix round — resolves the UXJB-110 ↔ UXJA-107 contradiction, ledger `S2R3-001`):** the two paragraphs above contradicted each other and the code implemented both halves literally. UXJB-110 EXCLUDES a metric served without provenance from the comparison set; UXJA-107 made the block say "Vale para todas las métricas mostradas" — a claim over the DISPLAYED set, which includes that excluded metric whenever the backend strips one (`service.py:479-518`, reachable per metric). The block therefore over-claimed its own scope. **Resolution: the sentence is DERIVED, the comparison set is untouched.** The universal wording survives only when the exclusion removed nothing; when a stripped metric is displayed the block scopes itself — `Vale solo para las métricas con procedencia servida, …`. The fold clause is derived too: `y en Antecedentes` is stated only when a non-empty `antecedents` group makes that fold mount (`RainfallDetailPanel.tsx:570`), so the block never names a control that is not on screen. Excluding a metric from the SET stays right (comparing it collapses the hoist to zero shared fields); the defect was only ever the sentence, and the excluded rows remain value-less and self-identifying (`—`, `Estado: No disponible`, `Motivo: …`), so no number can be mis-sourced. Implemented in `sharedProvenanceScope` (`RainfallMetricList.tsx`), pinned by two panel tests (mixed snapshot; no-antecedents snapshot).

**Rejected**: all-or-nothing hoist (under-hoists in the common case where only `revision` differs after a policy bump, and the reader gets 6 identical lines again); hoisting `coverage` (it is the metric's own quality, hoisting it would state a claim about metrics that do not share it); hoisting `interval_start`/`interval_end` (they are what makes d7 different from d90 — hoisting them would erase the very distinction the antecedents group exists for, and they are equal only by accident inside `annual`).
**Rationale**: satisfies both halves of the success criterion — one string when all agree, a divergent metric still shows its own — while keeping spec.md:154-163 inspectability: every field of the enumerated floor is readable for every metric as `shared ∪ row`.

### D6 — Controls consolidation

**Choice**: one `rainfall-controls` block directly under the header, holding the two controls that re-query: row 1 scope `SegmentedControl` (only when >1 choice), row 2 the year `NativeSelect`, on `flex: '1 1 160px'; minWidth: 0`. It stays OUTSIDE the snapshot render gate, exactly as today — it is how the reader moves while the analysis is loading, queued or unavailable.

The campaign preset stays where the chart renders it — inside the gate, in the chart's own header row, same `rainfall-campaign-preset` testid — but its STATE is lifted: `preset` and `onPresetChange` become **required** props of `RainfallAccumulationChart`, its internal `useState` and the uncontrolled branch are deleted. One code path, and D1's rule holds (`RainfallDetailPanel` is the only stateful node), which is also what lets direction C carry the preset in a URL.

**Rejected**: the dual-path controlled/uncontrolled chart of the first draft (two behaviours in one component of which only one ever ships — the untested path is the one that rots, and "optional prop" would let a future caller silently get a second source of truth); moving the preset up into `rainfall-controls` beside the year select (it would then render during loading/queued/unavailable — a live control windowing a series that does not exist yet, i.e. a dead control, which is the honesty defect this design is supposed to remove, and it would also unmount and remount with the gate); `SimpleGrid cols={{ base: 1, xs: 2 }}` (Mantine breakpoints read the VIEWPORT — inside a 380 px fixed card on a 1920 px screen they claim two columns that do not fit).
**Rationale**: the reader's complaint (finding #9) is that the year and the preset sit ~300 px apart with the metric list between them. After the reorder the chart mounts directly under the card, so `rainfall-controls` and the preset are ~1 block apart and read as one control area, while each keeps the lifecycle its own subject has. Widths: 348 px usable at `map.module.css:251` (`min(380px, 100% - 72px)`) and ~366 px in the 390 px bottom sheet; the scope/year rows fit at 160 px each and the wrap is container-driven, so it degrades by stacking, never by overflowing.
**Slice-1 task (consequence, not a footnote)**: `tests/unit/RainfallAccumulationChart.test.tsx` mounts the chart through one `renderChart()` helper (`:230`) and drives the control directly in the `campaign display preset (4.5)` block (`:623`). Making the props required means updating that helper to own the preset state (a controlled test wrapper). Every mount in that file goes through `renderChart` (26 call sites, one `render(` — the helper's own), so this is one edit plus the two preset tests, and it is listed in the slice-1 estimate.

### D7 — `PrecipChart` accordion default

**Choice**: in `FichaTerritorialPanel`'s `PanelBody` (`:496`, a real component — hooks are legal), read `useCanAccess(['admin','operador'])` as a LAYOUT hint and key the default on the CONTENT that will actually render, not on the role:

```tsx
// TOP of PanelBody, above every early return (:523 isLoading, :534 isError/!data).
const staff = useCanAccess(['admin', 'operador']);
// The EXACT mount predicate of the v2 detail, reassembled from its two homes:
// `tipo === 'parcela' && parcelaProps?.nomenclatura` gates the mount at
// FichaTerritorialPanel.tsx:606; the third conjunct — staff — is not there, it
// is the `if (!canAccess) return null` inside RainfallDetailPanel.tsx:133.
const v2DetailWillRender = staff && tipo === 'parcela' && !!parcelaProps?.nomenclatura;

<CollapsibleSection
  key={v2DetailWillRender ? 'precip-demoted' : 'precip-primary'}
  title="Precipitación mensual normal (recorte de la parcela)"
  defaultOpen={!v2DetailWillRender}
  testId="ficha-precip-fold"
>
```

The v2 detail renders ABOVE it.
**Rejected**: `defaultOpen={!staff}` (the first draft): a staff user on a ficha that is NOT a single parcel with nomenclatura gets NO v2 detail, so keying on the role alone would collapse the only rainfall content that user has — the exact harm the spec's "the public normal MUST be readable without operating a disclosure control" clause forbids, hidden behind an authorization word. A callback lifted out of `RainfallDetailPanel` (child→parent layout signalling with a first-render ordering hazard). Always-open (defeats the reordering for the users who do have the v2 detail).
**Rationale**: the fold is a statement about what else is on the screen, so it must be keyed on what else is on the screen. The authorization boundary is unchanged — the backend, plus the render gate that stays inside `RainfallDetailPanel`; this is the same store selector used as a display hint. R1 is served here too — this title says *recorte de la parcela* while the card states *Ámbito: Zona/Cuenca*, so the two "normal" numbers can no longer be read as the same pipeline.

**Hook placement (non-negotiable)**: the `useCanAccess` call goes at the TOP of `PanelBody`, above the `isLoading` early return at `:523` and the `isError || !data` early return at `:534`. Placing it lower — beside the JSX that uses it — would make it a CONDITIONAL hook: the loading and error renders would call zero hooks and the success render one, so the first transition from `ficha-loading` to `ficha-result` changes the hook count of the same component instance and React throws its "Rendered more hooks than during the previous render" invariant, crashing the whole ficha on the ordinary path every reader takes.

**The predicate is deliberately about MOUNTING, not about content richness** (adjudicated, confined): `v2DetailWillRender` is true whenever the panel mounts, including the runs where it renders only a queued, error or unavailable state. In those runs the reader gets a thin v2 detail above a collapsed public chart. That is accepted rather than patched: the fold header stays visible with its title, so the public normal is ONE click away — the spec's clause is about the reader for whom the public normal is the ONLY rainfall content, and a reader with a mounted (if degraded) v2 detail is not that reader. Keying on rendered richness instead would mean the fold's default flapping with a poll's answer, which is a worse experience than a stable default and one click. No predicate change; recorded here so a future reader knows it was weighed.

**Remount strategy (why the `key`)**: `CollapsibleSection` reads `defaultOpen` exactly once, into `useState` (`CollapsibleSection.tsx:69`); later prop changes are ignored by design. `v2DetailWillRender` CAN flip after mount — `useCanAccess` reads the auth store, which hydrates and can change on login/logout while the ficha is open — and without a remount the fold would silently keep the default computed from the pre-hydration value (a staff reader left with the public chart open above a v2 detail, or worse, a reader who lost staff access left with their only content collapsed). The `key` above remounts the section on exactly that flip, which is the sanctioned way to reset uncontrolled state and needs no change to the shared primitive. Cost, stated: a manual open/close the reader had performed is reset when the predicate flips. That flip only happens when the content itself changes, so the reset is honest rather than surprising, and it is the cheaper half of the trade against a stale default that no interaction can explain.

### D8 — Key-driven group renderer + `intensity` prune (slice 2, one commit)

**Choice**: `RainfallMetricList` iterates the SNAPSHOT's own keys: known keys first in `GROUP_TITLES` order, then any other entry passing `isMetricGroup(value)`, titled `GROUP_TITLES[key] ?? key`. With that guard in place, delete the `intensity` entry from `GROUP_TITLES` and the 8 intensity labels from `RAINFALL_METRIC_LABELS`.

The guard is TOTAL over `unknown` — it is fed whatever the wire carried, and `snapshot.summary` / `snapshot.source_health` are typed `unknown` on purpose:

```ts
function isMetricGroup(value: unknown): value is Record<string, RainfallMetric> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return false;
  const entries = Object.values(value);
  return (
    entries.length > 0 &&
    entries.every(
      (entry) => entry !== null && typeof entry === 'object' && 'metric' in entry && 'state' in entry
    )
  );
}
```

Both `typeof` checks come BEFORE any `in`: `'metric' in value` throws `TypeError: Cannot use 'in' operator` on a string, a number or `null`, so a server that starts emitting `"summary": "texto"` or a scalar under a new root key would take down the whole panel instead of being ignored — the exact opposite of R6's intent. `Array.isArray` is excluded because a JSON array is an object whose values could each look metric-shaped, and rendering a list as a keyed group would invent metric names from array indices.

The iteration runs over the snapshot's root keys MINUS an explicit deny-list of the keys that are not metric groups and already have their own renderer: `analysis_revision_id`, `data_revision`, `scope`, `regional_estimate`, `year`, `comparison_end`, `baseline`, `summary`, `source_health`, `metric_policy`. `metric_policy` is the completion of the list against the server's own envelope (`service.SNAPSHOT_ROOT_KEYS:201-221`): it is allow-listed at the root and `normalize_snapshot` copies it through, even though `RainfallAnalysisSnapshot` does not declare it. Today the total guard rejects it correctly (its values are thresholds and strings, not metric-shaped), so listing it changes no behaviour — it is listed because "the guard happens to reject it" is a weaker guarantee than "we know this key and it is not a group", and the next field added to the policy dict could change which of those two is true. The deny-list is not belt-and-braces — `source_health` is `unknown` on the wire, so a future shape like `{ chirps: { metric, state } }` would pass `isMetricGroup` and render as a metric group ON TOP of the single analysis-level line D9 gives it, which is the double-rendering the enumerated floor forbids. Only genuinely unknown keys reach the fallback title.

The crash this guards is not hypothetical: the e2e fixture already serves `summary: 'Año seco…'` (a string) and `source_health: { stations: 1, degraded: false }` (an object of scalars) at the root (`rainfall-v2-detail.spec.ts:150-151`). Under a guard that reaches `'metric' in entry` without the `typeof` checks, both shapes throw.
**Rejected**: keeping the dead labels "just in case" (dead-code-as-documentation is what produced finding #10); pruning before the guard exists (R6 violation — a silent drop); a partial guard that only checks `'metric' in value` (crashes on the scalar case above).
**Rationale**: `build_snapshot` cannot emit `intensity`. If it ever does, the group renders under its raw key with raw metric labels — the repo's standing rule for an untranslated fact (`metricLabel ?? key`, `export._label`) — which is visible, not dropped.
**Slice-2 task (was an unbacked claim)**: the e2e fixture carries `intensity.p24h` (`rainfall-v2-detail.spec.ts:147-148`), but NO assertion reads it as a rendered group — the only assertion that touches it is the CSV export row at `:161`. As written, the fixture witnesses the export, not the unknown-group fallback. Slice 2 adds the missing assertion: expand `rainfall-technical-header`, then assert the raw `intensity` title and the raw `p24h` metric key are present inside `rainfall-technical-body`. The CSV assertion at `:161` is NOT affected: `P24h (mm en 24 h)` lives in the mocked `CSV_BODY` fixture (`:156-162`), i.e. it is the BACKEND's export label, not `RAINFALL_METRIC_LABELS`; the download is served by the server (`downloadRainfallCsv`), so pruning the front-end labels cannot move it. Without it the sentence "the e2e fixture is the live witness of the unknown-group fallback" is false; with it, the fallback is covered end to end and a regression that drops unknown groups fails a test instead of a reader.

### D9 — Under-disclosure fields (slice 2, plain text — no new badge vocabulary)

| field | level | rendering | absence |
|---|---|---|---|
| `provenance.freshness` | metric | `Frescura: {iso}` in the shared block (or the row when divergent) | line omitted when the field is not served |
| `provenance.available_through` | metric | `Evidencia publicada hasta el {lastEvidenceDay(value)}` — **gated by the D1a evidence gate, applied per metric** (see D9a) | empty window → `Sin días con evidencia publicada para esta métrica`; indeterminate (stripped shape, no provenance) → no line at all; never a fallback date |
| `interval_start`, `interval_end` | metric | `Intervalo: {interval_start} → {interval_end}` on the row, never hoisted (D5) | line omitted when either end is not served |
| `completeness` | metric | `Completitud {n}%` beside `Cobertura` on the row | line omitted when the field is not served |
| `quality` | metric | `Calidad: k=v; …`, values stringified with a guard (never `[object Object]`) | line omitted when `{}` |
| `discrepancies` | metric | `Discrepancias: a; b` | line omitted when empty |
| `source_health` | **snapshot** | ONE dimmed line at the fold's foot, for the analysis — not repeated per metric; `Estado de fuentes: k=v; …` through the SAME stringify-with-guard `quality` uses (see below) | rendered only when present, and only when the guard yields at least one pair |

**D9a — the fold does not open a second date source.** The evidence row prints `lastEvidenceDay` over the metric's OWN `provenance.available_through`, from the same stored snapshot the card was fed, through the same function (D10). Four rules, all of them things this repo has already been bitten by:

1. **Same source.** The fold never reads the live `/series` response. The only two dated sources on this surface are the stored snapshot (card + fold) and the series (chart footer + lag notice), and each names its subject — see the D1a table.
2. **Same gate, applied per metric.** Each row runs D1a's three-branch EVIDENCE gate over its OWN fields — `coverage > 0` (or a served numeric value) → the date; `unavailable` + `no_data_in_disclosure_window` → the honest empty-window sentence; neither → no evidence line at all. Both failure modes are excluded by construction: printing `available_through` unconditionally would restate JDB-103 one layer down over a metric that measured nothing (with zero published intervals the fallback bound is ALWAYS present and ALWAYS plausible-looking), and keying on `state ∈ {available, partial}` would tell the reader that a policy-suppressed metric has no evidence when its own `coverage` on the same row says otherwise — the fold would contradict itself inside one row.
3. **No invented rows.** A field binds only when the snapshot serves it. Nothing renders a `—`, an empty label or a `null` placeholder to prove the field was considered; an unserved field simply has no line, which is what the spec delta's enumerated floor says ("whenever the served snapshot carries it"). This is also what a metric served in `service._unavailable`'s stripped four-field shape (`metric`/`value`/`state`/`reason` — `service.py:466-472`) renders: its state and reason, and NOTHING else — no provenance lines, no coverage, no evidence line, because none of it was served.
4. **One stringify guard, two fields.** `quality` and `source_health` both arrive as `unknown` on the wire and are printed by the same helper: a plain object becomes `k=v; k=v` pairs in key order (the flat `key=value` shape the backend already uses for `discrepancies`); scalar values (`string`/`number`/`boolean`) are printed as-is; `null`, arrays, nested objects and functions are SKIPPED rather than coerced, so `[object Object]` is unreachable; a non-object input (a bare string or number) prints as itself; and an input that yields zero pairs renders no line at all (rule 3). `source_health` is snapshot-level and `quality` is per-metric — different homes, one rendering rule, so the pair cannot drift into two different answers to "what does an object look like here".

**Rationale**: the proposal's scope decision, plus the wire types. `source_health` is a ROOT key of the snapshot (`lib/api/rainfall.ts:94`), not a member of `RainfallMetric` — rendering it per metric would attribute one analysis-wide fact to six metrics that never carried it. It is allow-listed at the root but never emitted by `build_snapshot`, so "render only when present" is not a nicety — it is the normal case. `interval_start`/`interval_end` (`lib/api/rainfall.ts:61-62`) are served on EVERY metric and were the two fields the first draft left out of the rendered set while claiming the set was complete.

### D10 — `lastEvidenceDay` reuse (R3) — **slice 1**, because the card needs it

**Choice**: MOVE `lastEvidenceDay` AND the sentence builder `evidenceFooter` from `RainfallAccumulationChart.tsx` (`:153` and `:178`) into `rainfallFormat.ts` (exported), in **slice 1**. Three callers, one implementation: the chart imports them back (behaviour byte-identical — its footer assertions, including the whole `the footer degrades honestly (JDA-104, JDB-103)` block, keep passing unchanged), the panel's `deriveFreshness` uses `lastEvidenceDay` for the card, and the technical fold (slice 2) uses the same pair on `provenance.available_through`.
**Rejected**: doing the move in slice 2 as first drafted — slice 1 introduces the card's freshness sentence, so postponing the move would mean slice 1 either re-derives the date (R3 violation, and the exact defect the function's docblock was written about) or duplicates the honest no-evidence copy; re-deriving in the fold; printing the raw value labelled "(exclusivo)" (leaks a window implementation detail into a reader-facing sentence).
**Rationale**: verified — `compute.py:339,455` set `available_through` to the exclusive window end, the SAME semantics the chart converts. `evidenceFooter` travels with it because the two are one decision: the conversion is meaningless without the gate that decides whether the claim may be made at all (JDA-104's unparseable-date fallback and JDB-103's no-evidence sentence both live in it), and a second copy of that copy is a second place for the two to drift.

### D11 — Slice boundary

| | slice 1 — re-hierarchy (existing data) | slice 2 — technical disclosure |
|---|---|---|
| scope | answer card + adjective (D3/D4) + freshness (D1a), fold structure (D2), controls + preset lift (D6), `PrecipChart` fold (D7), list split into row/group/list + `exclude`, `lastEvidenceDay`/`evidenceFooter` move (D10) | provenance hoist (D5), new fields incl. `interval_*` (D9), summary relocation under the shared block, key-driven renderer + total `isMetricGroup` + `intensity` prune (D8) |
| ships alone | yes — the owner's actual pain (hierarchy) | yes — pure fold contents; slice 1 unaffected if it slips |
| est. source lines changed | ~380 | ~310 |
| est. test lines changed | ~210 | ~160 |
| est. TOTAL (review budget) | **~590** | ~470 |

**Estimates carry their denominator.** The first draft's "~330 / ~280" counted only source and was read as a diff size; the review tier is decided on the whole diff, tests included, so both numbers are stated and the total is what the gate sees. Round-2 revision: slice 1 gained the three-branch freshness gate and `compactAntecedent` plus their boundary tests, slice 2 the hoist's provenance-less guard and the shared stringify guard — ~50 and ~30 lines respectively, moved into the table rather than left as a pleasant memory of the old number.

Slice 1's test line count is not an allowance, it is a list of files the layout change forces open:

| test file | why slice 1 touches it |
|---|---|
| `tests/unit/RainfallDetailPanel.test.tsx` | seven assertion sites across at least five tests (`:268`, `:303`, `:315-317`, `:327-330`, `:336`, `:359`, `:500`) reach `rainfall-metrics` / `rainfall-metric-*` / `rainfall-annual-text`, which now sit inside a CLOSED fold that unmounts its body — each either expands first or moves to the card |
| `tests/unit/RainfallMetricList.test.tsx` → new `RainfallAnswerCard.test.tsx` | the five `AnnualText` tests (`:83-156`) move; **three move verbatim**, and **two do not**: the ones that mount the list to reach the phrase have to be re-expressed against the card's `{ snapshot, freshness }` props instead of the list's, so "verbatim" was wrong for them |
| `tests/unit/RainfallAccumulationChart.test.tsx` | `renderChart()` (`:230`) becomes a controlled wrapper for the lifted preset (D6) |
| `tests/e2e/rainfall-v2-detail.spec.ts` | readiness sentinel switch + expand-before-assert (R4) + the zero-scroll case; run in the declared local environment, not in CI (D13) |

**Consequence, recorded rather than rounded away**: at ~590 lines slice 1 exceeds the 400-line threshold, so it is reviewed at the FULL 4R tier (risk · resilience · readability · reliability), not with a single lens. Splitting slice 1 further was considered and rejected — the card, the fold and the reorder are one hierarchy change, and a half-applied hierarchy is a worse review object than a large coherent one. If the implementation comes in under 400 the tier drops on measurement, not on hope.

### D12 — Bundle guard (≤ +3 kB gzip)

`npm --prefix consorcio-web run build` once per slice, then
`find consorcio-web/dist/assets -name '*.js' -exec sh -c 'gzip -9 -c "$1" | wc -c' _ {} \; | paste -sd+ - | bc`
on the merge-base and on the slice head; delta must be ≤ 3072 bytes.

**D12 amendment (2026-08-11, orchestrator, post-apply — the gate WORKED and this records its verdict rather than silencing it):** the slice-1 measured delta is **+3547 bytes** (904643 → 908190), exceeding the 3072 budget by 475. The attribution table in apply-progress shows the DESIGNED scope (tasks 1.1-1.23) landed at **+1941 — comfortably inside budget**; the overrun is entirely the owner-added mid-apply scope (tasks 1.24-1.30: the fallback query + notice, the ScopeControl extraction, the gloss, the scope-sentence/short-source builders, the exception-chips logic — each individually approved by the owner from live-prod screenshots and external reviews). The apply agent correctly REFUSED to shave code into compliance. Decision: the slice-1 budget is amended to the measured **3547** as the accepted baseline (attributed, intended growth); slice 2 keeps its own ≤3072 budget against THIS new base. The gate's purpose — detecting unintended growth — is preserved: any further slice-1-scope growth from review fixes must justify itself against 3547, not absorb silently.

**Second reading (post-fix-round, commit 0d3961b1):** the R3-001/R4-001 fix (terminal fallback disclosure + announcer branch + extracted `UnavailableAlert`) measured **+3779 total (908422), 232 B past 3547**. Accepted under the clause above: the growth is review-mandated (two refuter-verified CRITICALs), itemized, and measured byte-for-byte against the reproduced pre-fix figure. Slice-1 final accepted baseline: **3779**.
**Rejected**: per-chunk diffing (filenames carry content hashes — unstable across builds); trusting Vite's printed gzip column alone (per-chunk, same instability).
**Rationale**: the SUM over emitted JS is the only figure that is STABLE across builds — it is invariant to how Vite happened to split and hash the chunks, which is what makes it usable as a gate. It is deliberately NOT a model of what a reader downloads: a first visit pays the entry chunk plus whatever it statically imports, not every emitted file, and this app lazy-loads route chunks. The sum is therefore an upper bound used as a regression tripwire, not a page-weight measurement — a 3 kB rise in it means this change shipped 3 kB of new JS somewhere, which is the question the gate is asking. Precedent: lluvia-insights slice 4 chose recharts over `@mantine/charts` to add zero vendor bytes (`RainfallAccumulationChart.tsx` header) — this is the measurement that decision implied. One build per slice, at the gate, not per commit.

### D13 — Where the e2e spec is verified (the canary append is WITHDRAWN)

**Choice**: this change wires `tests/e2e/rainfall-v2-detail.spec.ts` into NO CI job, adds one npm script so the run is reproducible by name, and states plainly which claim is verified by what. The first draft's "append the spec to `test:e2e:canary`" is withdrawn: it breaks a production-safety contract AND would not have executed a single assertion.

**Why the canary append is out — two independent reasons, both verified**:

1. **It breaks a safety allowlist on purpose.** `CANARY_READ_ONLY_SPECS` (`gee-backend/tests/test_ci_workflow_contracts.py:815-859`) pins the `test:e2e:canary` script to EXACTLY three read-only `/mapa` specs, and the test's own docstring says adding a spec "must break this list on purpose". The canary is the one workflow allowed to touch the deployed site; widening it is a production-safety decision, not a testing convenience, and this UX change has no business making it. `gee-backend/**` stays untouched, as the File Changes table already promised.
2. **It would have been inert anyway.** The spec's preamble (`gotoAndOpenFicha`) calls `probeFichaAvailability()`, which probes `process.env.E2E_API_BASE ?? 'http://localhost:8000'`. `e2e-canary.yml` passes NO `E2E_API_BASE` — the same contract test asserts it cannot — so on a runner the probe returns `unknown` and `skipForMissingData` skips EVERY test in the describe, the new zero-scroll case included. The append would have bought a green job that asserts nothing: the exact defect it was meant to close.

**Why the local-preview variant is out too** (it was the better-looking option, so it gets its refutation in writing): the rainfall API is `page.route`-mocked and auth is seeded offline, but the ficha-open journey is NOT mocked. `clickFixtureParcela` requires a real `parcelas_catastro` vector tile to come back `200` from Martin before it clicks, and reports `catastroTilesAvailable: false` otherwise — a `skipForMissingData` gate — and the preamble still needs a reachable backend for the probe. A `vite preview` serves the bundle and nothing else, so the spec skips there for the same reason it skips on the canary. Two further blockers if it were ever attempted: `test_ci_workflows_never_run_production_writing_e2e` (`test_ci_workflow_contracts.py:799-808`) asserts that `.github/workflows/frontend.yml` contains none of the strings `test:e2e`, `tests/e2e` or `PLAYWRIGHT_BASE_URL`, so any such step is a `gee-backend` test change as well; and standing up postgres + backend + Martin + a seeded catastro per PR is minutes of Actions time this repo has already been rationing.

**What verifies what, then** — no claim is left resting on a suite nothing runs:

| claim | verified by | runs |
|---|---|---|
| R4 — folded testids stay reachable, the body unmounts when closed | `RainfallDetailPanel.test.tsx` expands each fold and asserts its contents; the R7 witness asserts `rainfall-annual-text` survives every fold being closed | the frontend `test` job, every PR that touches `consorcio-web/` |
| the e2e spec still matches the new tree (sentinel switch, expand-before-assert) | the spec edits themselves, executed in the declared local environment below | slice-1 merge gate, by hand |
| zero scroll @390×844 (success criterion 1) | the new `requireCondition`-gated e2e case | same declared local run — `E2E_APP_URL` is what turns `requireCondition` from a skip into a failure (`strictGate.ts`) |

**The script, verbatim** (one added line in `consorcio-web/package.json`, beside the existing e2e scripts):

```json
"test:e2e:rainfall": "playwright test -c tests/e2e/playwright.config.ts tests/e2e/rainfall-v2-detail.spec.ts"
```

`playwright.config.ts`, not `playwright.local.config.ts`: the local config's `globalSetup` hard-fails without `E2E_ADMIN_EMAIL`/`E2E_ADMIN_PASSWORD`, and this spec needs neither — it seeds its session offline. The prod config's `baseURL` is never used, because every navigation in the spec goes through `APP_URL`.

**The declared local run.** `docker compose` already ships everything this needs — `backend` for the ficha probe and `martin` for the `parcelas_catastro` tiles — and no credentials are involved, because the spec seeds its own session offline:

```
FICHA_ENABLED=true docker compose up -d postgres backend
docker compose up -d martin   # plus a host route to it — see precondition 5
npm --prefix consorcio-web run dev
E2E_APP_URL=http://localhost:5173 E2E_API_BASE=http://localhost:8000 npm --prefix consorcio-web run test:e2e:rainfall
```

Five preconditions, each stated because each is a way to get a dishonest green (the first three were the original list; 4 and 5 were surfaced as UXJA-201 in the final re-judge — both are documented blockers from the previous change's own apply record, `openspec/changes/archive/2026-08-07-lluvia-v2/apply-progress.md:245`): (1) the catastro dataset must be loaded (the same precondition `ficha-territorial.spec.ts` has always had — without it the tile gate skips); (2) `E2E_API_BASE` is what stops the preamble from soft-skipping; (3) `E2E_APP_URL` is what turns `requireCondition` from a skip into a failure; (4) **`FICHA_ENABLED=true` must reach the backend service** — `app/config.py:124` defaults it to `False` and no compose/env file in the repo sets it, so without it `probeFichaAvailability` returns `'off'` and every test skips; (5) **Martin must be reachable from the browser's host** — the compose service is docker-network-only (no published port, `docker-compose.yml` martin block), while the SPA resolves tiles from `VITE_MARTIN_URL || 'http://localhost:3000'`, so the run needs either a compose override publishing `3000` or `VITE_MARTIN_URL` pointed at a reachable Martin; without it `clickFixtureParcela` never gets its `parcelas_catastro` 200 and the zero-scroll case skips. The port matters — `run dev` serves 5173, while `run preview` serves 4173, so a preview run needs `--port 5173` or a matching `E2E_APP_URL`. Run with no env vars at all, the script skips loudly and touches nothing: the spec navigates to `APP_URL`, which defaults to `localhost:5173`, never to the config's production `baseURL`.

**Rejected**: the canary append (above); a preview-only CI job (above); leaving the design's "it actually runs" claim in place with no mechanism (that sentence was false the day it was written); inventing a test-only deep link that opens the ficha without the map click (`catastroFixture.ts` already weighed and rejected shipping test-shaped production code for exactly this).
**Consequence, stated rather than rounded away**: CI does not gate the zero-scroll criterion, and this change does not pretend it does. Making it gateable means a CI job with a seeded catastro and a live backend — its own change, on its own budget, not a rider on a UX slice.

## Data Flow

    useRainfallScopes ─┐
                       ├─→ RainfallDetailPanel  [scope · year · preset · export · announcer · gate]
    useRainfallAnalysis┘          │ snapshot (immutable)
                                  │ freshness = deriveFreshness(snapshot)   ← the ANALYSIS' date, derived once, here
                                  │                                            (the SERIES' date is the chart's own, D1a)
                                  ├─→ RainfallAnswerCard({snapshot, freshness})  (always mounted — R7 anchor)
                                  ├─→ RainfallAccumulationChart({snapshot, preset, onPresetChange})
                                  │        └─ owns useRainfallSeries; footer + aria-label describe the SERIES
                                  ├─→ CollapsibleSection "Antecedentes"    → RainfallMetricGroup('antecedents')
                                  └─→ CollapsibleSection "Detalle técnico" → RainfallMetricList(exclude=['antecedents'])

Card content, top to bottom: `Percentil 72` (`rainfall-headline`) → adjective (`rainfall-wetness`) → `rainfall-annual-text` → freshness (`rainfall-freshness`, one of D1a's three branches: `Evidencia publicada hasta el 2026-02-09` · `Sin días con evidencia publicada en este análisis` · `Frescura no disponible en este análisis`) → `Ámbito: Zona · estimación regional · comparación hasta {comparison_end}`. That is the full answer set the ADDED requirement asks for above the fold: percentile, selected-year total and normal-to-date (inside `rainfall-annual-text`), and freshness as the last day WITH evidence.

Degradation: no percentile → headline falls back to `Acumulado del año {value}`; a policy-suppressed year still states its real freshness date (its evidence is not in question, only its number — D1a); a genuinely empty disclosure window → the honest no-evidence sentence, never a fallback date; a stripped `annual.selected` with no provenance → the indeterminate sentence, which claims neither; nothing to say → the card still renders (it is the ready sentinel) with the scope line only. The ready announcement appends `· percentil 72, año húmedo` (existing assertion is `/disponible/i` — safe).

## File Changes

| File | Slice | Action |
|---|---|---|
| `consorcio-web/src/components/map2d/rainfall/RainfallAnswerCard.tsx` | 1 | Create — headline, adjective, `AnnualText`, freshness sentence, scope line |
| `consorcio-web/src/components/map2d/rainfall/RainfallDetailPanel.tsx` | 1 | Modify — order, controls block, folds, lifted preset state, `deriveFreshness` |
| `consorcio-web/src/components/map2d/rainfall/RainfallMetricList.tsx` | 1, 2 | Modify — row/group/list split + `exclude`; then hoist, R6, new fields incl. `interval_*`, snapshot-level `source_health`, summary |
| `consorcio-web/src/components/map2d/rainfall/rainfallFormat.ts` | 1, 2 | Modify — wetness + `lastEvidenceDay`/`evidenceFooter` move + `deriveFreshness`; then hoist helpers, label prune |
| `consorcio-web/src/components/map2d/rainfall/RainfallAccumulationChart.tsx` | 1 | Modify — required `preset`/`onPresetChange` (internal state deleted) + import the moved date helpers |
| `consorcio-web/src/components/map2d/FichaTerritorialPanel.tsx` | 1 | Modify — tab body order + `PrecipChart` fold keyed on `v2DetailWillRender` |
| `consorcio-web/src/components/map2d/MapPanelShell.tsx` | 1 | Modify — ONE added attribute: `data-testid="${testId}-sheet-body"` on the sheet body div (`:253`), the box the zero-scroll e2e measures against. No behaviour, no style, no prop |
| `consorcio-web/tests/e2e/rainfall-v2-detail.spec.ts` | 1, 2 | Modify — sentinel switch + expand-before-assert (R4) + zero-scroll case; then the unknown-group assertion (D8) |
| `consorcio-web/package.json` | 1 | Modify — ONE added script, `test:e2e:rainfall` (config + this spec), so the declared local run of D13 has a name instead of a paragraph. `test:e2e:canary` (`:23`) is NOT touched |
| `consorcio-web/src/components/ui/CollapsibleSection.tsx` | — | Reused unchanged (the post-hydration flip is handled with a `key`, D7) |
| `.github/workflows/**` | — | Untouched — no new job, no canary change (D13) |
| `gee-backend/**` (incl. `tests/test_ci_workflow_contracts.py`), `useRainfallAnalysis.ts`, `lib/api/rainfall.ts` | — | Untouched. The canary allowlist and the frontend-workflow e2e guard are production-safety contracts; this change stays on its own side of them |

## Interfaces

```ts
// rainfallFormat.ts — slice 1
export const RAINFALL_WETNESS = {
  VERY_DRY: 'muy_seco', DRY: 'seco', NORMAL: 'normal', WET: 'humedo', VERY_WET: 'muy_humedo',
} as const;
export type RainfallWetness = (typeof RAINFALL_WETNESS)[keyof typeof RAINFALL_WETNESS];
export function wetnessFromPercentile(metric: RainfallMetric | undefined): RainfallWetness | null;
export function wetnessLabel(wetness: RainfallWetness): string;

/** D2a — collapsed-header value: rounded, unitless, `—` when there is none. */
export function compactAntecedent(metric: RainfallMetric | undefined): string;

// moved from RainfallAccumulationChart.tsx (:153, :178) — one implementation, three callers
export function lastEvidenceDay(availableThrough: string): string;
export function evidenceFooter(evidenceDay: string | null, answered: boolean): string;

/** The freshness of the STORED analysis. Derived ONCE, in the panel (D1a). */
export interface RainfallFreshness {
  /**
   * Which branch of the D1a evidence gate was taken. A discriminator, not a
   * sentence match: `no_evidence` is reserved for a genuinely empty disclosure
   * window, `unknown` for a metric served without provenance/coverage.
   */
  readonly kind: 'evidenced' | 'no_evidence' | 'unknown';
  /** `available_through − 1 day`; null on every branch but `evidenced`. */
  readonly evidenceDay: string | null;
  /** The sentence to print — one per branch. */
  readonly sentence: string;
  /** The served `reason`, when the branch is `unknown` and one was served. */
  readonly reason: string | null;
}
export function deriveFreshness(snapshot: RainfallAnalysisSnapshot): RainfallFreshness;

// RainfallAnswerCard.tsx — slice 1
export interface RainfallAnswerCardProps {
  readonly snapshot: RainfallAnalysisSnapshot;
  readonly freshness: RainfallFreshness;
}

// RainfallAccumulationChart.tsx — slice 1: preset props are REQUIRED (D6), no internal state
export interface RainfallAccumulationChartProps {
  readonly snapshot: RainfallAnalysisSnapshot;
  readonly preset: CampaignPreset;
  readonly onPresetChange: (preset: CampaignPreset) => void;
}

// rainfallFormat.ts — slice 2
export const PROVENANCE_FIELD = { SOURCE_ID: 'source_id', SOURCE_CLASS: 'source_class',
  METHOD: 'method', NOMINAL_RESOLUTION: 'nominal_resolution', AGGREGATION: 'aggregation',
  SPATIAL_SCOPE: 'spatial_scope', FRESHNESS: 'freshness',
  AVAILABLE_THROUGH: 'available_through', REVISION: 'revision' } as const;
export type ProvenanceField = (typeof PROVENANCE_FIELD)[keyof typeof PROVENANCE_FIELD];
export interface RainfallProvenanceHoist {
  readonly shared: Readonly<Partial<Record<ProvenanceField, string>>>;
  readonly perMetric: readonly ProvenanceField[];
}
export function hoistProvenance(metrics: readonly RainfallMetric[]): RainfallProvenanceHoist;
```

## Testing Strategy

| Layer | What | How |
|---|---|---|
| Unit | adjective cut-offs | boundary table in `rainfallFormat.test.ts`: 0, 10, 10.4, 10.6, 30, **30.4 → seco**, **30.6 → normal**, 50, 69.4, **69.6 → húmedo** (agrees with "Percentil 70"), 70, **89 → húmedo**, **89.4 → húmedo**, 89.6 → muy húmedo, 90, 100; `null`/suppressed → `null`. Every published boundary is pinned from BOTH sides, rounding included — 30.4/30.6 and 89.4/89.6 are the two pairs the first draft left half-covered |
| Unit | card | new `RainfallAnswerCard.test.tsx`; the 5 `AnnualText` tests move here from `RainfallMetricList.test.tsx` — three verbatim, two re-expressed against the card's `{ snapshot, freshness }` props (baseline-as-served, percentile 0 survives, suppressed → "—", absent → no phrase) |
| Unit | freshness gate (D1a), all three branches | (a) `annual.selected` available → `Evidencia publicada hasta el {available_through − 1 day}`; (b) **`state: 'suppressed'`, `reason: 'coverage_below_threshold'`, `coverage: 0.62`, provenance intact → the SAME real date, no no-evidence sentence** (the policy-suppression counterexample: a suppressed value is not absent evidence); (c) `state: 'unavailable'`, `reason: 'no_data_in_disclosure_window'`, provenance carrying the `comparison_end + 1` fallback (the JDB-103 shape, one layer up) → `Sin días con evidencia publicada en este análisis` and NO date; (d) the stripped four-field `_unavailable` shape and an absent `annual.selected` → `Frescura no disponible en este análisis`, no date and no no-evidence claim; (e) an unparseable `available_through` degrades to the raw value instead of crashing (JDA-104) |
| Unit | freshness is derived once | `RainfallDetailPanel.test.tsx`: the date the card shows comes from the snapshot's `annual.selected.provenance`, and changing ONLY the `/series` response's `available_through` does not move it (the chart's own footer does move — that is the disclosed divergence, not a bug) |
| Unit | R7 witness | `RainfallDetailPanel.test.tsx`: with EVERY fold closed, `rainfall-annual-text` is still in the document |
| Unit | no datum lost | expand every disclosure, assert the rendered `rainfall-metric-*` key set equals the snapshot's group key union (success criterion 4) |
| Unit | enumerated field floor | with every disclosure expanded, each metric shows its `interval_start`/`interval_end`, coverage, completeness, quality, discrepancies, temporal state, revision, `fallback_used` and provenance (as `shared ∪ row`); a snapshot serving `source_health` renders it ONCE, at the fold's foot; a snapshot NOT serving it renders no placeholder |
| Unit | R6 | a snapshot carrying an unknown group renders it under its RAW key, with raw metric labels |
| Unit | `isMetricGroup` is total | a snapshot whose extra root key is a string, a number, `null`, an array or `{}` renders NO group and — the point of the test — does not throw (`'metric' in "texto"` is a `TypeError`) |
| Unit | hoist | all-equal fixture → one `rainfall-provenance-shared`, rows carry no source/resolution/revision; **mixed fixture** (metric A `revision: 'policy-v2'`, metric B `source_id: 'chirps-v3-prelim'`) → those two fields stay on their rows, the other seven hoist |
| Unit | hoist ignores provenance-less metrics (D5) | a fixture where one metric is served in the stripped four-field shape and the rest are identical → the shared block still hoists all eight fields (`available_through` left the hoistable set — see the D5 amendment recorded in apply-progress deviation #1), the stripped metric renders state + reason only, and no provenance line is invented for it |
| Unit | collapsed header formatter (D2a) | `compactAntecedent`: `31.0 → '31'`, `83.7 → '84'`, `null`/suppressed → `'—'`, no unit in the returned string; the assembled accessory states `mm` exactly once and keeps the d7 → d30 → d90 order with the last metric unavailable |
| Unit | object fields never print `[object Object]` (D9a rule 4) | `quality` and `source_health` fixtures with nested objects, arrays, `null` and scalars → only the scalar pairs render, in key order; an input yielding zero pairs renders no line |
| Unit | `PrecipChart` fold default (D7) | four cases on the exact predicate: staff + parcel-with-nomenclatura → CLOSED; **staff + non-parcela ficha → OPEN** (no v2 detail is rendering, so the public chart is that reader's only content); non-staff + parcel → OPEN; and a post-mount flip of `useCanAccess` remounts the section via its `key` so the default is recomputed instead of frozen |
| Unit | mobile hierarchy | jsdom has no layout: assert ORDER (`compareDocumentPosition`: card before chart before folds) and `aria-expanded="false"` on both folds — the structural precondition of zero-scroll. No fake viewport. |
| E2E | zero scroll @390×844 | new `test.use({ viewport: { width: 390, height: 844 } })` case measuring `boundingBox()` of `rainfall-answer-card` against `ficha-territorial-panel-sheet-body` — the scrolling box itself (`MapPanelShell.tsx:253`), which is the only element whose visible height the assertion can honestly compare against. Gated with `requireCondition`, NOT `skipForMissingData`: a missing sheet body means the layout under test is not there, and a criterion that skips itself when the thing it measures is absent measures nothing. `requireCondition` only bites when `E2E_APP_URL` is set (`strictGate.ts` — `STRICT`), so this case is executable exactly in the declared local environment D13 specifies, and is a slice-1 merge gate run there |
| E2E | folded content | one case expands `rainfall-technical-header` and asserts `rainfall-metrics` inside `rainfall-technical-body` (R4) |
| E2E | unknown group (slice 2) | expand the technical fold and assert the fixture's `intensity` group renders under its RAW key with the raw `p24h` label (D8) |
| E2E | where it runs — and where it CANNOT | `tests/e2e/rainfall-v2-detail.spec.ts` runs in NO CI job, and this change does NOT wire it into one. Both candidate wirings were evaluated and both are green-empty; see D13, which states what verifies each claim instead |
| a11y suite | delta: none | `tests/accessibility/a11y.spec.ts` audits public routes and never authenticates, so it never reached this panel; `tests/ui/CollapsibleSection.test.tsx` already pins `aria-expanded`/`aria-controls`/`role="region"` for the primitive |

**Testid migration (R4)** — slice 1:

The e2e spec pins **15** rainfall testids plus `ficha-precipitacion` (16 assertions' worth of contract), not the 13 the exploration listed — `rainfall-accumulation-lag` and `rainfall-regional-estimate` were missing from that count.

| testid | today | after | e2e action |
|---|---|---|---|
| `rainfall-detail`, `rainfall-live`, `rainfall-regional-estimate`, `rainfall-queued`, `rainfall-export-csv/xlsx/error` | panel | unchanged, always mounted | none |
| `rainfall-scope-switch`, `rainfall-year-select` | panel | controls row (still outside the snapshot gate) | none |
| `rainfall-campaign-preset` | chart header | UNCHANGED — stays in the chart header; only its state moves up (D6) | none (same testid, one instance, same place) |
| `rainfall-campaign-note`, `rainfall-accumulation*` (incl. `-dates`, `-lag`) | after list | directly under the card, contents unchanged | none — the chart keeps disclosing both dates for the series it draws (base spec "Chart Discloses Comparison Date and Freshness") |
| `rainfall-annual-text` | metric list | answer card | none (still always mounted) |
| `rainfall-metrics`, `rainfall-metric-*`, `rainfall-summary` | always | inside a CLOSED fold | readiness waits switch to the new `rainfall-answer-card` sentinel; the one content test expands first |
| `ficha-precipitacion` | ficha body | inside `ficha-precip-fold` (open whenever no v2 detail renders) | none — both authorization cases in the spec are non-staff, so the fold is open for them |

New in slice 1: `rainfall-answer-card`, `rainfall-headline`, `rainfall-wetness`, `rainfall-freshness`, `rainfall-controls`, `rainfall-antecedents(-header/-body)`, `rainfall-technical(-header/-body)`, `ficha-precip-fold(-header/-body)`, and `${testId}-sheet-body` on the shell's scrolling box (`MapPanelShell.tsx:253`), which for this panel resolves to `ficha-territorial-panel-sheet-body` — the same naming the shell already uses for `-sheet-handle` and `-sheet-close`. Slice 2 adds `rainfall-provenance-shared`.

## Migration / Rollout

No migration. Frontend-only render-tree change: reverting the slice restores the previous tree exactly. Slice 2 is revertible independently of slice 1. No feature flag — the change is the layout, and a flag would mean shipping and testing both hierarchies.

## Open Questions

All four are CLOSED. Nothing in this design is waiting on an answer.

- [x] **Q1 — D3, what "printed once" means.** Resolved in the SPEC, not by convention: the requirement now says the percentile MUST be the typographic headline and MUST NOT be repeated as a badged metric row on the same always-visible surface, and grounds the restatement inside the chart's textual equivalent in THIS change's own "Progressive Disclosure Without Data Loss" — which now requires that equivalent to stay COMPLETE, ranking included, for readers who cannot see the plot. The earlier draft cited the base "Chart Discloses Comparison Date and Freshness" for this; that requirement governs the series' two dates only and does not mention the percentile, so the citation was withdrawn rather than reworded. The badged row is the copy that moves into the fold; R3 is not regressed because the rule now names which occurrence is the offending one.
- [x] **Q2 — D4, the cut-offs.** Owner-ratified 2026-08-11 (≤10 / 11-30 / 31-69 / 70-89 / ≥90 over the rounded percentile, no label when suppressed). Published as user-visible vocabulary, with the n-variability property disclosed in D4 and pinned from both sides of every boundary in the unit table.
- [x] **Q3 — D2, `Antecedentes` on desktop.** Owner-ratified 2026-08-11: collapsed at every size, values in the collapsed header, whose exact content is now specified in D2a.
- [x] **Q4 — D9, `source_health` with no producer.** Yes, the delta states it — and generalised, because the question was narrower than the problem. The spec's field floor is now an ENUMERATED list bound to what the snapshot actually serves ("whenever the served snapshot carries it"), with `source_health` named as a snapshot-level fact rendered once for the analysis. An unserved field renders nothing at all: no `—`, no empty label, no fabricated placeholder. That is a requirement about honesty, not plumbing — the previous unbounded wording ("a served field MUST NOT remain unrendered") could not be satisfied or falsified without knowing which fields it meant.
