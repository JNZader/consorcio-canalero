import { describe, expect, it, vi } from 'vitest';

import {
  TERRAIN_HILLSHADE_LAYER_ID,
  TERRAIN_SKY,
  applyTerrainDepthCues,
  removeTerrainHillshade,
} from '../../src/components/terrain/terrainDepthCues';

function fakeMap(opts?: { hasHillshade?: boolean; hasPuntos?: boolean }) {
  const layers = new Set<string>();
  const sources = new Map<string, object>([
    ['terrain-rgb', { tiles: ['https://dem.test/{z}/{x}/{y}.png'], tileSize: 256 }],
  ]);
  if (opts?.hasHillshade) {
    layers.add(TERRAIN_HILLSHADE_LAYER_ID);
    sources.set('terrain-hillshade-dem', { tiles: ['https://dem.test/{z}/{x}/{y}.png'] });
  }
  if (opts?.hasPuntos) layers.add('puntos_conflicto-circle');
  return {
    getSource: (id: string) => sources.get(id),
    getLayer: (id: string) => (layers.has(id) ? {} : undefined),
    addSource: vi.fn((id: string, spec: object) => {
      sources.set(id, spec);
    }),
    addLayer: vi.fn((layer: { id: string }, before?: string) => {
      layers.add(layer.id);
      return before;
    }),
    removeLayer: vi.fn((id: string) => {
      layers.delete(id);
    }),
    removeSource: vi.fn((id: string) => {
      sources.delete(id);
    }),
    setSky: vi.fn(),
  };
}

describe('terrainDepthCues', () => {
  it('adds a low hillshade under vectors and sets sky/fog', () => {
    const map = fakeMap({ hasPuntos: true });
    applyTerrainDepthCues(map as never);
    expect(map.addSource).toHaveBeenCalledWith(
      'terrain-hillshade-dem',
      expect.objectContaining({ type: 'raster-dem' }),
    );
    expect(map.addLayer).toHaveBeenCalledWith(
      expect.objectContaining({
        id: TERRAIN_HILLSHADE_LAYER_ID,
        type: 'hillshade',
        source: 'terrain-hillshade-dem',
      }),
      'puntos_conflicto-circle',
    );
    expect(map.setSky).toHaveBeenCalledWith(TERRAIN_SKY);
  });

  it('does not duplicate hillshade', () => {
    const map = fakeMap({ hasHillshade: true });
    applyTerrainDepthCues(map as never);
    expect(map.addLayer).not.toHaveBeenCalled();
    expect(map.setSky).toHaveBeenCalled();
  });

  it('removes hillshade before a terrain-rgb rebuild', () => {
    const map = fakeMap({ hasHillshade: true });
    removeTerrainHillshade(map as never);
    expect(map.removeLayer).toHaveBeenCalledWith(TERRAIN_HILLSHADE_LAYER_ID);
    expect(map.removeSource).toHaveBeenCalledWith('terrain-hillshade-dem');
  });
});
