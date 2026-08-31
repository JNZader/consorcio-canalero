/**
 * rainfallFormat.ts (Lluvia v2 — shared by display and export, Task 3.4)
 *
 * ONE formatter for the metric state a user reads on screen and the text an
 * export summary carries, so displayed and exported states keep the same
 * meaning (spec "CSV Export Parity"). Rules: null is UNKNOWN, never "0" (a
 * served zero IS data); suppressed/unavailable always carry their reason
 * verbatim so the disclosure matches the CSV; partial exposes its coverage.
 */

import type {
  RainfallAnalysisSnapshot,
  RainfallMetric,
  RainfallMetricState,
  RainfallScopeChoice,
} from '../../../lib/api/rainfall';

/**
 * Human label per metric key (the server sends machine keys only).
 *
 * `normal` deliberately carries NO period: the baseline is server-driven and
 * gets appended from `snapshot.baseline` by {@link metricLabel}. A period
 * frozen here is the RISK-001 defect — the panel kept asserting 1991-2020
 * after the normals were regenerated over another period, and the badged row
 * then contradicted the annual phrase beside it, which reads the value AS
 * SERVED (LI4-004).
 *
 * The eight `intensity` labels (`p30`/`p60`/`p3h`/`p24h`/`i30`/`i60`/`peak`/
 * `duration`) were PRUNED in slice 2: `build_snapshot` cannot emit that group
 * (`compute.py:476-656`), so they were vocabulary for data nobody serves —
 * dead-code-as-documentation, exploration finding #10. The prune was safe only
 * once `RainfallMetricList`'s renderer became key-driven with a TOTAL group
 * guard (design D8): an intensity group served tomorrow renders under its raw
 * key with raw metric keys, which is visible. Pruning first would have been a
 * silent drop, i.e. an R6 violation. The backend's own export labels are
 * unaffected — the CSV carries `P24h (mm en 24 h)` from the server.
 */
const RAINFALL_METRIC_LABELS: Record<string, string> = {
  selected: 'Acumulado del año',
  normal: 'Normal',
  percentile: 'Percentil histórico',
  d7: 'Antecedente 7 días',
  d30: 'Antecedente 30 días',
  d90: 'Antecedente 90 días',
  // The rolling-window climatological reference (backend design D1). Flat
  // siblings of the totals above, so the wire key IS the vocabulary key —
  // these strings mirror `service.SUMMARY_METRIC_LABELS` one for one, which is
  // the coherence rule: the narrative the backend writes and the badge this
  // file draws must name the same metric with the same words.
  d7_normal: 'Antecedente 7 días normal',
  d30_normal: 'Antecedente 30 días normal',
  d90_normal: 'Antecedente 90 días normal',
  d7_percentile: 'Antecedente 7 días percentil',
  d30_percentile: 'Antecedente 30 días percentil',
  d90_percentile: 'Antecedente 90 días percentil',
};

/**
 * The metric keys whose LABEL names a baseline period.
 *
 * A SET, not the `key === 'normal'` identity test it replaced. That identity
 * was correct for an envelope with one normal in it; the backend now serves
 * four (`annual_normal` plus one per antecedent window), and an identity test
 * puts "Normal 1991-2020" three rows above a period-less "Antecedente 7 días
 * normal" in one fold — LI4-004, with the reader left to guess whether the two
 * numbers are computed over the same thirty years.
 *
 * The three window PERCENTILES are deliberately absent, for the same reason
 * `percentile` is: a rank's period belongs to the sentence that states it
 * ("Percentil 27 de 1991-2020"), not to the metric's name. Mirrors
 * `service.BASELINE_LABELED_METRICS` on the backend.
 */
const BASELINE_LABELLED_METRICS: ReadonlySet<string> = new Set([
  'normal',
  'd7_normal',
  'd30_normal',
  'd90_normal',
]);

/**
 * How a resolved analysis scope is NAMED on screen.
 *
 * One map, two readers (the panel's live announcement and the card's scope
 * line): the spec requires two normals of different spatial scope to be
 * labelled with their own scope, and two copies of the vocabulary is how one
 * of them ends up saying something the other does not.
 */
export const RAINFALL_SCOPE_LABELS: Record<RainfallScopeChoice['kind'], string> = {
  zone: 'Zona',
  basin: 'Cuenca',
};

/** Tokens dropped from the head of an id because they only repeat the kind. */
const SCOPE_ID_KIND_TOKENS: Record<RainfallScopeChoice['kind'], readonly string[]> = {
  zone: ['zona', 'zone'],
  basin: ['cuenca', 'basin'],
};

/**
 * ONE scope option, named so a reader can tell it from the next one.
 *
 * The defect this exists for (OWN-001, owner screenshots): the control labelled
 * every option with its KIND, so a parcel resolving to two zones and three
 * basins offered `Zona | Zona | Cuenca | Cuenca | Cuenca` — five options, three
 * of them indistinguishable, i.e. a control that cannot be operated correctly,
 * only guessed at.
 *
 * `RainfallScopeChoice` is `{kind, id, version}` and the backend serves no
 * display name, so the only qualifier available is the `id`. It is prettified
 * rather than shown raw — tokens split on `_`/`-`/space, a leading token that
 * merely repeats the kind dropped (`cuenca_sur` → `Sur`), the rest capitalized.
 * An OPAQUE id keeps its own prettified text (`b-carcara-01` → `B Carcara 01`):
 * ugly, and still the repo's standing rule — show the untranslated fact rather
 * than disappear, because a blank qualifier puts the reader back in front of
 * two identical options.
 *
 * `qualify` is passed in rather than inferred because it is a property of the
 * SET, not of the choice: a lone basin needs no qualifier, and adding one would
 * be noise. See {@link scopeChoiceLabels}.
 */
