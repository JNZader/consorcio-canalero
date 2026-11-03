import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { TerrainLayerTogglesPanel } from '../../src/components/terrain/TerrainLayerTogglesPanel';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

const IDECOR_ATTRIBUTION = 'Datos: IDECor — Gobierno de Córdoba';

describe('<TerrainLayerTogglesPanel /> — IDECor attribution delegated to LayerControlsPanel', () => {
  it('does not duplicate the IDECor attribution inside TerrainLayerTogglesPanel', () => {
    renderWithMantine(
      <TerrainLayerTogglesPanel
        rasterLayers={[]}
        selectedImageOption={null}
        activeRasterLayerId={undefined}
        onActiveRasterLayerChange={vi.fn()}
        overlayOpacity={0.7}
        onOverlayOpacityChange={vi.fn()}
        vectorLayerVisibility={{ pilar_verde_bpa_historico: true }}
        onVectorLayerToggle={vi.fn()}
        onClose={vi.fn()}
        hasApprovedZones={false}
      />,
    );

    expect(screen.queryByText(IDECOR_ATTRIBUTION)).not.toBeInTheDocument();
  });
});
