import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('zustand/middleware', async () => {
  const actual = await vi.importActual<typeof import('zustand/middleware')>('zustand/middleware');
  return {
    ...actual,
    persist: (fn: unknown) => fn,
  };
});

import { useMapLayerSyncStore } from '../../src/stores/mapLayerSyncStore';

describe('mapLayerSyncStore applyPreset', () => {
  beforeEach(() => {
    useMapLayerSyncStore.setState((state) => ({
      map2d: {
        ...state.map2d,
        visibleVectors: {
          ...state.map2d.visibleVectors,
          roads: true,
          catastro: true,
          canal_relevado_foo: true,
        },
      },
      presetByView: { map2d: null, map3d: null },
    }));
  });

  it('turns catalog layers to the agua set and keeps per-canal keys', () => {
    useMapLayerSyncStore.getState().applyPreset('map2d', 'agua');
    const vv = useMapLayerSyncStore.getState().map2d.visibleVectors;
    expect(vv.waterways).toBe(true);
    expect(vv.canales_relevados).toBe(true);
    expect(vv.approved_zones).toBe(true);
    expect(vv.roads).toBe(false);
    expect(vv.catastro).toBe(false);
    expect(vv.canal_relevado_foo).toBe(true);
    expect(useMapLayerSyncStore.getState().presetByView.map2d).toBe('agua');
  });

  it('hides the catalog and restores first-load defaults', () => {
    useMapLayerSyncStore.getState().applyPreset('map2d', 'agua');
    useMapLayerSyncStore.getState().hideAllCatalogLayers('map2d');
    expect(useMapLayerSyncStore.getState().map2d.visibleVectors.waterways).toBe(false);
    expect(useMapLayerSyncStore.getState().map2d.visibleVectors.canal_relevado_foo).toBe(true);
    useMapLayerSyncStore.getState().restoreCatalogDefaults('map2d');
    expect(useMapLayerSyncStore.getState().map2d.visibleVectors.roads).toBe(true);
    expect(useMapLayerSyncStore.getState().map2d.visibleVectors.waterways).toBe(true);
    expect(useMapLayerSyncStore.getState().map2d.visibleVectors.catastro).toBe(false);
    expect(useMapLayerSyncStore.getState().map2d.visibleVectors.canales_relevados).toBe(true);
    expect(useMapLayerSyncStore.getState().presetByView.map2d).toBeNull();
  });

  it('marks Personalizado after a manual toggle', () => {
    useMapLayerSyncStore.getState().applyPreset('map2d', 'caminos');
    useMapLayerSyncStore.getState().setVectorVisibility('map2d', 'catastro', true);
    expect(useMapLayerSyncStore.getState().presetByView.map2d).toBe('custom');
    expect(useMapLayerSyncStore.getState().map2d.visibleVectors.roads).toBe(true);
    expect(useMapLayerSyncStore.getState().map2d.visibleVectors.catastro).toBe(true);
  });
});