export function scopeChoiceLabel(choice: RainfallScopeChoice, qualify: boolean): string {
  const kindLabel = RAINFALL_SCOPE_LABELS[choice.kind];
  if (!qualify) return kindLabel;

  const tokens = choice.id
    .split(/[\s_-]+/)
    .filter((token) => token.length > 0)
    .map((token) => `${token.charAt(0).toUpperCase()}${token.slice(1)}`);
  const kindTokens = SCOPE_ID_KIND_TOKENS[choice.kind];
  const qualifier = tokens
    .filter((token, index) => index > 0 || !kindTokens.includes(token.toLowerCase()))
    .join(' ');

  return qualifier.length > 0 ? `${kindLabel} · ${qualifier}` : kindLabel;
}

/**
 * Label a whole set of scope choices, qualifying exactly the kinds that repeat.
 *
 * Qualifying unconditionally would turn the ordinary one-zone-one-basin control
 * into `Zona · Ne | Cuenca · Zo 12` — two ids nobody asked for. Qualifying
 * nothing is the defect above. So the rule is the set's own: a choice is
 * qualified iff another choice shares its kind.
 */
export function scopeChoiceLabels(choices: readonly RainfallScopeChoice[]): string[] {
  const perKind = new Map<RainfallScopeChoice['kind'], number>();
  for (const choice of choices) {
    perKind.set(choice.kind, (perKind.get(choice.kind) ?? 0) + 1);
  }
  return choices.map((choice) => scopeChoiceLabel(choice, (perKind.get(choice.kind) ?? 0) > 1));
}

/** Plain-language name for a source class. An unknown class shows itself. */
const SOURCE_CLASS_WORDS: Record<string, string> = {
  observed_station: 'estación',
  estimated_radar: 'radar',
  estimated_satellite: 'satelital',
};

/**
 * The SHORT source — one token plus how it was measured: `CHIRPS (satelital)`.
 *
 * The card's evidence footer is a closed set (owner-ratified): the cut date,
 * the scope, and this. Everything else about provenance — the revision, the
 * method, the nominal resolution, the aggregation, the intervals — lives in
 * the technical fold, because the always-visible surface answers "can I trust
 * this number" and the fold answers "how exactly was it built".
 *
 * `null` when the metric was served without provenance (the stripped
 * `_unavailable` shape), and then the footer simply has no source line: an
 * unserved field is never fabricated and never a placeholder.
 */
export function shortSource(metric: RainfallMetric | undefined): string | null {
  const provenance = metric?.provenance;
  if (provenance === undefined) return null;
  const family = provenance.source_id?.split('-')[0];
  if (family === undefined || family.length === 0) return null;
  const word = SOURCE_CLASS_WORDS[provenance.source_class] ?? provenance.source_class;
  return `${family.toUpperCase()} (${word})`;
}

/**
 * The teaching line under the adjective — the percentile in words.
 *
 * "Percentil 72" is a rank, and a rank is exactly the kind of number a reader
 * nods at without decoding. This says the same thing in a sentence anyone can
 * check: of every 100 years, N were drier than this one.
 *
 * Derived from the SAME rounded value the headline prints (R2, and the
 * consistency rule: no always-visible surface may show a different number for
 * one fact), and absent entirely when the percentile is not readable — an
 * interpretation of a withheld number would be the withheld number.
 */
export function percentileGloss(metric: RainfallMetric | undefined): string | null {
  if (metric === undefined || metric.value === null) return null;
  if (metric.state === 'suppressed' || metric.state === 'unavailable') return null;
  return `De cada 100 años, ${Math.round(metric.value)} fueron más secos que este.`;
}

/**
 * The scope named INSIDE a sentence — `la zona Bell Ville`, `la cuenca Sur`.
 *
 * The badge says `Estimación regional` and, on its own, leaves the reader to
 * guess what "regional" means for the parcel they clicked. This is what lets
 * the card say which region: the SELECTED one, by name.
 *
 * Not {@link scopeChoiceLabel}: that one builds a control OPTION and separates
 * its parts with `·`, which reads as a rendering artifact mid-sentence. Same
 * qualifier, prose shape — and no qualifier at all when the id carries none,
 * because `la zona` is still true and still useful.
 */
export function scopeSentence(choice: RainfallScopeChoice): string {
  const label = scopeChoiceLabel(choice, true);
  const article = 'la';
  const [kindWord, qualifier] = label.split(' · ');
  const lowerKind = (kindWord ?? RAINFALL_SCOPE_LABELS[choice.kind]).toLowerCase();
  return qualifier === undefined
    ? `${article} ${lowerKind}`
    : `${article} ${lowerKind} ${qualifier}`;
}

