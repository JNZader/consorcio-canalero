/**
 * LayerControlsPanelCollapse.test.tsx
 *
 * Accordion structure of `<LayerControlsPanel />` (change `rediseno-ux-mapa`,
 * Phase 2). The flat "Capas" `CollapsibleSection` was replaced by a Mantine
 * `Accordion` (multiple), one item per layer family. Every family is OPEN by
 * default (the panel passes all family values in `defaultValue`); the user can
 * collapse any family by clicking its control.
 */

import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { LayerControlsPanel } from '../../src/components/map2d/LayerControlsPanel';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

const baseProps = {
  baseLayer: 'osm' as const,
  onBaseLayerChange: () => {},
  layerItems: [
    { id: 'catastro', label: 'Catastro', category: 'territorio' as const },
    { id: 'pilar_verde_bpa_historico', label: 'BPA 2025', category: 'pilar_verde' as const },
  ],
  vectorVisibility: {},
  onLayerVisibilityChange: () => {},
  showIGNOverlay: false,
  onShowIGNOverlayChange: () => {},
  demEnabled: false,
  showDemOverlay: false,
  onShowDemOverlayChange: () => {},
  activeDemLayerId: null,
  onActiveDemLayerIdChange: () => {},
  demOptions: [],
};

describe('<LayerControlsPanel /> — family accordion', () => {
  it('renders the panel landmark with families collapsed by default', () => {
    renderWithMantine(<LayerControlsPanel {...baseProps} />);

    expect(
      screen.getByRole('region', { name: /controles de capas del mapa/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /territorio/i, expanded: false })).toBeInTheDocument();
    expect(screen.getByTestId('map-preset-chips')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /territorio/i, expanded: false }));
    fireEvent.click(screen.getByRole('button', { name: /pilar verde/i, expanded: false }));
    expect(screen.getByLabelText('Catastro')).toBeInTheDocument();
    expect(screen.getByLabelText('BPA 2025')).toBeInTheDocument();
  });

  it('expands a family when its control is clicked (aria-expanded flips)', () => {
    renderWithMantine(<LayerControlsPanel {...baseProps} />);

    const control = screen.getByRole('button', { name: /territorio/i });
    expect(control).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(control);
    expect(control).toHaveAttribute('aria-expanded', 'true');
  });

  it('collapses a family after a second click', () => {
    renderWithMantine(<LayerControlsPanel {...baseProps} />);

    const control = screen.getByRole('button', { name: /territorio/i });
    fireEvent.click(control);
    fireEvent.click(control);

    expect(control).toHaveAttribute('aria-expanded', 'false');
  });

  it('exposes an accessible label for the DEM layer selector', () => {
    renderWithMantine(
      <LayerControlsPanel
        {...baseProps}
        demEnabled
        showDemOverlay
        activeDemLayerId="slope"
        demOptions={[{ value: 'slope', label: 'Pendiente' }]}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /análisis raster/i }));
    expect(screen.getByLabelText(/tipo de capa raster/i)).toBeInTheDocument();
  });

  it('selects the first DEM layer before enabling the overlay when none is active', () => {
    const onShowDemOverlayChange = vi.fn();
    const onActiveDemLayerIdChange = vi.fn();

    renderWithMantine(
      <LayerControlsPanel
        {...baseProps}
        demEnabled
        onShowDemOverlayChange={onShowDemOverlayChange}
        onActiveDemLayerIdChange={onActiveDemLayerIdChange}
        demOptions={[
          { value: 'dem-1', label: 'Elevación' },
          { value: 'slope-1', label: 'Pendiente' },
        ]}
      />,
    );

    fireEvent.click(screen.getByLabelText('Todas las capas de Análisis raster'));

    expect(onActiveDemLayerIdChange).toHaveBeenCalledWith('dem-1');
    expect(onShowDemOverlayChange).toHaveBeenCalledWith(true);
  });
});
