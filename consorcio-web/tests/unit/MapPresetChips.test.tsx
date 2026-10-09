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
});
