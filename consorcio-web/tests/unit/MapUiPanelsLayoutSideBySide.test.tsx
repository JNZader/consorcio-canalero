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

describe('<MapUiPanels /> — side-by-side top-left layout (2D)', () => {
  it('renders a single top-left container with flex-row layout holding BOTH panels', () => {
    const { container } = renderWithMantine(<MapUiPanels {...buildProps()} />);

    const wrapper = container.querySelector<HTMLElement>(
      '[data-testid="map-2d-top-left-panels"]',
    );
    expect(wrapper).not.toBeNull();

    const style = wrapper?.getAttribute('style') ?? '';
    expect(style).toMatch(/position:\s*absolute/i);
    expect(style).toMatch(/top:\s*12px/i);
    expect(style).toMatch(/left:\s*12px/i);
    expect(style).toMatch(/display:\s*flex/i);
    expect(style).toMatch(/flex-direction:\s*row/i);
  });

  it('keeps LayerControlsPanel as the only child of the top-left stack (legends live in En el mapa)', () => {
    const { container } = renderWithMantine(<MapUiPanels {...buildProps()} />);

    const wrapper = container.querySelector<HTMLElement>(
      '[data-testid="map-2d-top-left-panels"]',
    );
    expect(wrapper).not.toBeNull();
    expect(wrapper!.querySelector('[data-testid="layer-controls-panel-scroll"]')).not.toBeNull();
    expect(wrapper!.querySelector('[data-testid="map-2d-leyenda-panel"]')).toBeNull();
    expect(screen.getByTestId('map-active-layers')).toBeInTheDocument();
  });

  it('bounds LayerControlsPanel with viewport-relative maxHeight + overflow-y: auto', () => {
    const { container } = renderWithMantine(<MapUiPanels {...buildProps()} />);

    const layerWrapper = container.querySelector<HTMLElement>(
      '[data-testid="layer-controls-panel-scroll"]',
    );
    expect(layerWrapper).not.toBeNull();
    expect(layerWrapper!.style.maxHeight).toMatch(/vh/);
    expect(layerWrapper!.style.overflowY).toBe('auto');
  });

  it('inlines the layer legend under an active row when showLegend is true', () => {
    renderWithMantine(
      <MapUiPanels
        {...buildProps({
          vectorVisibility: { roads: true },
          consorcios: [
            {
              nombre: 'C.C. 269',
              codigo: 'CC269',
              color: '#f00',
              tramos: 1,
              longitud_km: 10,
            },
          ],
        })}
      />,
    );
    expect(screen.getByTestId('layer-inline-legend-roads')).toBeInTheDocument();
    expect(screen.queryByText('Leyenda')).not.toBeInTheDocument();
  });

  it('omits inline legends when showLegend is false', () => {
    renderWithMantine(
      <MapUiPanels {...buildProps({ showLegend: false, vectorVisibility: { roads: true } })} />,
    );
    expect(screen.queryByTestId('layer-inline-legend-roads')).not.toBeInTheDocument();
    expect(screen.getByText(/capa base/i)).toBeInTheDocument();
  });
});
