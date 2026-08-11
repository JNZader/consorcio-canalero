/**
 * PrecipChart.test.tsx  (B2.3, rewritten for the compact INTA-style redesign)
 *
 * Covers the monthly precipitation block, asserting the RENDERED DOM — the bars,
 * their on-bar value labels and the month axis are all real elements here, not
 * source-text patterns:
 *   - the 12 month values are printed as visible text, one per bar, in calendar
 *     order (this replaces the old mes/mm table assertions: the table is gone,
 *     the twelve NUMBERS it carried are not);
 *   - those labels are whole millimetres (126.7 → "127"), while the annual
 *     headline keeps the decimal;
 *   - the annual total renders as a headline stat ABOVE the chart;
 *   - the provenance line renders under it, printing the SERVED `fuente` /
 *     `periodo` (RISK-001) and falling back to the legacy label only for a
 *     payload that carries neither;
 *   - `sin_cobertura` renders the no-data state with NO chart, NO bars and no
 *     fabricated zeros anywhere in the rendered output;
 *   - `parcial` renders a caveat ABOVE the numbers, and `total` renders none —
 *     partial coverage used to be served and rendered as nothing at all;
 *   - the low-confidence badge appears only when the dataset flags it (it never
 *     should for precip — K=0 — but the component honours the flag).
 *
 * HOW THE CHART IS MADE ASSERTABLE. recharts' `ResponsiveContainer` measures its
 * parent through `ResizeObserver` + `getBoundingClientRect`, and happy-dom
 * reports 0×0 — so the chart renders NOTHING and every bar/label assertion would
 * silently pass against an empty SVG. The `vi.mock` below swaps only that one
 * export for a pass-through that hands the chart a fixed 600×300 box; the rest
 * of recharts is the real library, so the SVG under test is the production one
 * laid out at a known size. `isAnimationActive={false}` on the `Bar` (in the
 * component) is what makes that layout deterministic on first paint.
 *
 * @see spec `ficha-frontend` § "Card rendering — tables plus monthly chart"
 * @see spec `precip-normals-pipeline` § "Zone outside precipitation coverage"
 */

import { MantineProvider } from '@mantine/core';
import { render, screen, within } from '@testing-library/react';
import { type ReactElement, cloneElement } from 'react';
import { describe, expect, it, vi } from 'vitest';

// Declared before the component import on purpose — `vi.mock` is hoisted, and
// the component pulls `ResponsiveContainer` in at module scope.
vi.mock('recharts', async () => {
  const actual = await vi.importActual<typeof import('recharts')>('recharts');
  return {
    ...actual,
    /** Fixed-size pass-through: see "HOW THE CHART IS MADE ASSERTABLE" above. */
    ResponsiveContainer: ({ children }: { children: ReactElement }) =>
      cloneElement(children, { width: 600, height: 300 }),
  };
});

import { PrecipChart } from '../../src/components/map2d/PrecipChart';
import type { FichaPrecipitacion } from '../../src/lib/api/ficha';

function renderWithMantine(ui: ReactElement) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

/**
 * Realistic Chaco monthly normals, WITH DECIMALS — the rounding the on-bar
 * labels apply is only observable against a fractional input, and every value
 * rounds to a distinct string so calendar order is observable too.
 */
const MM = [138.4, 126.7, 118.2, 94.5, 48.1, 27.3, 21.6, 19.4, 44.8, 108.3, 121.9, 144.6];
/** What the twelve labels MUST read, in calendar order. */
const MM_REDONDEADO = [
  '138',
  '127',
  '118',
  '95',
  '48',
  '27',
  '22',
  '19',
  '45',
  '108',
  '122',
  '145',
];

function precip(overrides: Partial<FichaPrecipitacion> = {}): FichaPrecipitacion {
  return {
    cobertura: 'total',
    low_confidence: false,
    pixel_count: 12,
    cobertura_ratio: 1,
    unidad: 'mm',
    // What the current backend serves, so the DEFAULT case exercises the
    // server-driven path and only the compat tests reach the legacy fallback.
    fuente: 'CHIRPS',
    periodo: '1991-2020',
    serie: MM.map((mm, i) => ({ mes: i + 1, mm })),
    anual_mm: 1013.8,
    ...overrides,
  };
}

const MESES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'];

/**
 * The chart's own subtree.
 *
 * Text queries MUST be scoped to it rather than run against `screen`: recharts
 * leaves a hidden `#recharts_measurement_span` on `document.body` holding the
 * LAST string it measured ("145" here), so a bare `getByText('145')` matches
 * twice and throws. Scoping also keeps `<style>`-injected numbers out of the
 * no-data assertions.
 */
function chartEl(container: HTMLElement): HTMLElement {
  const chart = container.querySelector('[data-testid="precip-chart"]');
  expect(chart, 'chart container').not.toBeNull();
  return chart as HTMLElement;
}

/** Every `<text>` the chart SVG rendered, in document order. */
function chartTexts(container: HTMLElement): string[] {
  return [...chartEl(container).querySelectorAll('text')].map((t) => t.textContent ?? '');
}

