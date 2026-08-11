/**
 * RainfallAccumulationChart.test.tsx (Lluvia insights — slice 4, D8)
 *
 * The accumulated-rainfall chart the owner asked for: "si selecciono un año
 * podría mostrarse además en el gráfico de arriba como comparando con el
 * histórico". Locks the disclosures that make that comparison honest:
 *   - 4.1 BOTH SERIES AND BOTH DATES: the selected year's accumulation and the
 *     1991-2020 normal curve are two separate lines, a `ReferenceLine` marks
 *     `comparison_end`, and the footer states `comparison_end` AND the last day
 *     evidence was published — under provider lag those are different days, and
 *     a chart that shows only the first reads as a dry spell.
 *   - 4.1b THE EXCLUSIVE BOUNDARY: the wire `available_through` is the
 *     EXCLUSIVE end of the published window (`compute._disclosure_window`), so
 *     the last day that HAS evidence is the day before it. Rendering the raw
 *     value as an inclusive claim overstates the evidence by one day, hides a
 *     one-day provider lag entirely, and on a finalized past year names a day
 *     outside the analyzed year (JDA-001 ≡ JDB-001).
 *   - 4.2 STALENESS: `consistent_with_snapshot: false` renders the curve PLUS
 *     an alert (design D3: "a silent redraw is prohibited"); absent when the
 *     pin is true.
 *   - 4.2b NORMAL-CURVE STATE: `integrity_refused` MUST read differently from
 *     `suppressed` — both arrive with every `normal_accumulated: null`, so a
 *     chart that keys on "is there a curve?" erases the observable half of
 *     LI3A-001. Asserted on TEXT and on a state attribute, never on colour:
 *     a colour-only distinction is not a distinction for the operator this
 *     disclosure exists for.
 *   - 4.3 NO FAKE REMEDY: the staleness alert offers no re-request action.
 *     `data_revision_moved` is not something a re-POST can fix — the only
 *     enqueue path is policy staleness — so a button there promised a remedy
 *     the backend cannot deliver (JDA-003 ≡ JDB-003). The disclosure stays;
 *     the button is gone.
 *   - 4.4 TOOLTIP: `null` is UNKNOWN, never `0.0 mm`. recharts hands the
 *     formatter the raw datum, `null` included, and `Number(null) === 0`
 *     (JDA-002).
 *   - 4.5 CAMPAIGN PRESET: a display window over the SAME series — no
 *     `/analyses` request may fire, which is what keeps spec.md:117-125 intact.
 *
 * HOW THE CHART IS MADE ASSERTABLE: same seam as `PrecipChart.test.tsx` —
 * recharts' `ResponsiveContainer` measures through `ResizeObserver` and
 * happy-dom reports 0x0, so it is swapped for a fixed-size pass-through. The
 * rest of recharts is the real library. `Tooltip` is a pass-through that ALSO
 * records the props it was handed: recharts only renders tooltip content for
 * an active pointer position, which happy-dom (0x0 rects) can never produce,
 * so capturing the `formatter` the component wires in is the only way to
 * assert it WITHOUT re-implementing it in the test — verified to leave the
 * real chart intact (both `.recharts-line` nodes still render).
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { type ComponentProps, type ReactElement, cloneElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

/** The `formatter` the component hands recharts' `Tooltip` (see 4.4). */
const tooltip = vi.hoisted(() => ({
  formatter: null as null | ((value: unknown, ...rest: unknown[]) => unknown),
}));

// Hoisted before the component import: the component pulls `ResponsiveContainer`
// in at module scope.
vi.mock('recharts', async () => {
  const actual = await vi.importActual<typeof import('recharts')>('recharts');
  const RealTooltip = actual.Tooltip;
  return {
    ...actual,
    // The generic on `ReactElement` is what lets `cloneElement` accept the
    // size props: with a bare `ReactElement` the props type is `unknown` and
    // `tsc` rejects them. `PrecipChart.test.tsx` has the same seam and never
    // showed it — that file is outside the typecheck project (LI3A-004).
    ResponsiveContainer: ({
      children,
    }: {
      children: ReactElement<{ width?: number; height?: number }>;
    }) => cloneElement(children, { width: 600, height: 300 }),
    // Records and forwards. The real Tooltip still mounts, so nothing else in
    // this file changes shape; what it renders is another matter — recharts
    // only fills the tooltip for an ACTIVE pointer index, and happy-dom's 0x0
    // bounding rects mean no `mousemove` ever produces one (measured: the
    // wrapper mounts `visibility: hidden` with an empty payload). The prop is
    // therefore the only honest place to assert the formatter.
    Tooltip: (props: ComponentProps<typeof RealTooltip>) => {
      tooltip.formatter = props.formatter as never;
      return <RealTooltip {...props} />;
    },
  };
});

