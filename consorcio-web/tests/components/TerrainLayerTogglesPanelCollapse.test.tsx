/**
 * TerrainLayerTogglesPanelCollapse.test.tsx
 *
 * Collapsible body for the 3D toggles panel — when layers + opacity slider +
 * vector checkboxes start to crowd the viewport, the user can collapse the
 * whole body and keep only the title row visible.
 */

import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { TerrainLayerTogglesPanel } from '../../src/components/terrain/TerrainLayerTogglesPanel';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

const rasterLayers = [
  {
    id: 'dem-1',
    nombre: 'dem-1',
    tipo: 'dem_raw',
    fuente: 'dem_pipeline',
    formato: 'cog',
    area_id: null,
    created_at: '2026-01-01',
    variante: 'relevado' as const,
    label: 'Elevación (DEM)',
  },
  {
    id: 'drain-1',
    nombre: 'drain-1',
    tipo: 'drainage_need',
    fuente: 'dem_pipeline',
    formato: 'cog',
    area_id: null,
    created_at: '2026-01-01',
    variante: 'relevado' as const,
    label: 'Necesidad de Drenaje',
  },
];

const baseProps = {
  rasterLayers,
  selectedImageOption: null,
  activeRasterLayerId: undefined,
  onActiveRasterLayerChange: vi.fn(),
  overlayOpacity: 0.7,
  onOverlayOpacityChange: vi.fn(),
  vectorLayerVisibility: {} as Record<string, boolean>,
  onVectorLayerToggle: vi.fn(),
  onClose: vi.fn(),
  hasApprovedZones: false,
};

describe('<TerrainLayerTogglesPanel /> — collapsible body', () => {
  it('renders body content visible by default (expanded)', () => {
    renderWithMantine(<TerrainLayerTogglesPanel {...baseProps} />);

    expect(screen.getByText(/Capas 3D/i)).toBeInTheDocument();
    expect(screen.getByText(/Overlay raster activo/i)).toBeInTheDocument();
    expect(screen.getByText(/Capas vectoriales 3D/i)).toBeInTheDocument();
  });

  it('hides body sections when the header is clicked, keeps title visible', () => {
    renderWithMantine(<TerrainLayerTogglesPanel {...baseProps} />);

    const header = screen.getByTestId('terrain-3d-toggles-header');
    fireEvent.click(header);

    expect(screen.queryByText(/Overlay raster activo/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Capas vectoriales 3D/i)).not.toBeInTheDocument();
    // Title still visible.
    expect(screen.getByText(/Capas 3D/i)).toBeInTheDocument();
    expect(header).toHaveAttribute('aria-expanded', 'false');
  });

  it('re-shows body sections after a second click', () => {
    renderWithMantine(<TerrainLayerTogglesPanel {...baseProps} />);

    const header = screen.getByTestId('terrain-3d-toggles-header');
    fireEvent.click(header);
    fireEvent.click(header);

    expect(screen.getByText(/Overlay raster activo/i)).toBeInTheDocument();
    expect(screen.getByText(/Capas vectoriales 3D/i)).toBeInTheDocument();
    expect(header).toHaveAttribute('aria-expanded', 'true');
  });

  it('toggles via Enter key on the header', async () => {
    const user = userEvent.setup();

    renderWithMantine(<TerrainLayerTogglesPanel {...baseProps} />);

    const header = screen.getByTestId('terrain-3d-toggles-header');
    header.focus();
    expect(header).toHaveFocus();
    await user.keyboard('{Enter}');

    expect(screen.queryByText(/Capas vectoriales 3D/i)).not.toBeInTheDocument();
    expect(header).toHaveAttribute('aria-expanded', 'false');
  });

  it('lets the user clear DEM / drainage overlay instead of forcing one', async () => {
    const user = userEvent.setup();
    const onActiveRasterLayerChange = vi.fn();
    renderWithMantine(
      <TerrainLayerTogglesPanel
        {...baseProps}
        activeRasterLayerId="drain-1"
        onActiveRasterLayerChange={onActiveRasterLayerChange}
      />,
    );

    await user.click(screen.getByRole('combobox'));
    await user.click(await screen.findByRole('option', { name: /sin overlay/i }));
    expect(onActiveRasterLayerChange).toHaveBeenCalledWith(null);
  });
});
