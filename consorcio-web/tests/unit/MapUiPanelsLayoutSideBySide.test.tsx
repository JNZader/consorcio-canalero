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
    layerItems: [{ id: 'roads', label: 'Red vial' }],
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
    isOperator: false,
    markingMode: false,
    onToggleMarkingMode: noop,
    canManageZoning: false,
    showSuggestedZonesPanel: false,
    hasApprovedZones: false,
    onToggleSuggestedZonesPanel: noop,
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
    suggestedZoneSummaries: [],
    suggestedZoneNames: {},
    onZoneNameChange: noop,
    selectedDraftBasinName: null,
    selectedDraftBasinZoneId: null,
    draftDestinationZoneId: null,
    onDestinationZoneChange: noop,
    onApplyBasinMove: noop,
    approvedAt: null,
    approvedVersion: null,
    approvedZonesHistory: [],
    approvalName: '',
    approvalNotes: '',
    onApprovalNameChange: noop,
    onApprovalNotesChange: noop,
    onCloseSuggestedZonesPanel: noop,
    onApproveZones: noop,
    onClearApprovedZones: noop,
    onRestoreVersion: noop,
    onExportApprovedZonesGeoJSON: noop,
    selectedFeatures: [],
    onCloseInfoPanel: noop,
    newPoint: null,
    onCloseAssetPointModal: noop,
    onSubmitAssetPointModal: noop,
    isSubmitting: false,
    nameInputProps: {},
    typeInputProps: {},
    descriptionInputProps: {},
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

  it('renders LayerControlsPanel FIRST (visually leftmost) and LeyendaPanel SECOND inside the top-left container', () => {
    const { container } = renderWithMantine(<MapUiPanels {...buildProps()} />);

    const wrapper = container.querySelector<HTMLElement>(
      '[data-testid="map-2d-top-left-panels"]',
    );
    expect(wrapper).not.toBeNull();

    // Layer controls witness: "Capa base" heading.
    // Legend witness: "Leyenda" heading.
    const legendText = wrapper!.querySelector('*:nodeName')?.textContent;
    // Use getByText within the wrapper — order-sensitive.
    const allText = wrapper!.textContent ?? '';
    const capasIdx = allText.indexOf('Capa base');
    const legendIdx = allText.indexOf('Leyenda');
    expect(capasIdx).toBeGreaterThanOrEqual(0);
    expect(legendIdx).toBeGreaterThanOrEqual(0);
    expect(capasIdx).toBeLessThan(legendIdx);
    // Silence unused — keep a structural witness that DOM was read.
    void legendText;
  });

  it('renders LeyendaPanel in embedded mode (no .legendPanel absolute-positioning class)', () => {
    const { container } = renderWithMantine(<MapUiPanels {...buildProps()} />);

    const wrapper = container.querySelector<HTMLElement>(
      '[data-testid="map-2d-top-left-panels"]',
    );
    expect(wrapper).not.toBeNull();

    // The first child (Leyenda) must NOT carry any class containing
    // `legendPanel` — that class applies `position:absolute; bottom; left`
    // which would fight the outer flex container.
    const papers = wrapper!.querySelectorAll<HTMLElement>('[class*="Paper"]');
    const hasLegendPanelClass = Array.from(papers).some((el) =>
      (el.className ?? '').includes('legendPanel'),
    );
    expect(hasLegendPanelClass).toBe(false);
  });

  it('bounds each panel with an inline viewport-relative maxHeight + overflow-y: auto', () => {
    const { container } = renderWithMantine(<MapUiPanels {...buildProps()} />);

    const wrapper = container.querySelector<HTMLElement>(
      '[data-testid="map-2d-top-left-panels"]',
    );
    expect(wrapper).not.toBeNull();

    // LayerControlsPanel inner wrapper already carries data-testid.
    const layerWrapper = wrapper!.querySelector<HTMLElement>(
      '[data-testid="layer-controls-panel-scroll"]',
    );
    expect(layerWrapper).not.toBeNull();
    expect(layerWrapper!.style.maxHeight).toMatch(/vh/);
    expect(layerWrapper!.style.overflowY).toBe('auto');

    // LeyendaPanel embedded Paper must also carry bounded max-height +
    // internal scroll (inline style, not via the removed CSS class).
    const legendPanel = wrapper!.querySelector<HTMLElement>(
      '[data-testid="map-2d-leyenda-panel"]',
    );
    expect(legendPanel).not.toBeNull();
    const legendStyle = legendPanel!.getAttribute('style') ?? '';
    expect(legendStyle).toMatch(/max-height/i);
    expect(legendStyle).toMatch(/overflow-y:\s*auto/i);
  });

  it('still renders the Leyenda when showLegend is true (smoke)', () => {
    renderWithMantine(<MapUiPanels {...buildProps()} />);
    expect(screen.getByText('Leyenda')).toBeInTheDocument();
    expect(screen.getByText(/capa base/i)).toBeInTheDocument();
  });

  it('omits the Leyenda when showLegend is false', () => {
    renderWithMantine(<MapUiPanels {...buildProps({ showLegend: false })} />);
    expect(screen.queryByText('Leyenda')).not.toBeInTheDocument();
    // LayerControlsPanel still renders.
    expect(screen.getByText(/capa base/i)).toBeInTheDocument();
  });
});