/**
 * Whether the scope control can be a `SegmentedControl` — or has to be a select.
 *
 * A segmented control divides ONE row between its options, so five of them in
 * the panel's 348 px reproduces the badge-truncation defect at the container
 * level: every label becomes a fragment. Above the budget the control becomes a
 * `NativeSelect`, the same one the year uses beside it, whose options are drawn
 * by the platform in its own popup and therefore cannot fragment.
 *
 * THE BUDGET IS AN ESTIMATE, AND SAYING SO IS THE POINT. jsdom has no layout
 * and the real width depends on the loaded font, so this cannot be a
 * measurement; it is a character budget derived from the panel's own geometry —
 * 348 px of card (`map.module.css`: `min(380px, 100% - 72px)`) minus ~32 px of
 * `Paper p="md"` padding leaves ~316 px, each segment spends ~20 px on its own
 * padding, and Inter at the `size="xs"` 12 px runs ~6.2 px per character. It
 * errs toward the select on purpose: a select that was not strictly necessary
 * costs one extra tap, while a segmented control that did not fit costs the
 * reader the ability to read any option at all.
 */
export function shouldUseSegmentedScope(labels: readonly string[]): boolean {
  if (labels.length > 3) return false;
  const glyphBudget = Math.floor((316 - 20 * labels.length) / 6.2);
  const characters = labels.reduce((total, label) => total + label.length, 0);
  return characters <= glyphBudget;
}

const RAINFALL_STATE_LABELS: Record<RainfallMetricState, string> = {
  available: 'Disponible',
  partial: 'Parcial',
  suppressed: 'Suprimida',
  unavailable: 'No disponible',
};

/**
 * The human label for a metric key, with the served baseline where the metric
 * is ABOUT a baseline.
 *
 * `baseline` is optional and the fallback is deliberately period-less
 * ("Normal"): naming the metric without a period is honest, while defaulting
 * to a constant period is the exact claim this signature exists to prevent.
 * An unknown key still degrades to the raw key, the repo's standing rule for
 * an untranslated fact (`export._label`).
 */
export function metricLabel(key: string, baseline?: string | null): string {
  const label = RAINFALL_METRIC_LABELS[key] ?? key;
  return BASELINE_LABELLED_METRICS.has(key) && baseline ? `${label} ${baseline}` : label;
}

/**
 * The unit that is NOT a suffix.
 *
 * Every other unit this contract carries is a magnitude the number is measured
 * in (`mm`, `mm/h`, `h`), so "850.2 mm" is right. `percentil` is a RANK: in
 * Spanish the word comes first and the number qualifies it, so the suffix
 * pattern produced "46.9 percentil" — not a phrase anyone reads, and the same
 * screen said "Percentil 47" three lines up.
 */
const UNIT_PREFIX_LABELS: Record<string, string> = { percentil: 'Percentil' };

/**
 * Value with unit; unknown stays "—", never "0".
 *
 * The precise value survives here on purpose: this is what the technical
 * fold's row renders, and the fold is where a reader goes for the number as
 * served. The ALWAYS-VISIBLE surfaces round it (the card headline, the gloss,
 * the annual phrase) because a Weibull rank over ~31 samples has no meaningful
 * tenth — what is not allowed is the same screen showing 47 and 46.9 while
 * calling both "the percentile", which is what the suffix bug produced.
 */
export function formatMetricValue(metric: RainfallMetric): string {
  if (metric.value === null) return '—';
  const prefix = UNIT_PREFIX_LABELS[metric.unit];
  if (prefix !== undefined) return `${prefix} ${metric.value.toFixed(1)}`;
  return `${metric.value.toFixed(1)} ${metric.unit}`;
}

/**
 * A series value with its unit — the chart's counterpart to
 * {@link formatMetricValue}, which only knows how to read a `RainfallMetric`.
 *
 * Same rule, stated once for both: `null` is UNKNOWN and prints "—", never
 * "0". A daily point with no published evidence carries `null`, and a chart
 * caption that renders it as a zero invents a dry day.
 */
export function formatAccumulated(value: number | null | undefined, unit: string): string {
  return value === null || value === undefined ? '—' : `${value.toFixed(1)} ${unit}`;
}

/**
 * The percentile as a PHRASE, for the annual textual equivalent.
 *
 * Not `formatMetricValue`: the server sends `unit: "percentil"` (deliberately
 * not `"%"`, so nobody reads a rank as a share of anything), and "27.4
 * percentil" is not a sentence a reader parses. `baseline` is passed in rather
 * than hardcoded — the period is server-driven, and a constant here is the
 * RISK-001 defect that let the UI keep asserting 1991-2020 after the normals
 * were regenerated over another period.
 *
 * Rounded to a whole percentile: a Weibull rank over ~31 samples moves in
 * steps of roughly 3, so the tenth is precision the number does not have. A
 * served 0 stays "0" — the driest year on record is data, not a missing value.
 */
export function percentilePhrase(metric: RainfallMetric, baseline: string): string {
  return metric.value === null
    ? `Percentil de ${baseline}: —`
    : `Percentil ${Math.round(metric.value)} de ${baseline}`;
}

/**
 * ISO day of a date or datetime string, without re-parsing it into a Date
 * (a `new Date(...)` round trip is where a UTC day silently becomes the day
 * before in a browser west of Greenwich).
 *
 * Moved here with {@link lastEvidenceDay} (design D10): it is that function's
 * only dependency, and leaving a copy behind in the chart would be a second
 * implementation of the one conversion R3 exists to keep single.
 */
export function isoDay(value: string): string {
  return value.slice(0, 10);
}

