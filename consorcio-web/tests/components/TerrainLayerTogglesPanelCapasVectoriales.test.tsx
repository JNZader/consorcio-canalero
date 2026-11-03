import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { TerrainLayerTogglesPanel } from '../../src/components/terrain/TerrainLayerTogglesPanel';

function renderWithMantine(ui: ReactNode) {
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

describe('<TerrainLayerTogglesPanel /> — vector sections delegated to LayerControlsPanel', () => {
  it('omits the dead "Capas vectoriales 3D" section', () => {
    renderWithMantine(<TerrainLayerTogglesPanel {...baseProps} />);
    expect(screen.queryByTestId('terrain-3d-capas-vectoriales')).not.toBeInTheDocument();
    expect(screen.queryByText(/Capas vectoriales 3D/i)).not.toBeInTheDocument();
  });

  it('hides the inline DEM opacity slider when showOpacitySlider is false', () => {
    renderWithMantine(<TerrainLayerTogglesPanel {...baseProps} showOpacitySlider={false} />);
    expect(screen.queryByText(/Opacidad DEM/i)).not.toBeInTheDocument();
  });
});
