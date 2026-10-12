import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('zustand/middleware', async () => {
  const actual = await vi.importActual<typeof import('zustand/middleware')>('zustand/middleware');
  return {
    ...actual,
    persist: (fn: unknown) => fn,
  };
});

vi.mock('../../src/lib/notifications', () => ({
  showInfo: vi.fn(),
}));

import { MapPresetChips } from '../../src/components/map2d/MapPresetChips';
import { useMapLayerSyncStore } from '../../src/stores/mapLayerSyncStore';

describe('MapPresetChips', () => {
  beforeEach(() => {
    useMapLayerSyncStore.setState({
      presetByView: { map2d: null, map3d: null },
    });
  });

  it('applies the agua preset from the chip', async () => {
    const user = userEvent.setup();
    render(
      <MantineProvider env="test">
        <MapPresetChips />
      </MantineProvider>
    );
    await user.click(screen.getByTestId('map-preset-agua'));
    expect(useMapLayerSyncStore.getState().presetByView.map2d).toBe('agua');
    expect(useMapLayerSyncStore.getState().map2d.visibleVectors.waterways).toBe(true);
    expect(useMapLayerSyncStore.getState().map2d.visibleVectors.roads).toBe(false);
  });

  it('titles the group Vistas rápidas and can undo the last vista', async () => {
    const user = userEvent.setup();
    useMapLayerSyncStore.setState((state) => ({
      map2d: {
        ...state.map2d,
        visibleVectors: { ...state.map2d.visibleVectors, roads: true, waterways: false },
      },
    }));
    render(
      <MantineProvider env="test">
        <MapPresetChips />
      </MantineProvider>
    );
    expect(screen.getByText('Vistas rápidas')).toBeInTheDocument();
    await user.click(screen.getByTestId('map-preset-agua'));
    expect(useMapLayerSyncStore.getState().map2d.visibleVectors.roads).toBe(false);
    await user.click(screen.getByTestId('map-preset-undo'));
    expect(useMapLayerSyncStore.getState().map2d.visibleVectors.roads).toBe(true);
    expect(useMapLayerSyncStore.getState().catalogUndoByView.map2d).toBeNull();
  });
});