/**
 * The last day the provider actually published, read off `available_through`.
 *
 * `available_through` is the EXCLUSIVE end of the disclosure window, not a
 * day the analysis has evidence for: `compute._disclosure_window` builds it as
 * `min(comparison_end + 1 day, max(interval_end))`, and `series._points` stops
 * at `window_end - 1 day`, so NO point is ever emitted on it. The backend pins
 * the pair literally (`test_rainfall_series_consistency.py`:
 * `available_through == 2025-01-21`, last point `2025-01-20`).
 *
 * Every INCLUSIVE sentence below is therefore about the day before it. Reading
 * the raw value as inclusive was wrong three times over: it claimed evidence
 * for a day with none, it hid a one-day provider lag completely (with a lag of
 * exactly one day the exclusive end EQUALS `comparison_end`, so a `<` test on
 * the raw value is false and the missing day reads as a day without rain), and
 * on a finalized past year it printed January 1 of the NEXT year under a chart
 * titled with this one.
 *
 * `Date.UTC` over the parsed parts, never `new Date(value)`: same reason
 * `isoDay` avoids the round trip, and it carries month and year rollover for
 * free (day 0 is the previous month's last day). Slicing the first ten
 * characters is only correct because the wire value is UTC-normalized where it
 * leaves the backend (`series.build_series`, JDB-101): the stored envelope can
 * carry the same instant under the database session's own offset, and the day
 * of `2024-03-02T21:00:00-03:00` is March 3, not March 2.
 *
 * An unparseable value degrades to its own raw day rather than throwing
 * (JDA-104): `toISOString()` on an invalid Date raises, and the exception
 * would take down the whole panel subtree over one footnote. `build_series`
 * refuses an unparseable `available_through` with a 503 long before it can
 * reach a chart, so this is a guard against an unmodelled shape, not a
 * reachable state — and the repo's rule for that is to show the untranslated
 * fact (`export._label`, `metricLabel ?? key`), never to disappear.
 *
 * Lives here rather than in the chart (design D10) because THREE surfaces read
 * it: the chart's footer for the plotted series, the answer card's freshness
 * for the stored analysis, and the technical fold for each metric. A second
 * copy is a second place for the exclusive→inclusive conversion to drift.
 */
export function lastEvidenceDay(availableThrough: string): string {
  const day = isoDay(availableThrough);
  const [year, month, dayOfMonth] = day.split('-').map(Number);
  // NaN defaults on purpose: a missing part must reach the fallback below
  // instead of being silently completed into a real, wrong date.
  const shifted = Date.UTC(
    year ?? Number.NaN,
    (month ?? Number.NaN) - 1,
    (dayOfMonth ?? Number.NaN) - 1
  );
  if (Number.isNaN(shifted)) return day;
  return new Date(shifted).toISOString().slice(0, 10);
}

/**
 * The evidence half of the footer — a CLAIM, so it is only made when the
 * series carries evidence to back it.
 *
 * With zero published intervals `compute._disclosure_window` falls back to
 * `comparison_end + 1 day`, so an analysis that published NOTHING still
 * carries a plausible-looking `available_through`, and stamping it read as
 * "evidence up to X" over a series whose every point is null (JDB-103). The
 * lag notice is gated on the same fact, because "the provider has not yet
 * published the days after X" is not a sentence about a series with no X.
 *
 * ANALYSIS-SCOPED WORDING (UXJA-205): the no-evidence sentence says "en este
 * análisis". It describes the series the chart drew and, through
 * {@link deriveFreshness}, the stored analysis — never one metric row, which
 * needs its own string because "this analysis" is a claim about the whole
 * envelope, not about the metric the reader is looking at.
 */
export function evidenceFooter(evidenceDay: string | null, answered: boolean): string {
  if (evidenceDay !== null) return `Evidencia publicada hasta el ${evidenceDay}`;
  return answered
    ? 'Sin días con evidencia publicada en este análisis'
    : 'Evidencia publicada hasta el —';
}

/**
 * The published interpretive vocabulary (design D4, owner-ratified 2026-08-11).
 *
 * Const object first, so the cut-off table, the labels and every caller share
 * ONE source of truth and a new category cannot be added in one of the three.
 */
export const RAINFALL_WETNESS = {
  VERY_DRY: 'muy_seco',
  DRY: 'seco',
  NORMAL: 'normal',
  WET: 'humedo',
  VERY_WET: 'muy_humedo',
} as const;

export type RainfallWetness = (typeof RAINFALL_WETNESS)[keyof typeof RAINFALL_WETNESS];

const RAINFALL_WETNESS_LABELS: Record<RainfallWetness, string> = {
  [RAINFALL_WETNESS.VERY_DRY]: 'muy seco',
  [RAINFALL_WETNESS.DRY]: 'seco',
  [RAINFALL_WETNESS.NORMAL]: 'normal',
  [RAINFALL_WETNESS.WET]: 'húmedo',
  [RAINFALL_WETNESS.VERY_WET]: 'muy húmedo',
};

