/**
 * MapUiPanelsLayout.test.tsx
 *
 * Phase 8 Fix 3/4 — legend panels and InfoPanel must not visually collide.
 *
 * The contract:
 *   - Layer legends live under En el mapa (UX R2b), not a floating Leyenda panel.
 *   - InfoPanel still renders without colliding with that list.
 *
 * We don't assert pixel positions (that's a CSS concern tested manually in
 * browser). We assert the DOM contract that keeps the positions decoupled.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { MapUiPanels, type MapUiPanelsProps } from '../../src/components/map2d/MapUiPanels';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

function buildProps(overrides: Partial<MapUiPanelsProps> = {}): MapUiPanelsProps {
  const noop = vi.fn();
  return {
    baseLayer: 'osm',
    onBaseLayerChange: noop,
    viewMode: 'base',
    onViewModeChange: noop,
    hasSingleImage: false,
    hasComparison: false,
    singleImageInfo: null,
    comparisonInfo: null,
    layerItems: [],
    vectorVisibility: {},
    onLayerVisibilityChange: noop,
    showIGNOverlay: false,
    onShowIGNOverlayChange: noop,
    demEnabled: false,
    showDemOverlay: false,
    onShowDemOverlayChange: noop,
    activeDemLayerId: null,
    onActiveDemLayerIdChange: noop,
    demOptions: [],
    hasApprovedZones: false,
    onOpenExportPng: noop,
    onExportApprovedZonesPdf: noop,
    showLegend: true,
    consorcios: [],
    activeLegendItems: [{ color: '#0f0', label: 'Cuenca', type: 'border' }],
    visibleRasterLayers: [],
    hiddenClasses: {},
    hiddenRanges: {},
    onClassToggle: noop,
    onRangeToggle: noop,
    fichaActive: false,
    fichaTipo: 'parcela',
    fichaNroCuenta: null,
    fichaLoading: false,
    fichaError: null,
    fichaData: undefined,
    onCloseFicha: noop,
    exportPngModalOpen: false,
    onCloseExportPngModal: noop,
    exportTitle: '',
    exportIncludeLegend: true,
    exportIncludeMetadata: true,
    onExportTitleChange: noop,
    onExportIncludeLegendChange: noop,
    onExportIncludeMetadataChange: noop,
    onExportPng: noop,
    ...overrides,
  };
}

describe('<MapUiPanels /> — Phase 8 legend / InfoPanel layout', () => {
  it('does not float En el mapa or a Leyenda heading over the canvas', () => {
    renderWithMantine(<MapUiPanels {...buildProps()} />);
    expect(screen.queryByTestId('map-active-layers')).not.toBeInTheDocument();
    expect(screen.queryByText('Leyenda')).not.toBeInTheDocument();
  });

  it('does not float the info readout over En el mapa', () => {
    const feat: Feature = {
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [0, 0] },
      properties: { nombre: 'Canal Este' },
    };
    renderWithMantine(
      <MapUiPanels {...buildProps({ selectedFeatures: [feat] })} />,
    );
    expect(screen.queryByTestId('map-active-layers')).not.toBeInTheDocument();
    expect(screen.queryByTestId('map-2d-info-panel')).not.toBeInTheDocument();
  });

  it('skips inline layer legends when showLegend is false', () => {
    renderWithMantine(
      <MapUiPanels {...buildProps({ showLegend: false, vectorVisibility: { roads: true } })} />,
    );
    expect(screen.queryByTestId('layer-inline-legend-roads')).not.toBeInTheDocument();
  });
});

describe('<MapUiPanels /> — InfoPanel + ficha coexistence', () => {
  it('does not shrink the ficha when rendered in MapUiPanels', () => {
    renderWithMantine(<MapUiPanels {...buildProps({ fichaActive: true })} />);

    expect(screen.queryByTestId('map-2d-info-panel')).not.toBeInTheDocument();
    expect(screen.getByTestId('ficha-territorial-panel').className).not.toContain('fichaPanelCompact');
  });

  it('does not paint a floating info card when ficha is inactive', () => {
    renderWithMantine(<MapUiPanels {...buildProps({ fichaActive: false })} />);

    expect(screen.queryByTestId('map-2d-info-panel')).not.toBeInTheDocument();
    expect(screen.queryByTestId('ficha-territorial-panel')).not.toBeInTheDocument();
  });

  it('keeps the full max-height when ONLY the ficha is open', () => {
    renderWithMantine(<MapUiPanels {...buildProps({ fichaActive: true })} />);

    expect(screen.queryByTestId('map-2d-info-panel')).not.toBeInTheDocument();
    expect(screen.getByTestId('ficha-territorial-panel').className).not.toContain(
      'fichaPanelCompact'
    );
  });
});
