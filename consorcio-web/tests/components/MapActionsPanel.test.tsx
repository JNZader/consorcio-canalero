/**
 * MapActionsPanel.test.tsx
 *
 * Batch F — Phase 6 — KMZ export button.
 *
 * Pins the contract for the "Exportar KMZ" entry inside the existing
 * "Exportar" `Menu` dropdown in `MapActionsPanel`:
 *
 *   1. When `onExportKmz` is provided, a menu item with the literal
 *      label "Exportar KMZ" renders inside the same dropdown that owns
 *      "Exportar PNG" / "Exportar PDF".
 *   2. Clicking that menu item invokes `onExportKmz` exactly once with
 *      no arguments.
 *   3. When `onExportKmz` is NOT provided (undefined), the menu item is
 *      NOT rendered at all — this mirrors how the "Exportar PDF" item
 *      is gated by `hasApprovedZones`. The overall "Exportar" dropdown
 *      stays clickable because PNG is always on.
 *
 * Rationale for not disabling the KMZ entry based on
 * `visibleVectors`: YPF is modelled as an always-on floor inside
 * `handleExportKmz` (via `ALWAYS_ON_KEYS` in the builder), so the KMZ
 * is never "empty"; the on-empty UX is already handled inside the
 * handler itself (try/catch + red notification). Mirrors PNG's
 * always-enabled behaviour.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { MapActionsPanel } from '../../src/components/map2d/MapActionsPanel';
import { MapUiPanels, type MapUiPanelsProps } from '../../src/components/map2d/MapUiPanels';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

function buildMapUiPanelsProps(overrides: Partial<MapUiPanelsProps> = {}): MapUiPanelsProps {
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
    isOperator: false,
    markingMode: false,
    onToggleMarkingMode: noop,
    canManageZoning: false,
    showSuggestedZonesPanel: false,
    hasApprovedZones: false,
    onToggleSuggestedZonesPanel: noop,
    onOpenExportPng: noop,
    onExportApprovedZonesPdf: noop,
    showLegend: false,
    consorcios: [],
    activeLegendItems: [],
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

describe('<MapActionsPanel /> — Exportar KMZ menu item', () => {
  it('exposes pressed and expanded state for map action toggles', () => {
    renderWithMantine(
      <MapActionsPanel
        isOperator
        markingMode
        onToggleMarkingMode={() => {}}
        canManageZoning
        showSuggestedZonesPanel
        hasApprovedZones
        onToggleSuggestedZonesPanel={() => {}}
        onOpenExportPng={() => {}}
        onExportApprovedZonesPdf={() => {}}
      />
    );

    expect(screen.getByRole('button', { name: /cancelar marcado/i })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    expect(screen.getByRole('button', { name: /ocultar zonificación/i })).toHaveAttribute(
      'aria-expanded',
      'true'
    );
    expect(screen.getByRole('button', { name: /ocultar zonificación/i })).toHaveAttribute(
      'aria-controls',
      'map-suggested-zones-panel'
    );
  });

  it('renders the "Exportar KMZ" menu item inside the Export dropdown when onExportKmz is provided', async () => {
    const user = userEvent.setup();

    renderWithMantine(
      <MapActionsPanel
        isOperator={false}
        markingMode={false}
        onToggleMarkingMode={() => {}}
        canManageZoning={false}
        showSuggestedZonesPanel={false}
        hasApprovedZones={false}
        onToggleSuggestedZonesPanel={() => {}}
        onOpenExportPng={() => {}}
        onExportApprovedZonesPdf={() => {}}
        onExportKmz={() => {}}
      />
    );

    // Open the "Exportar" Menu trigger.
    await user.click(screen.getByRole('button', { name: /exportar/i }));

    // Literal label match — must be EXACTLY "Exportar KMZ".
    expect(screen.getByText('Exportar KMZ')).toBeInTheDocument();
  });

  it('invokes onExportKmz exactly once with no arguments when the menu item is clicked', async () => {
    const user = userEvent.setup();
    const onExportKmz = vi.fn();

    renderWithMantine(
      <MapActionsPanel
        isOperator={false}
        markingMode={false}
        onToggleMarkingMode={() => {}}
        canManageZoning={false}
        showSuggestedZonesPanel={false}
        hasApprovedZones={false}
        onToggleSuggestedZonesPanel={() => {}}
        onOpenExportPng={() => {}}
        onExportApprovedZonesPdf={() => {}}
        onExportKmz={onExportKmz}
      />
    );

    await user.click(screen.getByRole('button', { name: /exportar/i }));
    await user.click(screen.getByText('Exportar KMZ'));

    // Note: Mantine's `Menu.Item` passes the DOM click event through to
    // onClick, so we assert call count, not zero-arg invocation.
    // `handleExportKmz` ignores arguments — see useMapActionHandlers.ts.
    expect(onExportKmz).toHaveBeenCalledTimes(1);
  });

  it('omits the "Exportar KMZ" menu item when onExportKmz is undefined', async () => {
    const user = userEvent.setup();

    renderWithMantine(
      <MapActionsPanel
        isOperator={false}
        markingMode={false}
        onToggleMarkingMode={() => {}}
        canManageZoning={false}
        showSuggestedZonesPanel={false}
        hasApprovedZones={false}
        onToggleSuggestedZonesPanel={() => {}}
        onOpenExportPng={() => {}}
        onExportApprovedZonesPdf={() => {}}
      />
    );

    await user.click(screen.getByRole('button', { name: /exportar/i }));

    // The dropdown is open and PNG is visible — prove it to distinguish
    // "menu is closed" from "KMZ item is absent".
    expect(screen.getByText('Exportar PNG')).toBeInTheDocument();
    expect(screen.queryByText('Exportar KMZ')).not.toBeInTheDocument();
  });

  it('sits as a sibling Menu.Item alongside "Exportar PNG" (both inside the same dropdown)', async () => {
    const user = userEvent.setup();

    renderWithMantine(
      <MapActionsPanel
        isOperator={false}
        markingMode={false}
        onToggleMarkingMode={() => {}}
        canManageZoning={false}
        showSuggestedZonesPanel={false}
        hasApprovedZones={false}
        onToggleSuggestedZonesPanel={() => {}}
        onOpenExportPng={() => {}}
        onExportApprovedZonesPdf={() => {}}
        onExportKmz={() => {}}
      />
    );

    await user.click(screen.getByRole('button', { name: /exportar/i }));

    // Both PNG and KMZ are present in the same open dropdown.
    const png = screen.getByText('Exportar PNG');
    const kmz = screen.getByText('Exportar KMZ');
    expect(png).toBeInTheDocument();
    expect(kmz).toBeInTheDocument();

    // And both are rendered as items of a Mantine Menu — i.e. have a
    // shared ancestor with role="menu".
    const menu = png.closest('[role="menu"]');
    expect(menu).not.toBeNull();
    expect(menu?.contains(kmz)).toBe(true);
  });
});

describe('<MapUiPanels /> — onExportKmz wiring to MapActionsPanel', () => {
  it('threads onExportKmz through MapUiPanels so clicking "Exportar KMZ" invokes the handler', async () => {
    const user = userEvent.setup();
    const onExportKmz = vi.fn();

    renderWithMantine(
      <MapUiPanels {...buildMapUiPanelsProps({ onExportKmz })} />
    );

    await user.click(screen.getByRole('button', { name: /exportar/i }));
    await user.click(screen.getByText('Exportar KMZ'));

    expect(onExportKmz).toHaveBeenCalledTimes(1);
  });

  it('does NOT render the "Exportar KMZ" item when MapUiPanels receives no onExportKmz', async () => {
    const user = userEvent.setup();

    renderWithMantine(<MapUiPanels {...buildMapUiPanelsProps()} />);

    await user.click(screen.getByRole('button', { name: /exportar/i }));
    expect(screen.getByText('Exportar PNG')).toBeInTheDocument();
    expect(screen.queryByText('Exportar KMZ')).not.toBeInTheDocument();
  });
});
