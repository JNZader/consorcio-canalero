/**
 * LeyendaPanelPrecip.test.tsx
 *
 * Covers the hazard CHIRPS precipitation legend ramp (H2): the legend range must
 * follow the active `precipMonth` via the shared `precipRanges` contract —
 * 0–1800 mm for the annual aggregate, 0–200 mm for any single month — while the
 * YlGnBu color ramp is preserved.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { LeyendaPanel } from '../../src/components/map2d/LeyendaPanel';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

describe('<LeyendaPanel /> — Hazard precip legend dynamic range (H2)', () => {
  it('renders the CHIRPS ramp with the annual 0–1800 mm range', () => {
    renderWithMantine(<LeyendaPanel hazardActive hazardPrecipVisible precipMonth="anual" />);

    expect(screen.getByTestId('hazard-precip-legend')).toBeInTheDocument();
    expect(screen.getByText('CHIRPS 1991-2020 normal')).toBeInTheDocument();
    expect(screen.getByTestId('hazard-precip-legend-min')).toHaveTextContent('0 mm');
    expect(screen.getByTestId('hazard-precip-legend-max')).toHaveTextContent('1800 mm');
  });

  it('renders the monthly 0–200 mm range for a single-month selection', () => {
    renderWithMantine(<LeyendaPanel hazardActive hazardPrecipVisible precipMonth="03" />);

    expect(screen.getByTestId('hazard-precip-legend-min')).toHaveTextContent('0 mm');
    expect(screen.getByTestId('hazard-precip-legend-max')).toHaveTextContent('200 mm');
  });

  it('switches the legend range when the month changes (annual → monthly)', () => {
    const { rerender } = renderWithMantine(
      <LeyendaPanel hazardActive hazardPrecipVisible precipMonth="anual" />,
    );
    expect(screen.getByTestId('hazard-precip-legend-max')).toHaveTextContent('1800 mm');

    rerender(
      <MantineProvider env="test">
        <LeyendaPanel hazardActive hazardPrecipVisible precipMonth="07" />
      </MantineProvider>,
    );
    expect(screen.getByTestId('hazard-precip-legend-max')).toHaveTextContent('200 mm');
    expect(screen.getByTestId('hazard-precip-legend')).toHaveAttribute(
      'data-precip-month',
      '07',
    );
  });

  it('preserves the YlGnBu color ramp (gradient uses the expected stop colors)', () => {
    renderWithMantine(<LeyendaPanel hazardActive hazardPrecipVisible precipMonth="anual" />);

    const gradient = screen.getByTestId('hazard-precip-ramp-gradient');
    const bg = (gradient as HTMLElement).style.background;
    expect(bg).toContain('linear-gradient');
    expect(bg).toContain('#ffffcc'); // lightest YlGnBu stop
    expect(bg).toContain('#0c2c84'); // darkest YlGnBu stop
  });

  it('does not render the precip ramp unless both hazardActive and hazardPrecipVisible are set', () => {
    renderWithMantine(<LeyendaPanel hazardActive precipMonth="anual" />);
    expect(screen.queryByTestId('hazard-precip-legend')).not.toBeInTheDocument();
  });

  it('defaults to the annual range when precipMonth is omitted (backwards compat)', () => {
    renderWithMantine(<LeyendaPanel hazardActive hazardPrecipVisible />);
    expect(screen.getByTestId('hazard-precip-legend-max')).toHaveTextContent('1800 mm');
  });
});