/**
 * The interpretive adjective for a year, derived SOLELY from the served
 * percentile (spec "Derived Interpretive Rainfall Label", proposal R2).
 *
 * Published cut-offs over the ALREADY-ROUNDED percentile: ≤10 muy seco ·
 * 11-30 seco · 31-69 normal · 70-89 húmedo · ≥90 muy húmedo. Rounding FIRST is
 * load-bearing, not incidental: `percentilePhrase` prints `Math.round(value)`,
 * so a percentile of 69.6 reads "Percentil 70" — and a label computed off the
 * raw 69.6 would print "año normal" beside it, a card contradicting itself in
 * two adjacent lines.
 *
 * 10/30/70/90 rather than terciles: a Weibull rank over ~31 samples moves in
 * steps of `100 / (n + 1)` — 3.125 points at n = 30, 4.545 at the n = 20
 * eligibility floor — so a 33/67 boundary would flip the WORD on a baseline
 * that gained or lost one eligible year. A 40-point-wide neutral band makes the
 * adjective move less often than the number it describes; the sentence that
 * renders it names the percentile and the baseline, so a reader who sees the
 * word move can see what moved it.
 *
 * `null` (no label at all) whenever the rank is not a served number — an absent
 * percentile is not a normal year, and a policy-suppressed one is not a dry
 * year. The STATE is checked as well as the value: a server that blanks one
 * without the other must not have a withheld number reappear as an adjective.
 */
export function wetnessFromPercentile(metric: RainfallMetric | undefined): RainfallWetness | null {
  if (metric === undefined || metric.value === null) return null;
  if (metric.state === 'suppressed' || metric.state === 'unavailable') return null;
  const rank = Math.round(metric.value);
  if (rank <= 10) return RAINFALL_WETNESS.VERY_DRY;
  if (rank <= 30) return RAINFALL_WETNESS.DRY;
  if (rank <= 69) return RAINFALL_WETNESS.NORMAL;
  if (rank <= 89) return RAINFALL_WETNESS.WET;
  return RAINFALL_WETNESS.VERY_WET;
}

/** The user-visible word for a derived category. */
export function wetnessLabel(wetness: RainfallWetness): string {
  return RAINFALL_WETNESS_LABELS[wetness];
}

/**
 * A Mantine colour for the derived category — ACCOMPANYING the word, never
 * replacing it.
 *
 * The word is always rendered, in full, inside a sentence that also names the
 * percentile and the baseline it was derived from. This map only tints that
 * sentence, so a colour-blind reader, a greyscale printout and a screen reader
 * all still get the whole fact. Colour as the sole carrier of meaning is the
 * thing this repo already refuses in the chart's solid-vs-dashed rule; nothing
 * here is allowed to become the exception.
 */
const RAINFALL_WETNESS_COLORS: Record<RainfallWetness, string> = {
  [RAINFALL_WETNESS.VERY_DRY]: 'red',
  [RAINFALL_WETNESS.DRY]: 'orange',
  [RAINFALL_WETNESS.NORMAL]: 'dimmed',
  [RAINFALL_WETNESS.WET]: 'blue',
  [RAINFALL_WETNESS.VERY_WET]: 'indigo',
};

export function wetnessColor(wetness: RainfallWetness): string {
  return RAINFALL_WETNESS_COLORS[wetness];
}

/**
 * The collapsed-header value of one antecedent (design D2a).
 *
 * NOT `formatAccumulated`: that one is `toFixed(1)` plus the unit, so it yields
 * `31.0 mm` — a decimal nobody reads off a collapsed header and a unit repeated
 * once per value inside a ~26-character string at 348 px. This is its own
 * decision with its own single call site: whole millimetres, no unit (the
 * accessory states it once at the end), and the unknown marker whenever there
 * is no value to state — never `0`, per "Partial, Suppressed, and Unavailable
 * Data States". The rows keep `formatAccumulated` unchanged.
 */
export function compactAntecedent(metric: RainfallMetric | undefined): string {
  if (metric === undefined || metric.value === null) return '—';
  if (metric.state === 'suppressed' || metric.state === 'unavailable') return '—';
  return String(Math.round(metric.value));
}

/**
 * The freshness of the STORED analysis — derived ONCE, in the panel (D1a).
 *
 * `kind` is the discriminator the card, the folds and the tests key on, so
 * nothing downstream has to match a sentence to know which claim was made.
 */
export interface RainfallFreshness {
  /**
   * Which branch of the D1a evidence gate was taken. `no_evidence` is reserved
   * for a genuinely EMPTY disclosure window; `unknown` is for an analysis
   * served without the facts either claim would need.
   */
  readonly kind: 'evidenced' | 'no_evidence' | 'unknown';
  /** `available_through − 1 day`; null on every branch but `evidenced`. */
  readonly evidenceDay: string | null;
  /** The sentence to print — one per branch. */
  readonly sentence: string;
  /** The served `reason`, when the branch is `unknown` and one was served. */
  readonly reason: string | null;
}

/**
 * Decide, from the SERVED analysis alone, what may honestly be said about how
 * fresh its numbers are.
 *
 * THE GATE KEYS ON EVIDENCE, NEVER ON POLICY STATE — and it is load-bearing in
 * both directions, because each direction is a defect this repo has already
 * shipped once:
 *
 *   - Never a stamped fallback. `compute._disclosure_window` falls back to
 *     `comparison_end + 1 day` when the analysis published zero intervals, so
 *     `available_through` alone is never proof that evidence exists (JDB-103,
 *     already fixed once in the chart footer).
 *   - Never "no evidence" for a metric that has some. Keying the no-evidence
 *     sentence on `state ∈ {suppressed, unavailable}` is the mirror defect:
 *     `apply_metric_policy` (`policy.py:166-167`) suppresses a metric whose
 *     coverage is REAL but below the served threshold, and `_normalize_metric`
 *     (`service.py:493,518`) blanks only its `value`, keeping `coverage`,
 *     `provenance` and `interval_*`. A 62 %-coverage year would then read "Sin
 *     días con evidencia publicada" directly above a chart footer declaring
 *     evidence through the same day — one screen asserting both.
 *
 * So the branches read only the facts that survive normalization: evidence
 * (`available_through` served AND (`coverage > 0` OR a served numeric value)),
 * the ONE server fact that means an empty window
 * (`unavailable` + `no_data_in_disclosure_window`, `compute.py:649-650`), or
 * neither — an absent `annual.selected`, or one served in
 * `service._unavailable`'s STRIPPED four-field shape (`service.py:466-472`),
 * which carries no provenance and no coverage at all.
 *
 * The subject is the ANALYSIS. The plotted SERIES has its own freshness,
 * derived once by the chart that owns the `/series` response: two different
 * objects that can legitimately disagree, and when they do the disagreement is
 * disclosed by `rainfall-series-stale`, never averaged into one number (D1a).
 */