vi.mock('../../src/lib/api/rainfall', async () => {
  const actual = await vi.importActual<typeof import('../../src/lib/api/rainfall')>(
    '../../src/lib/api/rainfall'
  );
  return {
    ...actual,
    fetchRainfallSeries: vi.fn(),
    fetchRainfallAnalysis: vi.fn(),
  };
});

import type {
  RainfallAnalysisSnapshot,
  RainfallMetric,
  RainfallSeriesPoint,
  RainfallSeriesResponse,
} from '../../src/lib/api/rainfall';
import { fetchRainfallAnalysis, fetchRainfallSeries } from '../../src/lib/api/rainfall';
import { RainfallAccumulationChart } from '../../src/components/map2d/rainfall/RainfallAccumulationChart';

const ZONE = { kind: 'zone' as const, id: 'zona-ne', version: '3' };
const YEAR = 2025;
/**
 * The wire `available_through`, EXCLUSIVE — exactly what the backend emits.
 *
 * `compute._disclosure_window` builds it as `min(comparison_end + 1 day,
 * max(interval_end))`, and `series._points` stops at `window_end - 1 day`:
 * NO point is ever emitted on this day, and the pin test
 * `test_rainfall_series_consistency.py:412-414` states the pair literally
 * (`available_through == 2025-01-21`, last point `2025-01-20`).
 *
 * The fixtures below encoded the opposite shape — a point ON
 * `available_through`, with `AVAILABLE_THROUGH == COMPARISON_END` — which is a
 * series the backend cannot produce, and which is what let the display bug in
 * 4.1b pass as correct. Rebuilt to the real contract.
 */
const AVAILABLE_THROUGH_EXCLUSIVE = '2025-10-06';
/** …so THIS is the last day that carries evidence, and the last plotted point. */
const LAST_EVIDENCE_DAY = '2025-10-05';
/** The default fixture is at ZERO lag: the provider reached `comparison_end`. */
const COMPARISON_END = '2025-10-05';

function metric(overrides: Partial<RainfallMetric> = {}): RainfallMetric {
  return {
    metric: 'selected',
    value: 850.24,
    unit: 'mm',
    state: 'available',
    reason: null,
    interval_start: '2025-01-01T00:00:00Z',
    interval_end: '2026-01-01T00:00:00Z',
    coverage: 1,
    completeness: 1,
    quality: { score: 0.9 },
    discrepancies: [],
    temporal_state: 'final',
    revision: 'policy-v1',
    provenance: {
      source_id: 'chirps-v3-final',
      source_class: 'estimated_satellite',
      method: 'sum',
      nominal_resolution: '0.05°',
      aggregation: 'daily',
      spatial_scope: 'zone',
      freshness: '2025-10-06T00:00:00Z',
      available_through: `${AVAILABLE_THROUGH_EXCLUSIVE}T00:00:00Z`,
    },
    fallback_used: false,
    ...overrides,
  };
}

function snapshot(overrides: Partial<RainfallAnalysisSnapshot> = {}): RainfallAnalysisSnapshot {
  return {
    analysis_revision_id: 'rev-9',
    data_revision: 'ab'.repeat(32),
    scope: ZONE,
    regional_estimate: true,
    year: YEAR,
    comparison_end: COMPARISON_END,
    baseline: '1991-2020',
    annual: {
      selected: metric({ metric: 'selected', value: 850.24 }),
      normal: metric({ metric: 'normal', value: 1013.8 }),
    },
    ...overrides,
  };
}

/**
 * A daily series from January 1 through the last day WITH evidence, inclusive
 * — so the September window of the campaign preset has real points on both
 * sides of its boundary, and so the series stops one day short of the
 * exclusive `available_through`, as the backend's does.
 */
