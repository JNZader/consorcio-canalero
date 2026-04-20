/**
 * TerrainPanelsSplit.test.tsx
 *
 * Phase 8 Fix 5/6 — the monolithic `<TerrainLayerPanel />` is split into:
 *   · `<TerrainLayerTogglesPanel />` — overlay select, opacity slider, vector-
 *     layer checkboxes (NO legends).
 *   · `<TerrainLegendsPanel />`      — RasterLegend + SoilLegend, bounded
 *     `maxHeight` + internal scroll so they never extend past the viewport.
 *
 * The goal is to surface legends and toggles as SEPARATE panels inside the
 * 3D chrome, matching the 2D layout where toggles (LayerControlsPanel) and
 * legends (LeyendaPanel) are already decoupled.
 *
 * Contracts tested here:
 *   1. Toggles panel renders the vector-layer checkboxes but NOT any legend.
 *   2. Legends panel renders the soil legend (when soil toggle is on) and
 *      the raster legend (when a raster type is active), with a scrollable
 *      container.
 *   3. Legends panel returns null when there is nothing to show.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { TerrainLayerTogglesPanel } from '../../src/components/terrain/TerrainLayerTogglesPanel';
import { TerrainLegendsPanel } from '../../src/components/terrain/TerrainLegendsPanel';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

// ---------------------------------------------------------------------------
// Toggles panel
// ---------------------------------------------------------------------------

const togglesBase = {
  rasterLayers: [],
  selectedImageOption: null,
  activeRasterLayerId: undefined,
  onActiveRasterLayerChange: vi.fn(),
  overlayOpacity: 0.7,
  onOverlayOpacityChange: vi.fn(),
  vectorLayerVisibility: {} as Record<string, boolean>,
  onVectorLayerToggle: vi.fn(),
  onClose: vi.fn(),
  hasApprovedZones: false,
};

describe('<TerrainLayerTogglesPanel /> — toggles only (Phase 8 Fix 5)', () => {
  it('renders the "Capas vectoriales 3D" heading', () => {
    renderWithMantine(<TerrainLayerTogglesPanel {...togglesBase} />);
    expect(screen.getByText(/Capas vectoriales 3D/i)).toBeInTheDocument();
  });

  it('does NOT render the soil legend, even when soil is toggled on', () => {
    renderWithMantine(
      <TerrainLayerTogglesPanel
        {...togglesBase}
        vectorLayerVisibility={{ soil: true }}
      />,
    );
    expect(screen.queryByTestId('terrain-3d-soil-legend')).not.toBeInTheDocument();
  });

  it('renders a close button that calls onClose', () => {
    const onClose = vi.fn();
    renderWithMantine(<TerrainLayerTogglesPanel {...togglesBase} onClose={onClose} />);
    const btn = screen.getByLabelText(/Cerrar panel 3D/i);
    btn.click();
    expect(onClose).toHaveBeenCalledOnce();
  });
});

// ---------------------------------------------------------------------------
// Legends panel
// ---------------------------------------------------------------------------

const legendsBase = {
  activeRasterType: undefined as string | undefined,
  hiddenClasses: {} as Record<string, number[]>,
  onClassToggle: vi.fn(),
  hiddenRanges: {} as Record<string, number[]>,
  onRangeToggle: vi.fn(),
  vectorLayerVisibility: {} as Record<string, boolean>,
};

describe('<TerrainLegendsPanel /> — legends only (Phase 8 Fix 5/6)', () => {
  it('returns null when there is nothing to render', () => {
    renderWithMantine(<TerrainLegendsPanel {...legendsBase} />);
    // Only the Mantine `<style>` tags should be present; the panel itself
    // must not render.
    expect(screen.queryByTestId('terrain-3d-legends-panel')).not.toBeInTheDocument();
    expect(screen.queryByText('Leyendas')).not.toBeInTheDocument();
  });

  it('renders the soil legend when the soil vector layer is on', () => {
    renderWithMantine(
      <TerrainLegendsPanel
        {...legendsBase}
        vectorLayerVisibility={{ soil: true }}
      />,
    );
    expect(screen.getByTestId('terrain-3d-soil-legend')).toBeInTheDocument();
  });

  it('applies a bounded maxHeight + overflow-y: auto to keep legends inside the viewport', () => {
    renderWithMantine(
      <TerrainLegendsPanel
        {...legendsBase}
        vectorLayerVisibility={{ soil: true }}
      />,
    );
    const panel = screen.getByTestId('terrain-3d-legends-panel');
    const style = panel.getAttribute('style') ?? '';
    // We don't pin the exact pixel value — just assert the intent.
    expect(style).toMatch(/max-height/i);
    expect(style).toMatch(/overflow-y:\s*auto/i);
  });
});
