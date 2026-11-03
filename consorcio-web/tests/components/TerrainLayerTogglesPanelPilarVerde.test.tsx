import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { TerrainLayerTogglesPanel } from '../../src/components/terrain/TerrainLayerTogglesPanel';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

function makeBaseProps() {
  return {
    rasterLayers: [],
    selectedImageOption: null,
    activeRasterLayerId: undefined,
    onActiveRasterLayerChange: vi.fn(),
    overlayOpacity: 0.7,
    onOverlayOpacityChange: vi.fn(),
    vectorLayerVisibility: {
      pilar_verde_bpa_historico: false,
      canales_relevados: true,
    },
    onVectorLayerToggle: vi.fn(),
    onClose: vi.fn(),
    hasApprovedZones: false,
  };
}

describe('<TerrainLayerTogglesPanel /> — Pilar Verde & Canales delegated to LayerControlsPanel', () => {
  it('does not render duplicate Pilar Verde or Canales sections inside TerrainLayerTogglesPanel', () => {
    renderWithMantine(<TerrainLayerTogglesPanel {...makeBaseProps()} />);
    expect(screen.queryByText('Pilar Verde')).not.toBeInTheDocument();
    expect(screen.queryByText('Canales')).not.toBeInTheDocument();
  });
});
