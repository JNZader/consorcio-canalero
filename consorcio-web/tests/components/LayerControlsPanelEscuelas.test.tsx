/**
 * LayerControlsPanelEscuelas.test.tsx
 *
 * Covers the Pilar Azul (Escuelas rurales) single master toggle inside the
 * existing "Capas" `CollapsibleSection` of `<LayerControlsPanel />`. The
 * escuelas toggle has NO Canales-style sub-layer hierarchy — it's one master
 * with one layer (7 features). Threading is identical to any other
 * `layerItems` entry: `buildVectorLayerItems` (Batch D task 3.4) returns a
 * `{ id: 'escuelas', label: 'Escuelas rurales' }` row, which the panel
 * renders via the same `layerItems.map()` loop used for soil / catastro /
 * approved_zones.
 *
 * See design `sdd/escuelas-rurales/design` §7 state wiring.
 */

import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { LayerControlsPanel } from '../../src/components/map2d/LayerControlsPanel';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

const baseProps = {
  baseLayer: 'osm' as const,
  onBaseLayerChange: () => {},
  showIGNOverlay: false,
  onShowIGNOverlayChange: () => {},
  demEnabled: false,
  showDemOverlay: false,
  onShowDemOverlayChange: () => {},
  activeDemLayerId: null,
  onActiveDemLayerIdChange: () => {},
  demOptions: [],
};

const ESCUELAS_ITEM = { id: 'escuelas', label: 'Escuelas rurales' };

describe('<LayerControlsPanel /> — Escuelas rurales toggle', () => {
  it('renders the "Escuelas rurales" checkbox when provided in layerItems', () => {
    renderWithMantine(
      <LayerControlsPanel
        {...baseProps}
        layerItems={[ESCUELAS_ITEM]}
        vectorVisibility={{ escuelas: false }}
        onLayerVisibilityChange={() => {}}
      />,
    );

    expect(screen.getByLabelText('Escuelas rurales')).toBeInTheDocument();
  });

  it('defaults to unchecked when vectorVisibility.escuelas is false', () => {
    renderWithMantine(
      <LayerControlsPanel
        {...baseProps}
        layerItems={[ESCUELAS_ITEM]}
        vectorVisibility={{ escuelas: false }}
        onLayerVisibilityChange={() => {}}
      />,
    );

    expect(screen.getByLabelText('Escuelas rurales')).not.toBeChecked();
  });

  it('reflects checked state from vectorVisibility.escuelas === true', () => {
    renderWithMantine(
      <LayerControlsPanel
        {...baseProps}
        layerItems={[ESCUELAS_ITEM]}
        vectorVisibility={{ escuelas: true }}
        onLayerVisibilityChange={() => {}}
      />,
    );

    expect(screen.getByLabelText('Escuelas rurales')).toBeChecked();
  });

  it('calls onLayerVisibilityChange("escuelas", true) when toggled ON', () => {
    const onLayerVisibilityChange = vi.fn();
    renderWithMantine(
      <LayerControlsPanel
        {...baseProps}
        layerItems={[ESCUELAS_ITEM]}
        vectorVisibility={{ escuelas: false }}
        onLayerVisibilityChange={onLayerVisibilityChange}
      />,
    );

    fireEvent.click(screen.getByLabelText('Escuelas rurales'));
    expect(onLayerVisibilityChange).toHaveBeenCalledWith('escuelas', true);
  });

  it('calls onLayerVisibilityChange("escuelas", false) when toggled OFF', () => {
    const onLayerVisibilityChange = vi.fn();
    renderWithMantine(
      <LayerControlsPanel
        {...baseProps}
        layerItems={[ESCUELAS_ITEM]}
        vectorVisibility={{ escuelas: true }}
        onLayerVisibilityChange={onLayerVisibilityChange}
      />,
    );

    fireEvent.click(screen.getByLabelText('Escuelas rurales'));
    expect(onLayerVisibilityChange).toHaveBeenCalledWith('escuelas', false);
  });

  it('does NOT render the Escuelas toggle when not present in layerItems', () => {
    renderWithMantine(
      <LayerControlsPanel
        {...baseProps}
        layerItems={[]}
        vectorVisibility={{ escuelas: true }}
        onLayerVisibilityChange={() => {}}
      />,
    );

    expect(screen.queryByLabelText('Escuelas rurales')).not.toBeInTheDocument();
  });
});

describe('buildVectorLayerItems — escuelas entry', () => {
  it('appends { id: "escuelas", label: "Escuelas rurales" } when showEscuelas is true', async () => {
    const { buildVectorLayerItems } = await import(
      '../../src/components/map2d/map2dDerived'
    );

    const items = buildVectorLayerItems({
      basins: null,
      approvedZonesCollection: null,
      roadsCollection: null,
      intersectionsLength: 0,
      isAdmin: false,
      showPilarVerde: false,
      showPilarAzul: false,
      showEscuelas: true,
    } as Parameters<typeof buildVectorLayerItems>[0]);

    const escuelas = items.find((item) => item.id === 'escuelas');
    expect(escuelas).toEqual({ id: 'escuelas', label: 'Escuelas rurales' });
  });

  it('OMITS the escuelas entry when showEscuelas is false', async () => {
    const { buildVectorLayerItems } = await import(
      '../../src/components/map2d/map2dDerived'
    );

    const items = buildVectorLayerItems({
      basins: null,
      approvedZonesCollection: null,
      roadsCollection: null,
      intersectionsLength: 0,
      isAdmin: false,
      showPilarVerde: false,
      showPilarAzul: false,
      showEscuelas: false,
    } as Parameters<typeof buildVectorLayerItems>[0]);

    expect(items.find((item) => item.id === 'escuelas')).toBeUndefined();
  });

  it('defaults showEscuelas to false when the param is not provided (backwards compat)', async () => {
    const { buildVectorLayerItems } = await import(
      '../../src/components/map2d/map2dDerived'
    );

    const items = buildVectorLayerItems({
      basins: null,
      approvedZonesCollection: null,
      roadsCollection: null,
      intersectionsLength: 0,
      isAdmin: false,
    });

    expect(items.find((item) => item.id === 'escuelas')).toBeUndefined();
  });
});
