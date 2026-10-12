import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { LayerControlsPanel } from '../../src/components/map2d/LayerControlsPanel';

vi.mock('zustand/middleware', async () => {
  const actual = await vi.importActual<typeof import('zustand/middleware')>('zustand/middleware');
  return { ...actual, persist: (fn: unknown) => fn };
});

const baseProps = {
  baseLayer: 'osm' as const,
  onBaseLayerChange: () => {},
  layerItems: [],
  vectorVisibility: {} as Record<string, boolean>,
  onLayerVisibilityChange: () => {},
  showIGNOverlay: false,
  onShowIGNOverlayChange: () => {},
  showHillshade: false,
  onShowHillshadeChange: () => {},
  hillshadeAvailable: false,
  demEnabled: true,
  showDemOverlay: false,
  onShowDemOverlayChange: () => {},
  activeDemLayerId: null as string | null,
  onActiveDemLayerIdChange: () => {},
  demOptions: [
    { value: 'dem-1', label: 'Elevación' },
    { value: 'slope-1', label: 'Pendiente' },
  ],
};

describe('LayerControlsPanel raster switch (A11Y-03)', () => {
  it('keeps Mostrar raster outside the accordion header button', async () => {
    render(
      <MantineProvider env="test">
        <LayerControlsPanel {...baseProps} />
      </MantineProvider>,
    );
    const header = screen.getByRole('button', { name: /Análisis raster/i });
    fireEvent.click(header);
    const rasterLabel = await waitFor(() => screen.getByText('Mostrar raster'));
    expect(header.contains(rasterLabel)).toBe(false);
  });

  it('enables the overlay from the sibling switch', async () => {
    const onShowDemOverlayChange = vi.fn();
    const onActiveDemLayerIdChange = vi.fn();
    render(
      <MantineProvider env="test">
        <LayerControlsPanel
          {...baseProps}
          onShowDemOverlayChange={onShowDemOverlayChange}
          onActiveDemLayerIdChange={onActiveDemLayerIdChange}
        />
      </MantineProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: /Análisis raster/i }));
    const rasterLabel = await waitFor(() => screen.getByText('Mostrar raster'));
    fireEvent.click(rasterLabel);
    expect(onShowDemOverlayChange).toHaveBeenCalledWith(true);
    expect(onActiveDemLayerIdChange).toHaveBeenCalledWith('dem-1');
  });
});
