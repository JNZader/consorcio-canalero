import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { TerrainViewer3DChrome } from '../../src/components/terrain/TerrainViewer3DChrome';
import { useMapWorkspaceDesktop } from '../../src/components/map2d/MapWorkspace';

vi.mock('../../src/components/map2d/MapWorkspace', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../src/components/map2d/MapWorkspace')>();
  return {
    ...actual,
    useMapWorkspaceDesktop: vi.fn(),
  };
});

function wrap(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

const defaultProps = {
  exaggeration: 1.5,
  onExaggerationChange: vi.fn(),
  minExaggeration: 0.5,
  maxExaggeration: 3,
  onNorth: vi.fn(),
  onNadir: vi.fn(),
  onOblique: vi.fn(),
  onLookWest: vi.fn(),
  onResetView: vi.fn(),
  height: 600,
  mapContainerRef: { current: null },
  rasterLayers: [],
  selectedImageOption: null,
  activeRasterType: undefined,
  activeRasterLayerId: undefined,
  onActiveRasterLayerChange: vi.fn(),
  overlayOpacity: 1,
  onOverlayOpacityChange: vi.fn(),
  terrainSmoothingEnabled: false,
  onTerrainSmoothingChange: vi.fn(),
  terrainSmoothingThreshold: 'low' as const,
  onTerrainSmoothingThresholdChange: vi.fn(),
  hiddenClasses: {},
  onClassToggle: vi.fn(),
  hiddenRanges: {},
  onRangeToggle: vi.fn(),
  vectorLayerVisibility: {},
  onVectorLayerToggle: vi.fn(),
  hasApprovedZones: false,
  ready: true,
  selectedImage: null,
};

describe('TerrainViewer3DChrome responsive layout', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders top header and desktop rotation hint on desktop', () => {
    vi.mocked(useMapWorkspaceDesktop).mockReturnValue(true);

    wrap(<TerrainViewer3DChrome {...defaultProps} />);

    expect(screen.getByText('Vista 3D del Terreno')).toBeInTheDocument();
    expect(screen.queryByTestId('terrain-3d-mobile-controls')).not.toBeInTheDocument();
    expect(screen.getByText('Ctrl+arrastre para rotar')).toBeInTheDocument();
  });

  it('hides top header, renders mobile controls in drawer, and shows touch gesture hint on mobile', () => {
    vi.mocked(useMapWorkspaceDesktop).mockReturnValue(false);

    wrap(<TerrainViewer3DChrome {...defaultProps} />);

    expect(screen.queryByText('Vista 3D del Terreno')).not.toBeInTheDocument();
    expect(screen.getByTestId('terrain-3d-mobile-controls')).toBeInTheDocument();
    expect(
      screen.getByText('Arrastrá con 2 dedos para rotar e inclinar')
    ).toBeInTheDocument();
  });
});