function points({
  from = `${YEAR}-01-01`,
  through = LAST_EVIDENCE_DAY,
}: { readonly from?: string; readonly through?: string } = {}): RainfallSeriesPoint[] {
  const built: RainfallSeriesPoint[] = [];
  let accumulated = 0;
  let normal = 0;
  const cursor = new Date(`${from}T00:00:00Z`);
  const last = new Date(`${through}T00:00:00Z`);
  while (cursor <= last) {
    accumulated += 3;
    normal += 3.5;
    built.push({
      date: cursor.toISOString().slice(0, 10),
      mm: 3,
      accumulated,
      normal_accumulated: normal,
      state: 'available',
    });
    cursor.setUTCDate(cursor.getUTCDate() + 1);
  }
  return built;
}

function series(overrides: Partial<RainfallSeriesResponse> = {}): RainfallSeriesResponse {
  return {
    analysis_revision_id: 'rev-9',
    data_revision: 'ab'.repeat(32),
    scope: ZONE,
    year: YEAR,
    unit: 'mm',
    comparison_end: COMPARISON_END,
    available_through: `${AVAILABLE_THROUGH_EXCLUSIVE}T00:00:00+00:00`,
    consistent_with_snapshot: true,
    consistency_reason: null,
    normal_curve_state: 'available',
    points: points(),
    ...overrides,
  };
}

/** A curve-less series: BOTH no-curve states arrive in exactly this shape. */
function curvelessPoints(): RainfallSeriesPoint[] {
  return points().map((point) => ({ ...point, normal_accumulated: null }));
}

function renderChart(snap: RainfallAnalysisSnapshot = snapshot()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const ui: ReactElement = (
    <QueryClientProvider client={client}>
      <MantineProvider env="test">
        <RainfallAccumulationChart snapshot={snap} />
      </MantineProvider>
    </QueryClientProvider>
  );
  return render(ui);
}

describe('RainfallAccumulationChart — both series and both dates (4.1)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchRainfallSeries).mockResolvedValue(series());
  });

  it('draws the selected year and the normal curve as two separate lines', async () => {
    const { container } = renderChart();

    await screen.findByTestId('rainfall-accumulation-chart');
    // TWO lines: the year and the 1991-2020 normal. One line would be the
    // owner's request half-implemented — there is nothing to compare against.
    await waitFor(() => expect(container.querySelectorAll('.recharts-line')).toHaveLength(2));
  });

  it('marks comparison_end with a reference line and states BOTH dates in the footer', async () => {
    const { container } = renderChart();

    await screen.findByTestId('rainfall-accumulation-chart');
    await waitFor(() =>
      expect(container.querySelectorAll('.recharts-reference-line-line').length).toBeGreaterThan(0)
    );

    const footer = screen.getByTestId('rainfall-accumulation-dates');
    expect(footer.textContent).toContain(COMPARISON_END);
    expect(footer.textContent).toContain(LAST_EVIDENCE_DAY);
  });

  it('says so when the provider has not published up to comparison_end', async () => {
    // Provider lag is the documented steady state (design D5/D6). The series
    // stops where the evidence does, and a reader who is not told that will
    // read the missing tail as a dry spell.
    vi.mocked(fetchRainfallSeries).mockResolvedValue(series({ comparison_end: '2025-12-31' }));
    renderChart(snapshot({ comparison_end: '2025-12-31' }));

    const footer = await screen.findByTestId('rainfall-accumulation-dates');
    expect(footer.textContent).toContain('2025-12-31');
    expect(footer.textContent).toContain(LAST_EVIDENCE_DAY);
    expect(screen.getByTestId('rainfall-accumulation-lag')).toBeInTheDocument();
  });

  it('carries a textual equivalent of the plotted window and both end values', async () => {
    // The chart is `role="img"` over a label that names the window and both
    // final values, because a screen reader gets nothing from an SVG of ticks.
    renderChart();

    const chart = await screen.findByTestId('rainfall-accumulation-chart');
    expect(chart).toHaveAttribute('role', 'img');
    const label = chart.getAttribute('aria-label') ?? '';
    expect(label).toContain('2025-01-01');
    expect(label).toContain(LAST_EVIDENCE_DAY);
    expect(label).toMatch(/mm/);
  });
});