export function deriveFreshness(snapshot: RainfallAnalysisSnapshot): RainfallFreshness {
  const selected = snapshot.annual?.selected;
  const availableThrough = selected?.provenance?.available_through;
  const hasEvidence =
    typeof availableThrough === 'string' &&
    availableThrough.length > 0 &&
    ((typeof selected?.coverage === 'number' && selected.coverage > 0) ||
      typeof selected?.value === 'number');

  if (hasEvidence && availableThrough !== undefined) {
    const evidenceDay = lastEvidenceDay(availableThrough);
    return {
      kind: 'evidenced',
      evidenceDay,
      sentence: evidenceFooter(evidenceDay, true),
      reason: null,
    };
  }

  if (selected?.state === 'unavailable' && selected.reason === 'no_data_in_disclosure_window') {
    return {
      kind: 'no_evidence',
      evidenceDay: null,
      sentence: evidenceFooter(null, true),
      reason: null,
    };
  }

  return {
    kind: 'unknown',
    evidenceDay: null,
    sentence: 'Frescura no disponible en este análisis',
    reason: selected?.reason ?? null,
  };
}

/**
 * The fields a provenance block MAY be hoisted over (design D5).
 *
 * EIGHT, not nine. `available_through` is deliberately NOT here (UXJB-201): it
 * is the INPUT of the per-metric evidence gate ({@link metricEvidenceLine},
 * D9a rule 2), which decides per metric whether an evidence claim may be made
 * at all — and a date hoisted into a block that "vale para todas las métricas"
 * cannot be gated per metric. It is pinned to the rows instead. D5's prose was
 * written when the count was nine; the arithmetic is corrected here (eight
 * candidates, six of them hoisting in the mixed case), the decision is not.
 *
 * `revision` is metric-level rather than a `provenance` key, and it is in the
 * set on purpose: a policy bump moves it while every other field stays put, and
 * that is precisely the case an all-or-nothing hoist would fail.
 *
 * `coverage`, `completeness`, `interval_start` and `interval_end` are NEVER
 * candidates: coverage and completeness are the metric's own quality (hoisting
 * them would state a claim about metrics that do not share it), and the
 * intervals are what makes d7 a different metric from d90 — hoisting them
 * would erase the distinction the antecedents group exists for.
 */
export const PROVENANCE_FIELD = {
  SOURCE_ID: 'source_id',
  SOURCE_CLASS: 'source_class',
  METHOD: 'method',
  NOMINAL_RESOLUTION: 'nominal_resolution',
  AGGREGATION: 'aggregation',
  SPATIAL_SCOPE: 'spatial_scope',
  FRESHNESS: 'freshness',
  REVISION: 'revision',
} as const;

export type ProvenanceField = (typeof PROVENANCE_FIELD)[keyof typeof PROVENANCE_FIELD];

export const PROVENANCE_FIELDS: readonly ProvenanceField[] = Object.values(PROVENANCE_FIELD);

/** How each candidate field is READ off a metric — `revision` is not a
 *  `provenance` key, so the set needs one accessor per field rather than one
 *  lookup for all of them. Exported because the ROW renders the same fields the
 *  hoist compares, and two readers of "where does this field live" is how the
 *  block and the row end up disagreeing about what was hoisted. */
export function provenanceFieldValue(
  metric: RainfallMetric,
  field: ProvenanceField
): string | undefined {
  if (field === PROVENANCE_FIELD.REVISION) return metric.revision;
  return metric.provenance?.[field];
}

export interface RainfallProvenanceHoist {
  /** The fields every metric of the comparison set agreed on, ready to render
   *  ONCE for the whole displayed set. */
  readonly shared: Readonly<Partial<Record<ProvenanceField, string>>>;
  /** The fields that diverged, and therefore stay on each row. */
  readonly perMetric: readonly ProvenanceField[];
}

/**
 * Decide, PER FIELD, what may honestly be said once for a whole displayed set.
 *
 * A field is `shared` iff the comparison set is non-empty and every metric in
 * it carries the strictly equal value. Per-field rather than all-or-nothing
 * because the common divergence is a single field — a `revision` bumped by a
 * policy change — and an all-or-nothing rule would answer that by putting six
 * identical provenance blocks back on the rows, which is the reader's original
 * complaint.
 *
 * THE COMPARISON SET EXCLUDES METRICS SERVED WITHOUT PROVENANCE (UXJB-110).
 * `service._unavailable` (`service.py:466-472`) serves a stripped four-field
 * shape — `metric`/`value`/`state`/`reason` — for a contract, policy or quality
 * rejection. Comparing it would make EVERY field diverge against a metric that
 * carries none, so one unrelated rejection would collapse the hoist to zero.
 * Such a metric renders its state and reason and nothing else (D9a rule 3), so
 * excluding it hides nothing: there was nothing to hide.
 *
 * The set may end up empty (everything stripped). Then `shared` is empty, there
 * is no block to render, and the same rule 3 covers it.
 */
