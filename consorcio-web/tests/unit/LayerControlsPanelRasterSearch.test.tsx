/**
 * LayerControlsPanelRasterSearch.test.tsx — T3c fix 2.
 *
 * The raster/DEM options live in the Base > "Capa DEM" Select, so the layer
 * search (which only scanned `layerItems`) answered "Sin resultados" for
 * "riesgo" — about a layer the map can absolutely paint. They now surface in
 * their own "Capas raster" results section, and picking one activates the DEM
 * overlay with that raster selected.
 */

import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { LayerControlsPanel } from '../../src/components/map2d/LayerControlsPanel';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

function expandNamed(name: RegExp) {
  const btn = screen.getByRole('button', { name });
  if (btn.getAttribute('aria-expanded') === 'false') fireEvent.click(btn);
  return btn;
}

const demOptions = [
  { value: 'layer-flood', label: 'Riesgo de Inundacion' },
  { value: 'layer-drain', label: 'Necesidad de Drenaje' },
  { value: 'layer-dem', label: 'Modelo de Elevacion' },
];

function baseProps(overrides: Record<string, unknown> = {}) {
  return {
    layerItems: [{ id: 'roads', label: 'Red Vial', category: 'territorio' as const }],
    vectorVisibility: {},
    onLayerVisibilityChange: () => {},
    showIGNOverlay: false,
    onShowIGNOverlayChange: () => {},
    demEnabled: true,
    showDemOverlay: false,
    onShowDemOverlayChange: () => {},
    activeDemLayerId: null,
    onActiveDemLayerIdChange: () => {},
    demOptions,
    ...overrides,
  };
}

function search(term: string) {
  fireEvent.change(screen.getByLabelText('Buscar capa'), { target: { value: term } });
}

describe('<LayerControlsPanel /> — raster search (T3c fix 2)', () => {
  it('surfaces matching raster options instead of "Sin resultados"', () => {
    renderWithMantine(<LayerControlsPanel {...baseProps()} />);

    search('riesgo');

    expect(screen.queryByTestId('layer-controls-no-results')).toBeNull();
    expect(screen.getByTestId('layer-controls-raster')).toBeInTheDocument();
    expect(screen.getByTestId('raster-search-option-layer-flood')).toBeInTheDocument();
    // Non-matching raster options stay out of the results.
    expect(screen.queryByTestId('raster-search-option-layer-drain')).toBeNull();
  });

  it('activates the DEM overlay with that raster when the result is clicked', () => {
    const onShowDemOverlayChange = vi.fn();
    const onActiveDemLayerIdChange = vi.fn();
    renderWithMantine(
      <LayerControlsPanel
        {...baseProps({ onShowDemOverlayChange, onActiveDemLayerIdChange })}
      />
    );

    search('riesgo');
    fireEvent.click(screen.getByTestId('raster-search-option-layer-flood'));

    expect(onActiveDemLayerIdChange).toHaveBeenCalledWith('layer-flood');
    expect(onShowDemOverlayChange).toHaveBeenCalledWith(true);
  });

  it('shows no raster section when the DEM overlay is unavailable', () => {
    renderWithMantine(<LayerControlsPanel {...baseProps({ demEnabled: false })} />);

    search('riesgo');

    expect(screen.queryByTestId('layer-controls-raster')).toBeNull();
  });

  it('keeps the raster family collapsed outside of a search', () => {
    renderWithMantine(<LayerControlsPanel {...baseProps()} />);
    expect(screen.getByTestId('layer-controls-raster')).toBeInTheDocument();
    expect(
      screen.queryByRole('radio', { name: 'Riesgo de Inundacion' }),
    ).not.toBeInTheDocument();
  });

  it('shows the gated hazard toggle and includes its mounted rasters in the base count', () => {
    const onActiveChange = vi.fn();
    renderWithMantine(
      <LayerControlsPanel
        {...baseProps()}
        hazardLayerControl={{
          active: true,
          activeLayerCount: 3,
          onActiveChange,
          visible: true,
        }}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /^base/i }));
    const hazardToggle = screen.getByLabelText('Visor de riesgos');
    expect(hazardToggle).toBeChecked();
    fireEvent.click(hazardToggle);

    expect(onActiveChange).toHaveBeenCalledWith(false);
  });

  it('offers Comparar con… when a raster is on (UX R7)', () => {
    const onRasterCompare = vi.fn();
    renderWithMantine(
      <LayerControlsPanel
        {...baseProps({
          showDemOverlay: true,
          activeDemLayerId: 'layer-flood',
          onRasterCompare,
        })}
      />,
    );
    expandNamed(/análisis raster/i);
    expect(screen.getByTestId('raster-compare-select')).toBeInTheDocument();
  });
});