describe('RainfallAccumulationChart — the EXCLUSIVE available_through (4.1b)', () => {
  // JDA-001 ≡ JDB-001. `available_through` is the exclusive end of the
  // published window; the last day that HAS evidence is the day before it.
  // Truncating the wire value to a day and printing it as an inclusive claim
  // is wrong in three separate ways, one per test below.
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchRainfallSeries).mockResolvedValue(series());
  });

  it('names the last day WITH evidence, not the exclusive end', async () => {
    renderChart();

    const footer = await screen.findByTestId('rainfall-accumulation-dates');
    expect(footer.textContent).toContain(`Evidencia publicada hasta el ${LAST_EVIDENCE_DAY}`);
    // The exclusive end is an implementation detail of the window, and there
    // is no evidence for that day at all — it must never reach the reader.
    expect(footer.textContent).not.toContain(AVAILABLE_THROUGH_EXCLUSIVE);
    // Zero lag: the provider reached `comparison_end`, so there is nothing to
    // disclose and the notice must stay away.
    expect(screen.queryByTestId('rainfall-accumulation-lag')).toBeNull();
  });

  it('discloses a lag of exactly ONE day', async () => {
    // The boundary the bug hid completely: with a one-day lag the exclusive
    // `available_through` EQUALS `comparison_end`, so a `<` comparison on the
    // raw value is false and the reader is told nothing — the missing day
    // reads as a day without rain.
    vi.mocked(fetchRainfallSeries).mockResolvedValue(series({ comparison_end: '2025-10-06' }));
    renderChart(snapshot({ comparison_end: '2025-10-06' }));

    // Asserted FIRST on purpose: the missing notice is the defect, and an
    // assertion order that trips on the footer string instead would leave the
    // suppression itself unproven.
    const lag = await screen.findByTestId('rainfall-accumulation-lag');
    expect(lag.textContent).toContain(`posteriores al ${LAST_EVIDENCE_DAY}`);
    const footer = screen.getByTestId('rainfall-accumulation-dates');
    expect(footer.textContent).toContain('Comparación hasta el 2025-10-06');
    expect(footer.textContent).toContain(`Evidencia publicada hasta el ${LAST_EVIDENCE_DAY}`);
  });

  it('stays inside the analyzed year on a finalized past year', async () => {
    // A finalized 2024 reaches December 31, so its exclusive window end is
    // 2025-01-01 — a day in ANOTHER year, and one the analysis says nothing
    // about. Printing it makes the footer contradict the title above it.
    const finalized = { from: '2024-01-01', through: '2024-12-31' };
    vi.mocked(fetchRainfallSeries).mockResolvedValue(
      series({
        year: 2024,
        comparison_end: '2024-12-31',
        available_through: '2025-01-01T00:00:00+00:00',
        points: points(finalized),
      })
    );
    renderChart(snapshot({ year: 2024, comparison_end: '2024-12-31' }));

    const footer = await screen.findByTestId('rainfall-accumulation-dates');
    expect(footer.textContent).toContain('Evidencia publicada hasta el 2024-12-31');
    expect(footer.textContent).not.toContain('2025-01-01');
    expect(screen.queryByTestId('rainfall-accumulation-lag')).toBeNull();
  });

  it('agrees with the textual equivalent about the last plotted day', async () => {
    // `describePlottedWindow` reports the real last POINT; the footer reports
    // the disclosure window. They describe the same edge of the same series,
    // so a reader comparing the caption with the footnote must not find two
    // different days.
    renderChart();

    const chart = await screen.findByTestId('rainfall-accumulation-chart');
    const footer = screen.getByTestId('rainfall-accumulation-dates');
    expect(chart.getAttribute('aria-label')).toContain(`y el ${LAST_EVIDENCE_DAY}`);
    expect(footer.textContent).toContain(`Evidencia publicada hasta el ${LAST_EVIDENCE_DAY}`);
  });
});

