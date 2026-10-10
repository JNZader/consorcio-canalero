import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { LayerControlsPanel } from '../../src/components/map2d/LayerControlsPanel';
import { LAYER_CATEGORY } from '../../src/components/map2d/map2dDerived';

function wrap(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

const baseProps = {
  layerItems: [
    { id: 'roads', label: 'Red Vial', category: LAYER_CATEGORY.TERRITORIO },
    {
      id: 'escuelas',
      label: 'Escuelas rurales',
      category: LAYER_CATEGORY.TERRITORIO,
    },
  ],
  vectorVisibility: { roads: true, escuelas: false },
  onLayerVisibilityChange: vi.fn(),
  showIGNOverlay: false,
  onShowIGNOverlayChange: vi.fn(),
  demEnabled: false,
  showDemOverlay: false,
  onShowDemOverlayChange: vi.fn(),
  activeDemLayerId: null,
  onActiveDemLayerIdChange: vi.fn(),
  demOptions: [],
};

describe('LayerControlsPanel variant 3d', () => {
  it('hides Base, raster analysis, and ajustes', () => {
    wrap(
      <LayerControlsPanel
        {...baseProps}
        variant="3d"
        unsupportedLayerIds={['escuelas']}
      />,
    );
    expect(screen.queryByTestId('layer-controls-capas')).not.toBeInTheDocument();
    expect(screen.queryByTestId('layer-controls-raster')).not.toBeInTheDocument();
    expect(screen.queryByTestId('layer-controls-ajustes')).not.toBeInTheDocument();
  });

  it('grays unsupported layers with tooltip no disponible en 3D', async () => {
    const user = userEvent.setup();
    wrap(
      <LayerControlsPanel
        {...baseProps}
        variant="3d"
        unsupportedLayerIds={['escuelas']}
      />,
    );
    await user.click(screen.getByTestId('layer-family-territorio-control'));
    const checkbox = screen.getByRole('checkbox', { name: 'Escuelas rurales' });
    expect(checkbox).toBeDisabled();
    await user.hover(checkbox);
    expect(await screen.findByRole('tooltip', { name: 'no disponible en 3D' })).toBeInTheDocument();
  });
});
