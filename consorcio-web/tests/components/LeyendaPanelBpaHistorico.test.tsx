/**
 * LeyendaPanelBpaHistorico.test.tsx
 *
 * The "Años en BPA" color-scale block (4 chips: 1 / 3 / 5 / 7 años) was
 * originally rendered at the bottom of `<LayerControlsPanel />` (the panel
 * that holds the layer toggles). It was moved to `<LeyendaPanel />` so all
 * map legends live in a single place, consistent with roads / consorcios /
 * custom legend entries.
 *
 * These tests lock in the new location:
 *   - The section renders when `pilarVerdeBpaHistoricoVisible` is true.
 *   - It is hidden otherwise.
 *   - Colors match the MapLibre paint expression exactly (the same constants
 *     consumed by `buildBpaHistoricoFillPaint()`), so the legend never drifts
 *     from the map.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { LeyendaPanel } from '../../src/components/map2d/LeyendaPanel';
import { PILAR_VERDE_COLORS } from '../../src/components/map2d/pilarVerdeLayers';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

describe('<LeyendaPanel /> — Años en BPA color scale', () => {
  it('does NOT render the "Años en BPA" section by default', () => {
    renderWithMantine(<LeyendaPanel />);
    expect(screen.queryByText('Años en BPA:')).not.toBeInTheDocument();
    expect(screen.queryByTestId('bpa-historico-legend')).not.toBeInTheDocument();
  });

  it('does NOT render the section when the flag is explicitly false', () => {
    renderWithMantine(<LeyendaPanel pilarVerdeBpaHistoricoVisible={false} />);
    expect(screen.queryByText('Años en BPA:')).not.toBeInTheDocument();
    expect(screen.queryByTestId('bpa-historico-legend')).not.toBeInTheDocument();
  });

  it('renders the section and the 4 chips when the flag is true', () => {
    renderWithMantine(<LeyendaPanel pilarVerdeBpaHistoricoVisible />);

    expect(screen.getByText('Años en BPA:')).toBeInTheDocument();

    const scale = screen.getByTestId('bpa-historico-legend');
    expect(scale).toBeInTheDocument();

    // 4 chips, labelled 1 / 3 / 5 / 7 años via aria-label.
    expect(screen.getByLabelText('1 años')).toBeInTheDocument();
    expect(screen.getByLabelText('3 años')).toBeInTheDocument();
    expect(screen.getByLabelText('5 años')).toBeInTheDocument();
    expect(screen.getByLabelText('7 años')).toBeInTheDocument();
  });

  it('chip colors match the MapLibre paint expression stops', () => {
    renderWithMantine(<LeyendaPanel pilarVerdeBpaHistoricoVisible />);

    // Colors are carried on `data-color` so the test does not depend on
    // browser-specific style parsing.
    expect(screen.getByLabelText('1 años')).toHaveAttribute(
      'data-color',
      PILAR_VERDE_COLORS.bpaHistoricoStop1,
    );
    expect(screen.getByLabelText('3 años')).toHaveAttribute(
      'data-color',
      PILAR_VERDE_COLORS.bpaHistoricoStop3,
    );
    expect(screen.getByLabelText('5 años')).toHaveAttribute(
      'data-color',
      PILAR_VERDE_COLORS.bpaHistoricoStop5,
    );
    expect(screen.getByLabelText('7 años')).toHaveAttribute(
      'data-color',
      PILAR_VERDE_COLORS.bpaHistoricoStop7,
    );
  });

  it('renders alongside custom legend items (does not collide)', () => {
    renderWithMantine(
      <LeyendaPanel
        pilarVerdeBpaHistoricoVisible
        customItems={[{ color: '#FF0000', label: 'Zona Consorcio', type: 'border' }]}
      />,
    );

    expect(screen.getByText('Zona Consorcio')).toBeInTheDocument();
    expect(screen.getByText('Años en BPA:')).toBeInTheDocument();
    expect(screen.getByTestId('bpa-historico-legend')).toBeInTheDocument();
  });
});
