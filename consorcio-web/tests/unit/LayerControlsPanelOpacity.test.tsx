/**
 * LayerControlsPanelOpacity.test.tsx
 *
 * map-redesign Fase 3 — Tanda B (task 3.3): per-active-layer opacity slider.
 *   - An ACTIVE registry layer renders a slider seeded from `opacityByLayer[id] ?? 1`.
 *   - Moving it calls `onLayerOpacityChange(id, value/100)`.
 *   - The reset affordance calls `onLayerOpacityChange(id, 1)`.
 *   - An OFF layer renders NO slider.
 */

import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import {
  LayerControlsPanel,
  type LayerFineControl,
} from '../../src/components/map2d/LayerControlsPanel';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

const baseProps = {
  baseLayer: 'osm' as const,
  onBaseLayerChange: () => {},
  layerItems: [{ id: 'soil', label: 'Suelos', category: 'territorio' as const }],
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

function makeFineControl(overrides?: Partial<LayerFineControl>): LayerFineControl {
  return {
    opacityByLayer: {},
    onLayerOpacityChange: vi.fn(),
    orderByLayer: [],
    onLayerOrderChange: vi.fn(),
    ...overrides,
  };
}

describe('<LayerControlsPanel /> — per-layer opacity slider (3.3)', () => {
  it('renders a slider for an ACTIVE registry layer seeded from opacityByLayer[id]', () => {
    renderWithMantine(
      <LayerControlsPanel
        {...baseProps}
        vectorVisibility={{ soil: true }}
        layerFineControl={makeFineControl({ opacityByLayer: { soil: 0.5 } })}
      />
    );
    expect(screen.getByTestId('layer-opacity-soil')).toBeInTheDocument();
    const slider = screen.getByRole('slider', { name: /opacidad de suelos/i });
    expect(slider).toHaveAttribute('aria-valuenow', '50');
  });

  it('seeds at 100% when no override is present (?? 1)', () => {
    renderWithMantine(
      <LayerControlsPanel
        {...baseProps}
        vectorVisibility={{ soil: true }}
        layerFineControl={makeFineControl()}
      />
    );
    expect(screen.getByRole('slider', { name: /opacidad de suelos/i })).toHaveAttribute(
      'aria-valuenow',
      '100'
    );
  });

  it('moving the slider calls onLayerOpacityChange(id, value/100)', () => {
    const fineControl = makeFineControl({ opacityByLayer: { soil: 0.5 } });
    renderWithMantine(
      <LayerControlsPanel
        {...baseProps}
        vectorVisibility={{ soil: true }}
        layerFineControl={fineControl}
      />
    );
    const slider = screen.getByRole('slider', { name: /opacidad de suelos/i });
    // Keyboard is the reliable way to fire Mantine Slider onChange in jsdom
    // (@dnd-kit-style pointer drag is impractical). 50 → ArrowLeft → 49.
    fireEvent.keyDown(slider, { key: 'ArrowLeft' });
    expect(fineControl.onLayerOpacityChange).toHaveBeenCalledWith('soil', expect.closeTo(0.49, 5));
  });

  it('the reset affordance calls onLayerOpacityChange(id, 1)', () => {
    const fineControl = makeFineControl({ opacityByLayer: { soil: 0.3 } });
    renderWithMantine(
      <LayerControlsPanel
        {...baseProps}
        vectorVisibility={{ soil: true }}
        layerFineControl={fineControl}
      />
    );
    fireEvent.click(screen.getByTestId('layer-opacity-reset-soil'));
    expect(fineControl.onLayerOpacityChange).toHaveBeenCalledWith('soil', 1);
  });

  it('renders NO slider for an OFF layer', () => {
    renderWithMantine(
      <LayerControlsPanel
        {...baseProps}
        vectorVisibility={{ soil: false }}
        layerFineControl={makeFineControl({ opacityByLayer: { soil: 0.5 } })}
      />
    );
    expect(screen.queryByTestId('layer-opacity-soil')).not.toBeInTheDocument();
    expect(
      screen.queryByRole('slider', { name: /opacidad de suelos/i })
    ).not.toBeInTheDocument();
  });
});
