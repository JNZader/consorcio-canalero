import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { TerrainLayerTogglesPanel } from '../../src/components/terrain/TerrainLayerTogglesPanel';

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
  it('does not claim 2D and 3D stay separate and delegates vector rows to LayerControlsPanel', () => {
    wrap(<TerrainLayerTogglesPanel {...baseProps} />);
    expect(screen.queryByText(/se mantienen por separado/i)).not.toBeInTheDocument();
    expect(screen.queryByTestId('terrain-3d-capas-vectoriales')).not.toBeInTheDocument();
  });
});
