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
    { id: 'roads', label: 'Red vial rural', category: LAYER_CATEGORY.TERRITORIO },
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
  it('shows a 3D Base note, hides raster analysis and ajustes', () => {
    wrap(
      <LayerControlsPanel
        {...baseProps}
        variant="3d"
        unsupportedLayerIds={['escuelas']}
      />,
    );
    expect(screen.getByTestId('layer-controls-capas')).toBeInTheDocument();
    expect(screen.getByText(/Zona Consorcio es el terreno 3D/)).toBeInTheDocument();
    expect(screen.queryByTestId('layer-controls-raster')).not.toBeInTheDocument();
    expect(screen.queryByTestId('layer-controls-ajustes')).not.toBeInTheDocument();
  });

  it('lists the 3D raster overlay in En el mapa (MAP-09)', () => {
    wrap(
      <LayerControlsPanel
        {...baseProps}
        variant="3d"
        demEnabled
        showDemOverlay
        activeDemLayerId="hand-1"
        demOptions={[{ value: 'hand-1', label: 'Altura sobre Drenaje (HAND)', tipo: 'hand' }]}
      />,
    );
    expect(screen.getByTestId('map-active-remove-__dem')).toBeInTheDocument();
    expect(screen.queryByText('Nada prendido')).not.toBeInTheDocument();
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
    const checkbox = screen.getByRole('checkbox', { name: 'Escuelas rurales' });
    expect(checkbox).toBeDisabled();
    await user.hover(checkbox);
    expect(await screen.findByRole('tooltip', { name: 'No disponible en 3D' })).toBeInTheDocument();
  });
});
