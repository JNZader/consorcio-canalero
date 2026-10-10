import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { TerrainLayerTogglesPanel } from '../../src/components/terrain/TerrainLayerTogglesPanel';
import { UNSUPPORTED_3D_VECTOR_LAYERS } from '../../src/components/terrain/terrainLayerConfig';

function wrap(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

const baseProps = {
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
  intersectionsLength: 3,
};

describe('TerrainLayerTogglesPanel 3D-unsupported rows', () => {
  it('does not claim 2D and 3D stay separate', () => {
    wrap(<TerrainLayerTogglesPanel {...baseProps} />);
    expect(screen.queryByText(/se mantienen por separado/i)).not.toBeInTheDocument();
  });

  it('grays 2D-only layers with tooltip no disponible en 3D', async () => {
    const user = userEvent.setup();
    wrap(<TerrainLayerTogglesPanel {...baseProps} />);
    for (const layer of UNSUPPORTED_3D_VECTOR_LAYERS) {
      const checkbox = screen.getByRole('checkbox', { name: layer.label });
      expect(checkbox).toBeDisabled();
    }
    await user.hover(screen.getByRole('checkbox', { name: UNSUPPORTED_3D_VECTOR_LAYERS[0].label }));
    expect(await screen.findByRole('tooltip', { name: 'no disponible en 3D' })).toBeInTheDocument();
  });
});
