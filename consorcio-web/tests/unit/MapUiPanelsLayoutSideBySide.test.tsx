/**
 * MapUiPanelsLayoutSideBySide.test.tsx
 *
 * 2D layout fix — the previous `maxHeight + overflow-y: auto` attempt on
 * `LayerControlsPanel` did not stop the visual collision between the
 * top-left `LayerControlsPanel` and the bottom-left `LeyendaPanel`
 * (which was positioned via the `.legendPanel` CSS class).
 *
 * The new approach mirrors the 3D pattern (TerrainLayerTogglesPanel /
 * TerrainLegendsPanel) by rendering BOTH panels side-by-side at the
 * top-left of the map:
 *
 *   [LeyendaPanel] [LayerControlsPanel]
 *
 * Contracts asserted here:
 *   1. A single `data-testid="map-2d-top-left-panels"` flex-row container
 *      owns the positioning (position:absolute, top:12, left:12).
 *   2. Inside that container, LeyendaPanel renders FIRST (visually
 *      leftmost) and LayerControlsPanel SECOND.
 *   3. In the new layout, LeyendaPanel is rendered in `embedded` mode —
 *      it MUST NOT carry the old `.legendPanel` absolute-positioning
 *      class (the parent owns positioning now).
 *   4. Each panel keeps its own bounded `maxHeight` + `overflow-y: auto`
 *      so neither overflows the viewport.
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
    layerItems: [{ id: 'roads', label: 'Red vial', category: 'territorio' as const }],
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

describe('<MapUiPanels /> — the floating layer stack is gone', () => {
  it('does not paint the legacy top-left layer panels over the canvas', () => {
    const { container } = renderWithMantine(<MapUiPanels {...buildProps()} />);
    expect(container.querySelector('[data-testid="map-2d-top-left-panels"]')).toBeNull();
    expect(container.querySelector('[data-testid="layer-controls-panel-scroll"]')).toBeNull();
    expect(screen.queryByTestId('map-2d-leyenda-panel')).not.toBeInTheDocument();
  });

  it('keeps the right-hand column for home and export', () => {
    renderWithMantine(<MapUiPanels {...buildProps()} />);
    expect(screen.getByTestId('map-right-stack')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Exportar' })).toBeInTheDocument();
  });
});
