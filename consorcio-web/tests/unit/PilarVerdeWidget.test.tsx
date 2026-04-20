/**
 * PilarVerdeWidget.test.tsx
 *
 * Component tests for the AdminDashboard Pilar Verde widget. The widget is
 * PROP-DRIVEN (not hook-driven) so the tests never have to mock fetch or
 * TanStack Query — they feed the pinned fixture straight in.
 *
 * Test matrix (5 KPI rows + chrome):
 *   1. Ley Forestal cumplen line renders parcel + hectares (es-AR formatter)
 *   2. Ley Forestal no-cumplen line renders parcel + hectares
 *   3. BPA activos line renders explotaciones + superficie
 *   4. Top práctica adoptada → humanized Spanish label + %
 *   5. Top práctica NO adoptada → humanized Spanish label + %
 *   6. Historical one-liner: histórico count/pct · abandonaron · nunca
 *   7. Footer attribution "Datos: IDECor 2025"
 *   8. CTA <Anchor> has href `/mapa?pilarVerde=1`
 *   9. Loader branch when `isLoading` and no data
 *  10. Alert branch when `isError` or aggregates missing
 */

import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { PilarVerdeWidget } from '../../src/components/admin/pilarVerdeWidget/PilarVerdeWidget';
import pilarVerdeAggregatesFixture from '../fixtures/pilarVerdeAggregates';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

const AGG = pilarVerdeAggregatesFixture;

describe('<PilarVerdeWidget />', () => {
  it('renders the section title', () => {
    renderWithMantine(<PilarVerdeWidget aggregates={AGG} />);
    expect(
      screen.getByRole('heading', { name: /Pilar Verde.*Suelo y Agroforestal/i }),
    ).toBeInTheDocument();
  });

  it('renders the Ley Forestal cumplen row with parcels and hectares', () => {
    renderWithMantine(<PilarVerdeWidget aggregates={AGG} />);
    const row = screen.getByTestId('kpi-ley-cumplen');
    expect(row.textContent).toContain('252');
    expect(row.textContent).toContain('27.967,6');
  });

  it('renders the Ley Forestal no-cumplen row with parcels and hectares', () => {
    renderWithMantine(<PilarVerdeWidget aggregates={AGG} />);
    const row = screen.getByTestId('kpi-ley-no-cumplen');
    expect(row.textContent).toContain('511');
    expect(row.textContent).toContain('36.252,1');
  });

  it('renders the BPA activos row with explotaciones and superficie', () => {
    renderWithMantine(<PilarVerdeWidget aggregates={AGG} />);
    const row = screen.getByTestId('kpi-bpa-activos');
    expect(row.textContent).toContain('70');
    expect(row.textContent).toContain('6.097,3');
  });

  it('renders the top adopted practice with humanized Spanish label', () => {
    renderWithMantine(<PilarVerdeWidget aggregates={AGG} />);
    const row = screen.getByTestId('kpi-top-adoptada');
    expect(row.textContent).toContain('Rotación de gramíneas');
    expect(row.textContent).toContain('92,9%');
  });

  it('renders the top NOT adopted practice with humanized Spanish label', () => {
    renderWithMantine(<PilarVerdeWidget aggregates={AGG} />);
    const row = screen.getByTestId('kpi-top-no-adoptada');
    expect(row.textContent).toContain('Sistema de terrazas');
    expect(row.textContent).toContain('0,0%');
  });

  it('renders the historical one-liner with histórico + abandonaron + nunca', () => {
    renderWithMantine(<PilarVerdeWidget aggregates={AGG} />);
    const row = screen.getByTestId('kpi-historico');
    expect(row.textContent).toContain('228');
    expect(row.textContent).toContain('17,2%');
    expect(row.textContent).toContain('158');
    expect(row.textContent).toContain('1.094');
  });

  it('renders the IDECor 2025 footer attribution', () => {
    renderWithMantine(<PilarVerdeWidget aggregates={AGG} />);
    expect(screen.getByText(/Datos: IDECor 2025/i)).toBeInTheDocument();
  });

  it('renders a CTA anchor pointing to /mapa?pilarVerde=1', () => {
    renderWithMantine(<PilarVerdeWidget aggregates={AGG} />);
    const cta = screen.getByRole('link', { name: /Ver mapa Pilar Verde/i });
    expect(cta).toHaveAttribute('href', '/mapa?pilarVerde=1');
  });

  it('shows a loader when isLoading and no aggregates are provided', () => {
    renderWithMantine(<PilarVerdeWidget isLoading aggregates={undefined} />);
    expect(screen.getByTestId('pilar-verde-widget-loader')).toBeInTheDocument();
    expect(screen.queryByTestId('kpi-ley-cumplen')).not.toBeInTheDocument();
  });

  it('shows a "Datos no disponibles" alert when isError and no aggregates', () => {
    renderWithMantine(<PilarVerdeWidget isError aggregates={undefined} />);
    expect(screen.getByText(/Datos no disponibles/i)).toBeInTheDocument();
    expect(screen.queryByTestId('kpi-ley-cumplen')).not.toBeInTheDocument();
  });

  it('shows the alert branch when aggregates is undefined and not loading', () => {
    renderWithMantine(<PilarVerdeWidget aggregates={undefined} />);
    expect(screen.getByText(/Datos no disponibles/i)).toBeInTheDocument();
  });
});