export function hoistProvenance(metrics: readonly RainfallMetric[]): RainfallProvenanceHoist {
  const comparable = metrics.filter((metric) => metric.provenance !== undefined);
  const shared: Partial<Record<ProvenanceField, string>> = {};
  const perMetric: ProvenanceField[] = [];

  for (const field of PROVENANCE_FIELDS) {
    const first = comparable.length > 0 ? provenanceFieldValue(comparable[0], field) : undefined;
    const agrees =
      first !== undefined &&
      comparable.every((metric) => provenanceFieldValue(metric, field) === first);
    if (agrees) shared[field] = first;
    else perMetric.push(field);
  }

  return { shared, perMetric };
}

/**
 * An `unknown` wire field rendered as text — with `[object Object]` made
 * unreachable by construction (D9a rule 4).
 *
 * ONE guard, TWO callers: `quality` (per metric) and `source_health` (per
 * analysis). Both arrive typed `unknown` because the backend does not pin their
 * shape, and two renderings of "what does an object look like here" is exactly
 * how the pair drifts into two different answers.
 *
 * The rules, each of them a way the naive version lies:
 *   - a plain object becomes `k=v; k=v` pairs IN KEY ORDER — the same flat
 *     shape the backend already uses for `discrepancies`;
 *   - only SCALAR values are printed. `null`, arrays, nested objects and
 *     functions are SKIPPED, never coerced: `String({})` is `[object Object]`,
 *     a string that looks like a fact and is not one;
 *   - a non-object input prints as ITSELF. Where D9's table and this rule
 *     disagree on a scalar `source_health`, this rule wins (UXJB-207): a served
 *     `"degradado"` is the fact, and wrapping it in an invented key would be
 *     fabrication;
 *   - zero pairs yields the EMPTY STRING, and the caller renders no line at all
 *     (rule 3: an unserved field is never a placeholder).
 */
export function stringifyUnknownFields(value: unknown): string {
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return '';

  return Object.entries(value)
    .filter(
      ([, entry]) =>
        typeof entry === 'string' || typeof entry === 'number' || typeof entry === 'boolean'
    )
    .map(([key, entry]) => `${key}=${String(entry)}`)
    .join('; ');
}

const EXPECTED_INTERVAL_PREFIX = 'expected_interval=';
const DAY_MS = 86_400_000;

interface ParsedExpectedInterval {
  readonly iso: string;
  readonly ms: number;
}

/** `expected_interval=<ISO-8601>` with a parseable timestamp; anything else is opaque. */
function parseExpectedInterval(token: string): ParsedExpectedInterval | null {
  if (!token.startsWith(EXPECTED_INTERVAL_PREFIX)) return null;
  const iso = token.slice(EXPECTED_INTERVAL_PREFIX.length);
  const ms = Date.parse(iso);
  if (Number.isNaN(ms)) return null;
  return { iso, ms };
}

function gcd(a: number, b: number): number {
  let x = Math.abs(a);
  let y = Math.abs(b);
  while (y !== 0) {
    const remainder = x % y;
    x = y;
    y = remainder;
  }
  return x;
}

/** Regular step for a sorted run: UTC-midnight dates are daily; otherwise gcd, then median. */
function rangeStep(timestamps: readonly number[]): number {
  if (timestamps.length < 2) return DAY_MS;
  if (timestamps.every((ms) => ms % DAY_MS === 0)) return DAY_MS;

  const deltas: number[] = [];
  for (let i = 1; i < timestamps.length; i++) {
    const delta = timestamps[i] - timestamps[i - 1];
    if (delta > 0) deltas.push(delta);
  }
  if (deltas.length === 0) return DAY_MS;

  const byGcd = deltas.reduce((acc, delta) => gcd(acc, delta));
  if (byGcd > 0) return byGcd;

  const ordered = [...deltas].sort((left, right) => left - right);
  const median = ordered[Math.floor(ordered.length / 2)];
  return median > 0 ? median : DAY_MS;
}

function formatIntervalRange(items: readonly ParsedExpectedInterval[]): string {
  const first = items[0];
  const last = items[items.length - 1];
  if (items.length === 1) return `${EXPECTED_INTERVAL_PREFIX}${first.iso}`;
  return `${EXPECTED_INTERVAL_PREFIX}${first.iso} → ${last.iso} (${items.length})`;
}

function compressIntervalRun(tokens: readonly string[]): string[] {
  const parsed = tokens
    .map(parseExpectedInterval)
    .filter((item): item is ParsedExpectedInterval => item !== null)
    .sort((left, right) => left.ms - right.ms);
  if (parsed.length === 0) return [...tokens];

  const step = rangeStep(parsed.map((item) => item.ms));
  const fragments: string[] = [];
  let runStart = 0;
  for (let i = 1; i <= parsed.length; i++) {
    const continues = i < parsed.length && parsed[i].ms === parsed[i - 1].ms + step;
    if (continues) continue;
    fragments.push(formatIntervalRange(parsed.slice(runStart, i)));
    runStart = i;
  }
  return fragments;
}