describe('PrecipChart', () => {
  it('prints all 12 month values ON the bars, as visible text, in calendar order', () => {
    const { container } = renderWithMantine(<PrecipChart dataset={precip()} />);

    // One bar per month…
    expect(container.querySelectorAll('.recharts-bar-rectangle')).toHaveLength(12);

    // …and the twelve values, RENDERED, in calendar order. This is the whole
    // point of dropping the table: not one number it carried was lost.
    const etiquetas = chartTexts(container).filter((t) => /^\d+$/.test(t));
    expect(etiquetas).toEqual(MM_REDONDEADO);

    // Each is individually findable as visible text, not just present in the
    // SVG soup.
    const chart = within(chartEl(container));
    for (const valor of MM_REDONDEADO) {
      expect(chart.getByText(valor)).toBeInTheDocument();
    }
  });

  it('always labels the month axis, never thinning it to fit', () => {
    const { container } = renderWithMantine(<PrecipChart dataset={precip()} />);

    // `interval={0}`: at 12 bars recharts would otherwise drop every second tick
    // on a narrow panel, and an unlabeled bar is an unreadable one.
    expect(chartTexts(container).filter((t) => MESES.includes(t))).toEqual(MESES);
  });

  it('rounds the on-bar labels to whole millimetres (126.7 → "127")', () => {
    // A tenth of a millimetre in a 30-year mean is noise, and three digits is
    // all that fits in a ~25px slot at 12 bars.
    const { container } = renderWithMantine(<PrecipChart dataset={precip()} />);
    const chart = within(chartEl(container));

    expect(chart.getByText('127')).toBeInTheDocument();
    expect(chart.queryByText('126.7')).toBeNull();
    expect(chart.queryByText('126.7 mm')).toBeNull();
    // …and it ROUNDS, it does not truncate: 94.5 → 95, 21.6 → 22.
    expect(chart.getByText('95')).toBeInTheDocument();
    expect(chart.getByText('22')).toBeInTheDocument();
  });

  it('renders the annual total as a headline stat ABOVE the chart', () => {
    renderWithMantine(<PrecipChart dataset={precip()} />);

    const anual = screen.getByTestId('precip-anual');
    // The one figure a reader leaves with, so it is a standalone stat now, not a
    // table footer row — and at full precision, unlike the cramped bar labels.
    expect(anual).toHaveTextContent('Anual (normal): 1013.8 mm');

    const chart = screen.getByTestId('precip-chart');
    expect(anual.compareDocumentPosition(chart) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('states the provenance of the numbers under the chart, from the payload', () => {
    renderWithMantine(<PrecipChart dataset={precip()} />);

    const fuente = screen.getByTestId('precip-fuente');
    // SERVED, not hardcoded: the backend reads product and period off the
    // `metadata_extra` of the rasters that answered.
    expect(fuente).toHaveTextContent('Normales CHIRPS 1991-2020');

    const chart = screen.getByTestId('precip-chart');
    expect(chart.compareDocumentPosition(fuente) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('RISK-001: the provenance line follows the payload, whatever it says', () => {
    // THE regression this contract exists for. The label used to be a constant
    // in this file, so regenerating the normals over another period left the UI
    // asserting 1991-2020 with nothing able to catch it. A payload from a
    // different run must read as that run — no frontend edit involved.
    renderWithMantine(
      <PrecipChart dataset={precip({ fuente: 'CHIRPS v3', periodo: '2001-2030' })} />
    );

    expect(screen.getByTestId('precip-fuente')).toHaveTextContent('Normales CHIRPS v3 2001-2030');
    expect(screen.getByTestId('precip-fuente')).not.toHaveTextContent('1991-2020');
  });

  it('falls back to the legacy label when the payload carries no provenance', () => {
    // Compat, not decoration: a browser can be talking to a backend older than
    // the served fields. Better the period that backend is pinned to than an
    // empty footer or a half-rendered "Normales  ".
    renderWithMantine(
      <PrecipChart dataset={precip({ fuente: undefined, periodo: undefined })} />
    );

    expect(screen.getByTestId('precip-fuente')).toHaveTextContent('Normales CHIRPS 1991-2020');
  });

  it('treats a half-populated or blank provenance as absent, never rendering a gap', () => {
    // "Normales CHIRPS " / "Normales  1991-2020" read as a rendering bug rather
    // than as the missing datum they are.
    const { rerender } = renderWithMantine(
      <PrecipChart dataset={precip({ fuente: 'CHIRPS', periodo: undefined })} />
    );
    expect(screen.getByTestId('precip-fuente')).toHaveTextContent('Normales CHIRPS 1991-2020');

    rerender(
      <MantineProvider env="test">
        <PrecipChart dataset={precip({ fuente: '   ', periodo: '2001-2030' })} />
      </MantineProvider>
    );
    expect(screen.getByTestId('precip-fuente')).toHaveTextContent('Normales CHIRPS 1991-2020');
  });

  it('no longer renders the 13-row mes/mm table (it doubled the block height)', () => {
    const { container } = renderWithMantine(<PrecipChart dataset={precip()} />);

    expect(screen.queryByTestId('precip-table')).toBeNull();
    expect(screen.queryByRole('table')).toBeNull();
    // The table printed "138.4 mm"-style cells; nothing does now except the
    // annual headline, which is a single figure, not twelve rows.
    expect(within(container).queryAllByText(/^\d+\.\d+ mm$/)).toHaveLength(0);
  });

  it('renders sin_cobertura with no chart, no bars and no fabricated zeros', () => {
    const { container } = renderWithMantine(
      <PrecipChart dataset={precip({ cobertura: 'sin_cobertura', serie: [], anual_mm: null })} />
    );

    expect(screen.getByTestId('ficha-precipitacion-sin-cobertura')).toBeInTheDocument();
    expect(screen.queryByTestId('precip-chart')).toBeNull();
    expect(screen.queryByTestId('precip-anual')).toBeNull();
    expect(screen.queryByTestId('precip-fuente')).toBeNull();
    // No bars at all — not zero-height ones, which would still draw twelve "0"
    // labels and read as "it rained nothing here".
    expect(container.querySelectorAll('.recharts-bar-rectangle')).toHaveLength(0);
    expect(container.querySelectorAll('svg')).toHaveLength(0);
    // Nothing numeric anywhere in the BLOCK's own output. Scoped to the block,
    // not to `container`: the render root also carries the `<style>` element
    // Mantine injects, which is full of breakpoint numbers.
    expect(screen.getByTestId('ficha-precipitacion').textContent).not.toMatch(/\d/);
  });

  it('a covered dataset containing a real 0 mm month still draws a bar AND a "0"', () => {
    // REGRESSION GUARD, found by this suite. The inverse of the test above:
    // `sin_cobertura` must invent no zeros, but a SERVED zero is DATA.
    //
    // recharts skips zero-height rectangles, and `LabelList` labels rectangles —
    // so before `minPointSize` a `0 mm` month rendered NO bar and NO label:
    // eleven columns and a silent gap where July should be, which a reader
    // cannot tell apart from missing data. The old mes/mm table printed
    // "0.0 mm"; removing the table is what exposed the hole.
    const serie = MM.map((mm, i) => ({ mes: i + 1, mm: i === 6 ? 0 : mm }));
    const { container } = renderWithMantine(<PrecipChart dataset={precip({ serie })} />);

    // Twelve bars, not eleven: the dry month keeps its column.
    expect(container.querySelectorAll('.recharts-bar-rectangle')).toHaveLength(12);
    // And twelve labels, with the zero in July's slot and the rest untouched.
    const etiquetas = chartTexts(container).filter((t) => /^\d+$/.test(t));
    expect(etiquetas).toEqual(MM_REDONDEADO.map((v, i) => (i === 6 ? '0' : v)));
  });

  it('warns that a `parcial` coverage average speaks for only part of the zone', () => {
    // The state was already on the wire and rendered as nothing: the reader got
    // a chart indistinguishable from a full-coverage one. Same defect class as
    // the fake zeros the backend fix closed — a number worn as more
    // authoritative than it is.
    renderWithMantine(<PrecipChart dataset={precip({ cobertura: 'parcial' })} />);

    const aviso = screen.getByTestId('ficha-precipitacion-cobertura-parcial');
    expect(aviso).toHaveTextContent(/cobertura parcial/i);
    // The numbers are still served and still drawn — this qualifies them, it
    // does not suppress them.
    expect(screen.getByTestId('precip-chart')).toBeInTheDocument();
    expect(screen.getByTestId('precip-anual')).toBeInTheDocument();
    // …and the caveat is read BEFORE them, not after.
    const anual = screen.getByTestId('precip-anual');
    expect(aviso.compareDocumentPosition(anual) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('stays silent about coverage when it is total', () => {
    // A caveat on every ficha is a caveat nobody reads.
    renderWithMantine(<PrecipChart dataset={precip()} />);

    expect(screen.queryByTestId('ficha-precipitacion-cobertura-parcial')).toBeNull();
  });

  it('renders the no-data state, not the partial caveat, for sin_cobertura', () => {
    // The two states are mutually exclusive: there is no average to qualify when
    // there is no average.
    renderWithMantine(
      <PrecipChart dataset={precip({ cobertura: 'sin_cobertura', serie: [], anual_mm: null })} />
    );

    expect(screen.getByTestId('ficha-precipitacion-sin-cobertura')).toBeInTheDocument();
    expect(screen.queryByTestId('ficha-precipitacion-cobertura-parcial')).toBeNull();
  });

  it('shows the low-confidence badge only when the dataset flags it', () => {
    const { rerender } = renderWithMantine(<PrecipChart dataset={precip()} />);
    expect(screen.queryByTestId('ficha-low-confidence')).toBeNull();

    rerender(
      <MantineProvider env="test">
        <PrecipChart dataset={precip({ low_confidence: true, pixel_count: 2 })} />
      </MantineProvider>
    );
    expect(screen.getByTestId('ficha-low-confidence')).toBeInTheDocument();
  });
});