describe('RainfallAccumulationChart — the footer degrades honestly (JDA-104, JDB-103)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchRainfallSeries).mockResolvedValue(series());
  });

  it('falls back to the raw value instead of crashing on an unparseable date', async () => {
    // JDA-104. `lastEvidenceDay` did `new Date(Date.UTC(NaN, …)).toISOString()`
    // on anything it could not parse, and `toISOString` on an invalid Date
    // THROWS — taking the whole panel subtree with it. `build_series` refuses
    // an unparseable `available_through` with a 503 upstream, so this is
    // unreachable today; the repo's own convention for an unmodelled value is
    // to degrade to the untranslated fact (`export._label`, `metricLabel ?? key`),
    // never to remove the panel the operator was reading.
    vi.mocked(fetchRainfallSeries).mockResolvedValue(series({ available_through: 'no-es-fecha' }));
    renderChart();

    const footer = await screen.findByTestId('rainfall-accumulation-dates');
    expect(footer.textContent).toContain('no-es-fec');
    // The rest of the panel is still there: a bad date costs its own sentence,
    // not the chart.
    expect(screen.getByTestId('rainfall-accumulation-chart')).toBeInTheDocument();
  });

  it('does not claim published evidence when no day carries any', async () => {
    // JDB-103. With zero published intervals `compute._disclosure_window`
    // falls back to `comparison_end + 1 day`, so an analysis that published
    // NOTHING still carries a plausible-looking `available_through` — and the
    // footer stamped it as evidence for a series whose every point is null.
    // The lag notice is gated the same way: "the provider has not published
    // the days after X" is not a sentence about a series with no X.
    const empty = points().map((point) => ({
      ...point,
      mm: null,
      accumulated: null,
      normal_accumulated: null,
      state: 'unavailable' as const,
    }));
    vi.mocked(fetchRainfallSeries).mockResolvedValue(
      series({ comparison_end: '2025-12-31', points: empty, normal_curve_state: 'suppressed' })
    );
    renderChart(snapshot({ comparison_end: '2025-12-31' }));

    const footer = await screen.findByTestId('rainfall-accumulation-dates');
    expect(footer.textContent).not.toContain(`Evidencia publicada hasta el ${LAST_EVIDENCE_DAY}`);
    expect(footer.textContent).toContain('Sin días con evidencia publicada');
    // The analysis window is still a fact and stays disclosed.
    expect(footer.textContent).toContain('2025-12-31');
    expect(screen.queryByTestId('rainfall-accumulation-lag')).toBeNull();
  });

  it('still names the evidence day when a single day carries evidence', async () => {
    // The counterexample to the gate above: it must key on "is there any
    // evidence", not on "are there trailing nulls" — a series whose tail is
    // unpublished is the documented steady state and still has a last
    // evidence day.
    const tail = points().map((point, index) =>
      index === 0 ? point : { ...point, mm: null, accumulated: point.accumulated, state: 'unavailable' as const }
    );
    vi.mocked(fetchRainfallSeries).mockResolvedValue(series({ points: tail }));
    renderChart();

    const footer = await screen.findByTestId('rainfall-accumulation-dates');
    expect(footer.textContent).toContain(`Evidencia publicada hasta el ${LAST_EVIDENCE_DAY}`);
  });
});

describe('RainfallAccumulationChart — staleness disclosure (4.2)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchRainfallSeries).mockResolvedValue(series());
  });

  it('renders the curve PLUS an alert when the pin is false', async () => {
    vi.mocked(fetchRainfallSeries).mockResolvedValue(
      series({ consistent_with_snapshot: false, consistency_reason: 'data_revision_moved' })
    );
    const { container } = renderChart();

    const alert = await screen.findByTestId('rainfall-series-stale');
    // The data is the FRESHER evidence, not garbage: it is still drawn.
    expect(container.querySelectorAll('.recharts-line')).toHaveLength(2);
    expect(alert.textContent).toMatch(/corrigieron/i);
    expect(alert.textContent).toContain('data_revision_moved');
  });

  it('shows no staleness alert when the pin is true', async () => {
    renderChart();

    await screen.findByTestId('rainfall-accumulation-chart');
    expect(screen.queryByTestId('rainfall-series-stale')).toBeNull();
  });

  it('catches a stale tab: the series echo disagreeing with the snapshot in hand', async () => {
    // The server pin is authoritative and says CONSISTENT here — this is the
    // cheap client cross-check design D3 promised, and the only thing that
    // catches a snapshot left open in a tab while the server moved on.
    vi.mocked(fetchRainfallSeries).mockResolvedValue(series({ data_revision: 'cd'.repeat(32) }));
    renderChart();

    const alert = await screen.findByTestId('rainfall-series-stale');
    expect(alert.textContent).toMatch(/pestaña|anterior/i);
  });
});

