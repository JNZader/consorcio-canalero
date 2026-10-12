import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { LayerControlsPanel } from '../../src/components/map2d/LayerControlsPanel';

vi.mock('zustand/middleware', async () => {
  const actual = await vi.importActual<typeof import('zustand/middleware')>('zustand/middleware');
  return { ...actual, persist: (fn: unknown) => fn };
});

describe('En el mapa satellite row (UX-02)', () => {
  it('lists the published image and can hide it without touching vectors', () => {
    const onHideSatellite = vi.fn();
    render(
      <MantineProvider env="test">
        <LayerControlsPanel
          baseLayer="osm"
          onBaseLayerChange={() => {}}
          layerItems={[]}
          vectorVisibility={{}}
          onLayerVisibilityChange={() => {}}
          showIGNOverlay={false}
          onShowIGNOverlayChange={() => {}}
          demEnabled={false}
          showDemOverlay={false}
          onShowDemOverlayChange={() => {}}
          activeDemLayerId={null}
          onActiveDemLayerIdChange={() => {}}
          demOptions={[]}
          satelliteLayer={{ label: 'Imagen Sentinel-2 · 2025-09-05' }}
          onHideSatellite={onHideSatellite}
        />
      </MantineProvider>,
    );
    expect(screen.getByText('Imagen Sentinel-2 · 2025-09-05')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('map-active-remove-__satellite'));
    expect(onHideSatellite).toHaveBeenCalledTimes(1);
  });
});
