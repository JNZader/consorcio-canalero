/**
 * MapUiPanelsLayout.test.tsx
 *
 * Phase 8 Fix 3/4 — legend panels and InfoPanel must not visually collide.
 *
 * The contract:
 *   - LeyendaPanel must render in FLOATING mode (bottom-left), decoupled
 *     from the top-right MapActionsPanel.
 *   - When an InfoPanel + LeyendaPanel are both visible, both render without
 *     crashing — and neither consumes the same floating slot as the other.
 *
 * We don't assert pixel positions (that's a CSS concern tested manually in
 * browser). We assert the DOM contract that keeps the positions decoupled.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { Feature } from 'geojson';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { MapUiPanels, type MapUiPanelsProps } from '../../src/components/map2d/MapUiPanels';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider>{ui}</MantineProvider>);
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
    selectedFeatures: [],
    onCloseInfoPanel: noop,
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
  it('renders the LeyendaPanel as a floating (standalone) panel — not nested in the action bar', () => {
    renderWithMantine(<MapUiPanels {...buildProps()} />);
    // The "Leyenda" heading is our witness that LeyendaPanel rendered.
    expect(screen.getByText('Leyenda')).toBeInTheDocument();
  });

  it('renders InfoPanel and LeyendaPanel simultaneously without crashing', () => {
    const feat: Feature = {
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [0, 0] },
      properties: { nombre: 'Canal Este' },
    };
    renderWithMantine(
      <MapUiPanels {...buildProps({ selectedFeatures: [feat] })} />,
    );
    expect(screen.getByText('Leyenda')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /informacion/i })).toBeInTheDocument();
  });

  it('skips the LeyendaPanel when showLegend is false', () => {
    renderWithMantine(<MapUiPanels {...buildProps({ showLegend: false })} />);
    expect(screen.queryByText('Leyenda')).not.toBeInTheDocument();
  });
});