describe('RainfallAccumulationChart — normal-curve state (4.2b)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders integrity_refused DISTINCTLY from suppressed, in copy and in state', async () => {
    // THE regression this task exists for. Both states arrive with every
    // `normal_accumulated: null` (backend D3 "Normal-curve integrity
    // amendment"), so the wire cannot tell them apart by shape — only by this
    // field. An honest absence and a curve that was computed and thrown away
    // for contradicting the card beside it are different facts.
    vi.mocked(fetchRainfallSeries).mockResolvedValue(
      series({ normal_curve_state: 'suppressed', points: curvelessPoints() })
    );
    const suppressed = renderChart();
    const suppressedNotice = await screen.findByTestId('rainfall-normal-curve-state');
    const suppressedState = suppressedNotice.getAttribute('data-normal-curve-state');
    const suppressedText = suppressedNotice.textContent ?? '';
    suppressed.unmount();

    vi.mocked(fetchRainfallSeries).mockResolvedValue(
      series({ normal_curve_state: 'integrity_refused', points: curvelessPoints() })
    );
    renderChart();
    const refusedNotice = await screen.findByTestId('rainfall-normal-curve-state');
    const refusedState = refusedNotice.getAttribute('data-normal-curve-state');
    const refusedText = refusedNotice.textContent ?? '';

    expect(suppressedState).toBe('suppressed');
    expect(refusedState).toBe('integrity_refused');
    // The COPY differs — and not by a colour class, which an operator reading
    // a printed screenshot or a colour-blind reader would never see.
    expect(refusedText).not.toEqual(suppressedText);
    expect(suppressedText).toMatch(/no hay/i);
    expect(refusedText).toMatch(/descartad/i);
    expect(refusedText).toMatch(/inconsistencia/i);
    // …and refusal is never described as an absence of data.
    expect(refusedText).not.toMatch(/no hay (línea )?normal para este análisis/i);
  });

  it('draws no normal line at all when the curve is refused', async () => {
    vi.mocked(fetchRainfallSeries).mockResolvedValue(
      series({ normal_curve_state: 'integrity_refused', points: curvelessPoints() })
    );
    const { container } = renderChart();

    await screen.findByTestId('rainfall-accumulation-chart');
    // ONE line, not two-with-one-empty: an empty line renders as a legend entry
    // and an axis that promise a comparison the response refused to make.
    await waitFor(() => expect(container.querySelectorAll('.recharts-line')).toHaveLength(1));
  });

  it('says nothing about the curve when it is available', async () => {
    vi.mocked(fetchRainfallSeries).mockResolvedValue(series());
    renderChart();

    await screen.findByTestId('rainfall-accumulation-chart');
    expect(screen.queryByTestId('rainfall-normal-curve-state')).toBeNull();
  });

  it('degrades on an unmodelled curve state instead of crashing the panel', async () => {
    // LI4-005. `NORMAL_CURVE_NOTICE` is keyed by the states this client knows
    // TODAY; the wire type is the backend's to extend. A fourth state reaches
    // an `undefined` entry, and reading `.title` off it is a TypeError that
    // takes down the whole panel subtree over one footnote — a strictly worse
    // outcome than the untranslated fact. The repo's standing rule for exactly
    // this case is to SHOW the raw value (`metricLabel ?? key`,
    // `export._label`), never to disappear.
    vi.mocked(fetchRainfallSeries).mockResolvedValue(
      series({
        // Cast on purpose: the point is a state the union does NOT model.
        normal_curve_state: 'provider_withdrew' as RainfallSeriesResponse['normal_curve_state'],
        points: curvelessPoints(),
      })
    );
    renderChart();

    // The chart still mounts — that is the whole claim.
    await screen.findByTestId('rainfall-accumulation-chart');
    const notice = await screen.findByTestId('rainfall-normal-curve-state');
    expect(notice.getAttribute('data-normal-curve-state')).toBe('provider_withdrew');
    // The raw state is carried through, so an operator can name what the server
    // actually said rather than reading a silent panel.
    expect(notice.textContent).toContain('provider_withdrew');
  });
});

