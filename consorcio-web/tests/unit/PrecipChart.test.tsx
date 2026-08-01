/**
 * PrecipChart.test.tsx  (B2.3)
 *
 * Covers the monthly precipitation block:
 *   - renders BOTH the 12-bar chart and the mes/mm table in calendar order;
 *   - renders the annual total;
 *   - renders the `sin_cobertura` state (no data) WITHOUT crashing and with no
 *     fabricated `0 mm` rows;
 *   - the low-confidence badge appears only when the dataset flags it (it never
 *     should for precip — K=0 — but the component honours the flag).
 *
 * @see spec `ficha-frontend` § "Full ficha rendered"
 * @see spec `precip-normals-pipeline` § "Zone outside precipitation coverage"
 */

import { MantineProvider } from '@mantine/core';
import { render, screen, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { PrecipChart } from '../../src/components/map2d/PrecipChart';
import type { FichaPrecipitacion } from '../../src/lib/api/ficha';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

function precip(overrides: Partial<FichaPrecipitacion> = {}): FichaPrecipitacion {
  return {
    cobertura: 'total',
    low_confidence: false,
    pixel_count: 12,
    cobertura_ratio: 1,
    unidad: 'mm',
    // 12 months, calendar order, distinct values so ordering is observable.
    serie: Array.from({ length: 12 }, (_, i) => ({ mes: i + 1, mm: (i + 1) * 10 })),
    anual_mm: 780,
    ...overrides,
  };
}

const MESES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'];

describe('PrecipChart', () => {
  it('renders the chart, the 12-month table in calendar order, and the annual total', () => {
    renderWithMantine(<PrecipChart dataset={precip()} />);

    // The chart container is present (the visual complement).
    expect(screen.getByTestId('precip-chart')).toBeInTheDocument();

    // The table is the contract: 12 data rows, months in calendar order.
    const table = screen.getByTestId('precip-table');
    const bodyRows = within(table).getAllByRole('row');
    // header + 12 data + annual footer row = 14 rows.
    const monthCells = MESES.map((m) => within(table).getByText(m));
    expect(monthCells).toHaveLength(12);
    // Order: the rendered month labels appear top-to-bottom Jan..Dec.
    const renderedOrder = bodyRows
      .map((row) => row.textContent ?? '')
      .filter((txt) => MESES.some((m) => txt.startsWith(m)))
      .map((txt) => MESES.find((m) => txt.startsWith(m)));
    expect(renderedOrder).toEqual(MESES);

    // A specific server mm value is rendered verbatim (mes 3 → 30 mm).
    expect(within(table).getByText('30.0 mm')).toBeInTheDocument();

    // Annual total.
    expect(screen.getByTestId('precip-anual')).toHaveTextContent('780.0 mm');
  });

  it('renders the sin_cobertura state without crashing and with no chart or 0 mm rows', () => {
    renderWithMantine(
      <PrecipChart dataset={precip({ cobertura: 'sin_cobertura', serie: [], anual_mm: null })} />
    );

    expect(screen.getByTestId('ficha-precipitacion-sin-cobertura')).toBeInTheDocument();
    // No chart, no table, no fabricated zeros.
    expect(screen.queryByTestId('precip-chart')).toBeNull();
    expect(screen.queryByTestId('precip-table')).toBeNull();
    expect(screen.queryByText('0.0 mm')).toBeNull();
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
