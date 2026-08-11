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
 */
const RAINFALL_METRIC_LABELS: Record<string, string> = {
  selected: 'Acumulado del año',
  normal: 'Normal',
  percentile: 'Percentil histórico',
  d7: 'Antecedente 7 días',
  d30: 'Antecedente 30 días',
  d90: 'Antecedente 90 días',
  p30: 'P30 (mm en 30 min)',
  p60: 'P60 (mm en 1 h)',
  p3h: 'P3h (mm en 3 h)',
  p24h: 'P24h (mm en 24 h)',
  i30: 'I30 (mm/h)',
  i60: 'I60 (mm/h)',
  peak: 'Pico del evento',
  duration: 'Duración del evento',
};

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
  return key === 'normal' && baseline ? `${label} ${baseline}` : label;
}

/** Value with unit; unknown stays "—", never "0". */
export function formatMetricValue(metric: RainfallMetric): string {
  if (metric.value === null) return '—';
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