describe('RainfallAccumulationChart — no fake remedy (4.3)', () => {
  // JDA-003 ≡ JDB-003. The alert used to carry a "Volver a pedir el análisis"
  // button that could not remedy what the alert describes: the only path that
  // enqueues a rebuild is a SUPERSEDED policy revision (`router.py`
  // `read_analysis` → `_requeue_stale_revision`), never a moved
  // `data_revision`, and the revision the tab holds is immutable. Re-POSTing
  // returns the same revision every time. A button that reliably does nothing
  // is worse than no button: it converts an accurate disclosure into an
  // instruction the reader will follow, repeatedly, and blame themselves for.
  //
  // The tests it replaces asserted a labelled `202` and a newer-revision `200`
  // from this flow — wire states the backend cannot produce here — so they
  // were pinning a fiction rather than protecting a behavior.
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('offers no re-request action for data_revision_moved, and keeps saying why', async () => {
    vi.mocked(fetchRainfallSeries).mockResolvedValue(
      series({ consistent_with_snapshot: false, consistency_reason: 'data_revision_moved' })
    );
    renderChart();

    // The disclosure is the whole point and it stays, in full.
    const alert = await screen.findByTestId('rainfall-series-stale');
    expect(alert.textContent).toMatch(/corrigieron/i);
    expect(alert.textContent).toContain('data_revision_moved');
    expect(screen.queryByTestId('rainfall-series-rerequest')).toBeNull();
  });

  it('offers no re-request action on the echo cross-check either', async () => {
    vi.mocked(fetchRainfallSeries).mockResolvedValue(series({ data_revision: 'cd'.repeat(32) }));
    renderChart();

    await screen.findByTestId('rainfall-series-stale');
    expect(screen.queryByTestId('rainfall-series-rerequest')).toBeNull();
  });

  it('never re-POSTs /analyses from the chart at all', async () => {
    vi.mocked(fetchRainfallSeries).mockResolvedValue(
      series({ consistent_with_snapshot: false, consistency_reason: 'data_revision_moved' })
    );
    renderChart();

    await screen.findByTestId('rainfall-series-stale');
    // The panel owns the analysis query; the chart reads a series and nothing
    // else. Without this, a re-request could grow back on another control.
    expect(fetchRainfallAnalysis).not.toHaveBeenCalled();
  });
});

describe('RainfallAccumulationChart — the tooltip never invents a zero (4.4)', () => {
  // JDA-002. recharts hands the formatter the raw datum value, `null`
  // included, and `Number(null)` is `0` — so coercing first turns "no
  // evidence" into a measured 0.0 mm. Two real shapes carry `null` here:
  // February 29, which the backend omits from the normal curve by
  // construction, and any day before the first published one.
  beforeEach(() => {
    vi.clearAllMocks();
    tooltip.formatter = null;
    vi.mocked(fetchRainfallSeries).mockResolvedValue(series());
  });

  it.each([
    ['a Feb-29-style point with no curve key', null],
    ['a day before the first published evidence', undefined],
  ])('renders the unknown marker for %s', async (_case, value) => {
    renderChart();
    await screen.findByTestId('rainfall-accumulation-chart');

    expect(tooltip.formatter).not.toBeNull();
    expect(tooltip.formatter?.(value)).toBe('—');
  });

  it('still formats a served value, zero included', async () => {
    renderChart();
    await screen.findByTestId('rainfall-accumulation-chart');

    // A served 0 IS data — the rule `rainfallFormat` states for every surface.
    expect(tooltip.formatter?.(0)).toBe('0.0 mm');
    expect(tooltip.formatter?.(12.34)).toBe('12.3 mm');
  });
});

describe('RainfallAccumulationChart — campaign display preset (4.5)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchRainfallSeries).mockResolvedValue(series());
  });

  it('windows the SAME series and fires no /analyses request', async () => {
    renderChart();
    const chart = await screen.findByTestId('rainfall-accumulation-chart');
    expect(chart.getAttribute('aria-label')).toContain('2025-01-01');

    fireEvent.click(screen.getByText('Campaña'));

    await waitFor(() =>
      expect(screen.getByTestId('rainfall-accumulation-chart').getAttribute('aria-label')).toContain(
        '2025-09-01'
      )
    );
    // spec.md:117-125 — a display preset MUST NOT be requested as a period.
    expect(fetchRainfallAnalysis).not.toHaveBeenCalled();
    // …and it does not re-read the series either: same analysis, same data.
    expect(fetchRainfallSeries).toHaveBeenCalledTimes(1);
  });

  it('labels the campaign view as derived from the calendar-year analysis', async () => {
    renderChart();
    await screen.findByTestId('rainfall-accumulation-chart');

    fireEvent.click(screen.getByText('Campaña'));

    const note = await screen.findByTestId('rainfall-campaign-note');
    expect(note.textContent).toMatch(/1 de septiembre/i);
    // The accumulations are still counted from January 1 — saying otherwise
    // would turn a display preset into a different measurement.
    expect(note.textContent).toMatch(/1 de enero/i);
    expect(note.textContent).toContain(String(YEAR));
  });
});
