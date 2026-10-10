import { describe, expect, it, vi } from 'vitest';

import {
  TERRAIN_HILLSHADE_LAYER_ID,
  TERRAIN_SKY,
  applyTerrainDepthCues,
  removeTerrainHillshade,
} from '../../src/components/terrain/terrainDepthCues';

function fakeMap(opts?: { hasHillshade?: boolean; hasPuntos?: boolean }) {
  const layers = new Set<string>();
  if (opts?.hasHillshade) layers.add(TERRAIN_HILLSHADE_LAYER_ID);
  if (opts?.hasPuntos) layers.add('puntos_conflicto-circle');
  return {
    getSource: (id: string) => (id === 'terrain-rgb' ? {} : undefined),
    getLayer: (id: string) => (layers.has(id) ? {} : undefined),
    addLayer: vi.fn((layer: { id: string }, before?: string) => {
      layers.add(layer.id);
      return before;
    }),
    removeLayer: vi.fn((id: string) => {
      layers.delete(id);
    }),
    setSky: vi.fn(),
  };
}

describe('terrainDepthCues', () => {
  it('adds a low hillshade under vectors and sets sky/fog', () => {
    const map = fakeMap({ hasPuntos: true });
    applyTerrainDepthCues(map as never);
    expect(map.addLayer).toHaveBeenCalledWith(
      expect.objectContaining({
        id: TERRAIN_HILLSHADE_LAYER_ID,
        type: 'hillshade',
        source: 'terrain-rgb',
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
  });
});