/**
 * Collapse a discrepancy list so N consecutive `expected_interval=<ISO>`
 * tokens become one `expected_interval=<first> → <last> (N)` fragment.
 *
 * Consecutive means adjacent in the list AND a regular time step (UTC-midnight
 * daily, else gcd/median of adjacent deltas). A gap starts a new range.
 * Non-interval tokens keep their original relative order. Empty → `''`.
 */
export function formatDiscrepancies(discrepancies: readonly string[]): string {
  if (discrepancies.length === 0) return '';

  const fragments: string[] = [];
  let intervalRun: string[] = [];

  const flushIntervalRun = (): void => {
    if (intervalRun.length === 0) return;
    fragments.push(...compressIntervalRun(intervalRun));
    intervalRun = [];
  };

  for (const token of discrepancies) {
    if (parseExpectedInterval(token) !== null) {
      intervalRun.push(token);
    } else {
      flushIntervalRun();
      fragments.push(token);
    }
  }
  flushIntervalRun();
  return fragments.join('; ');
}

/**
 * The scope limit of ONE metric, in the reader's language (backend design D7).
 *
 * The six rolling-window reference metrics carry `quality.reference_scope`,
 * and the spec requires the fold to STATE that limit where the reference is
 * displayed. `quality` already reaches the row through
 * {@link stringifyUnknownFields}, but as a raw English `reference_scope=zone`
 * fragment inside a `Calidad:` line — a machine-readable fact, not a statement
 * a reader can act on. So this is one named line beside it, not instead of it.
 *
 * Rendered ONLY for a metric that carries the key. A row that always printed
 * one would state a limit about a metric that has none: the antecedent TOTALS
 * sit in the same group and are not zone-limited, which is the whole
 * conflation D7 rejected a root-level flag to avoid.
 *
 * The scope word comes from {@link RAINFALL_SCOPE_LABELS} rather than from a
 * second literal — one vocabulary, so the panel's scope control and this line
 * cannot come to call the same scope two different things. An unmodelled value
 * prints as ITSELF: an untranslated fact beats a dropped line.
 */
export function referenceScopeLine(metric: RainfallMetric): string | null {
  const quality = metric.quality;
  if (quality === null || typeof quality !== 'object' || Array.isArray(quality)) return null;
  const scope = (quality as Record<string, unknown>).reference_scope;
  if (typeof scope !== 'string' || scope.length === 0) return null;
  const known = RAINFALL_SCOPE_LABELS[scope as keyof typeof RAINFALL_SCOPE_LABELS];
  return `Alcance de la referencia: ${known === undefined ? scope : known.toLowerCase()}`;
}

/**
 * The evidence statement of ONE metric — the D1a gate applied to the metric's
 * own fields (D9 table, D9a rule 2).
 *
 * NOT {@link evidenceFooter}, and the difference is the whole point of this
 * function existing (UXJA-205): that one is ANALYSIS-scoped ("…en este
 * análisis"), describing the whole envelope. A metric row that borrowed it
 * would make a claim about the analysis while the reader is looking at one
 * metric — and the two can legitimately differ, which is why the rows are
 * gated one by one.
 *
 * Same three branches, same reasons they exist:
 *   - evidence (`available_through` served AND `coverage > 0` or a served
 *     numeric value) → the day BEFORE the exclusive window end. A
 *     policy-suppressed metric takes this branch: its value is withheld, its
 *     evidence is not in question;
 *   - `unavailable` + `no_data_in_disclosure_window` (`compute.py:649-650`) →
 *     the honest empty-window sentence, in the metric's own words;
 *   - neither → `null`, and the row renders NO evidence line. Printing
 *     `available_through` unconditionally would restate JDB-103 one layer down:
 *     with zero published intervals the fallback bound is always present and
 *     always plausible-looking.
 */
export function metricEvidenceLine(metric: RainfallMetric): string | null {
  const availableThrough = metric.provenance?.available_through;
  const hasEvidence =
    typeof availableThrough === 'string' &&
    availableThrough.length > 0 &&
    ((typeof metric.coverage === 'number' && metric.coverage > 0) ||
      typeof metric.value === 'number');

  if (hasEvidence && availableThrough !== undefined) {
    return `Evidencia publicada hasta el ${lastEvidenceDay(availableThrough)}`;
  }
  if (metric.state === 'unavailable' && metric.reason === 'no_data_in_disclosure_window') {
    return 'Sin días con evidencia publicada para esta métrica';
  }
  return null;
}

/**
 * The state WORD alone — what a badge may carry.
 *
 * OWN-003: the badge used to render {@link describeMetricState}, i.e. the state
 * AND its reason, so a suppressed metric asked a 348 px panel to fit
 * "Suprimida: coverage_below_threshold" and the reader got `DISPONI…` instead.
 * A truncated badge is worse than no badge: unreadable AND still looking like
 * data. The reason is not lost — it gets its own line on the row.
 */
export function metricStateLabel(metric: RainfallMetric): string {
  return RAINFALL_STATE_LABELS[metric.state];
}

/** State sentence with its reason where the contract carries one. Used where
 *  there is room for a sentence — the card, an `aria-label` — never in a badge. */
export function describeMetricState(metric: RainfallMetric): string {
  const label = RAINFALL_STATE_LABELS[metric.state];
  if ((metric.state === 'suppressed' || metric.state === 'unavailable') && metric.reason) {
    return `${label}: ${metric.reason}`;
  }
  return label;
}
