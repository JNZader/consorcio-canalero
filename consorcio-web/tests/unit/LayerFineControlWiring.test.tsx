/**
 * LayerFineControlWiring.test.tsx
 *
 * map-redesign Fase 3 — Tanda B (task 3.4): the grouped `layerFineControl`
 * prop is threaded MapUiPanels → LayerControlsPanel and its callbacks reach
 * the setter (mock). A callback fired through the tree lands on the mock — the
 * same object MapaMapLibre binds to `setLayerOpacity('map2d', …)` /
 * `setLayerOrder('map2d', …)`.
 */

import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import {
  LayerControlsPanel,
  type LayerFineControl,
} from '../../src/components/map2d/LayerControlsPanel';
import { MAP_VIEW_MODE } from '../../src/components/map2d/ViewModePanel';
import { MapUiPanels, type MapUiPanelsProps } from '../../src/components/map2d/MapUiPanels';
import { DEFAULT_LAYER_ORDER } from '../../src/components/map2d/layerRenderRegistry';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

function makeFineControl(overrides?: Partial<LayerFineControl>): LayerFineControl {
  return {
    opacityByLayer: {},
    onLayerOpacityChange: vi.fn(),
    orderByLayer: [],
    onLayerOrderChange: vi.fn(),
    ...overrides,
  };
}

/** Minimal-but-complete MapUiPanels props (mirrors map2d-panels.test.tsx). */
function makeMapUiPanelsProps(fineControl: LayerFineControl): MapUiPanelsProps {
  return {
    baseLayer: 'osm',
    onBaseLayerChange: () => {},
    viewMode: MAP_VIEW_MODE.BASE,
    onViewModeChange: () => {},
    hasSingleImage: false,
    hasComparison: false,
    singleImageInfo: null,
    comparisonInfo: null,
    layerItems: [{ id: 'soil', label: 'Suelos', category: 'territorio' }],
    vectorVisibility: { soil: true },
    onLayerVisibilityChange: () => {},
    showIGNOverlay: false,
    onShowIGNOverlayChange: () => {},
    demEnabled: false,
    showDemOverlay: false,
    onShowDemOverlayChange: () => {},
    activeDemLayerId: null,
    onActiveDemLayerIdChange: () => {},
    demOptions: [],
    layerFineControl: fineControl,
    hasApprovedZones: false,
    onOpenExportPng: () => {},
    onExportApprovedZonesPdf: () => {},
    showLegend: false,
    consorcios: [],
    activeLegendItems: [],
    visibleRasterLayers: [],
    hiddenClasses: {},
    hiddenRanges: {},
    onClassToggle: () => {},
    onRangeToggle: () => {},
    selectedFeatures: [],
    onCloseInfoPanel: () => {},
    exportPngModalOpen: false,
    onCloseExportPngModal: () => {},
    exportTitle: '',
    exportIncludeLegend: false,
    exportIncludeMetadata: false,
    onExportTitleChange: () => {},
    onExportIncludeLegendChange: () => {},
    onExportIncludeMetadataChange: () => {},
    onExportPng: () => {},
  };
}

describe('layerFineControl wiring (3.4)', () => {
  it('LayerControlsPanel forwards the opacity callback to the injected setter', () => {
    const fineControl = makeFineControl({ opacityByLayer: { soil: 0.5 } });
    renderWithMantine(
      <LayerControlsPanel
        baseLayer="osm"
        onBaseLayerChange={() => {}}
        layerItems={[{ id: 'soil', label: 'Suelos', category: 'territorio' }]}
        vectorVisibility={{ soil: true }}
        onLayerVisibilityChange={() => {}}
        showIGNOverlay={false}
        onShowIGNOverlayChange={() => {}}
        demEnabled={false}
        showDemOverlay={false}
        onShowDemOverlayChange={() => {}}
        activeDemLayerId={null}
        onActiveDemLayerIdChange={() => {}}
        demOptions={[]}
        layerFineControl={fineControl}
      />
    );
    fireEvent.click(screen.getByTestId('layer-opacity-reset-soil'));
    expect(fineControl.onLayerOpacityChange).toHaveBeenCalledWith('soil', 1);
  });

  it('LayerControlsPanel forwards the order-reset callback to the injected setter', () => {
    const fineControl = makeFineControl({ orderByLayer: ['roads', 'waterways'] });
    renderWithMantine(
      <LayerControlsPanel
        baseLayer="osm"
        onBaseLayerChange={() => {}}
        layerItems={[{ id: 'soil', label: 'Suelos', category: 'territorio' }]}
        vectorVisibility={{ soil: true }}
        onLayerVisibilityChange={() => {}}
        showIGNOverlay={false}
        onShowIGNOverlayChange={() => {}}
        demEnabled={false}
        showDemOverlay={false}
        onShowDemOverlayChange={() => {}}
        activeDemLayerId={null}
        onActiveDemLayerIdChange={() => {}}
        demOptions={[]}
        layerFineControl={fineControl}
      />
    );
    // "Orden de capas" is a collapsible section, closed by default — expand it.
    fireEvent.click(screen.getByTestId('layer-order-collapsible-header'));
    fireEvent.click(screen.getByTestId('layer-order-reset'));
    // FF-B1: reset writes the explicit default set (not `[]`) so the map
    // re-hoists to canonical order instead of staying on the custom stacking.
    expect(fineControl.onLayerOrderChange).toHaveBeenCalledWith([...DEFAULT_LAYER_ORDER]);
  });

  it('MapUiPanels threads layerFineControl down to LayerControlsPanel (callback reaches setter)', () => {
    const fineControl = makeFineControl({ opacityByLayer: { soil: 0.25 } });
    renderWithMantine(<MapUiPanels {...makeMapUiPanelsProps(fineControl)} />);
    fireEvent.click(screen.getByTestId('layer-opacity-reset-soil'));
    expect(fineControl.onLayerOpacityChange).toHaveBeenCalledWith('soil', 1);
  });
});
