/**
 * LayerControlsPanelMaxHeight.test.tsx
 *
 * Layout guard for `<LayerControlsPanel />` in 2D.
 *
 * Problem fixed: when many layer toggles + DEM + attributions are active,
 * the top-left `LayerControlsPanel` used to grow downward and overlap
 * the bottom-left `LeyendaPanel`. The panel now renders a bounded outer
 * wrapper that scrolls internally instead of overflowing the viewport.
 *
 * This test is a REGRESSION GUARD — it asserts that the outer wrapper
 * carries inline `maxHeight` (viewport-relative) and `overflowY: auto`
 * so content stays within the viewport and cannot cover adjacent UI.
 */

import { MantineProvider } from '@mantine/core';
import { render } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { LayerControlsPanel } from '../../src/components/map2d/LayerControlsPanel';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

const baseProps = {
  baseLayer: 'osm' as const,
  onBaseLayerChange: () => {},
  layerItems: [
    { id: 'catastro', label: 'Catastro' },
    { id: 'pilar_verde_bpa_2025', label: 'BPA 2025' },
  ],
  vectorVisibility: {},
  onLayerVisibilityChange: () => {},
  showIGNOverlay: false,
  onShowIGNOverlayChange: () => {},
  demEnabled: false,
  showDemOverlay: false,
  onShowDemOverlayChange: () => {},
  activeDemLayerId: null,
  onActiveDemLayerIdChange: () => {},
  demOptions: [],
};

describe('<LayerControlsPanel /> — bounded max-height wrapper (regression guard)', () => {
  it('renders an outer wrapper with inline viewport-relative maxHeight', () => {
    const { container } = renderWithMantine(<LayerControlsPanel {...baseProps} />);

    const wrapper = container.querySelector<HTMLElement>(
      '[data-testid="layer-controls-panel-scroll"]',
    );
    expect(wrapper).not.toBeNull();

    const maxHeight = wrapper?.style.maxHeight ?? '';
    // Accept any viewport-relative bound (vh or calc(...vh...)) — the exact
    // number is a design call, but it MUST be viewport-relative so the
    // panel never exceeds the visible area.
    expect(maxHeight).toMatch(/vh/);
  });

  it('renders the outer wrapper with overflowY: auto so long content scrolls internally', () => {
    const { container } = renderWithMantine(<LayerControlsPanel {...baseProps} />);

    const wrapper = container.querySelector<HTMLElement>(
      '[data-testid="layer-controls-panel-scroll"]',
    );
    expect(wrapper).not.toBeNull();
    expect(wrapper?.style.overflowY).toBe('auto');
  });

  it('renders the outer wrapper with overflowX: hidden as a safety cap', () => {
    const { container } = renderWithMantine(<LayerControlsPanel {...baseProps} />);

    const wrapper = container.querySelector<HTMLElement>(
      '[data-testid="layer-controls-panel-scroll"]',
    );
    expect(wrapper).not.toBeNull();
    expect(wrapper?.style.overflowX).toBe('hidden');
  });
});
