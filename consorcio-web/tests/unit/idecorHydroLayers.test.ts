import type { Map as MapLibreMap } from 'maplibre-gl';
import { describe, expect, it } from 'vitest';

import {
  IDECOR_HYDRO_LAYERS,
  syncIdecorHydroLayers,
} from '../../src/components/map2d/idecorHydroLayers';
import { getMartinTileUrl } from '../../src/hooks/useMartinLayers';

interface FakeLayer {
  id: string;
  type: string;
  source: string;
  'source-layer': string;
  paint: Record<string, unknown>;
  visibility: 'visible' | 'none';
}

function fakeMap() {
  const sources = new Map<string, { tiles: string[] }>();
  const layers = new Map<string, FakeLayer>();
  let sourceAdds = 0;
  const map = {
    getSource: (id: string) => sources.get(id),
    addSource: (id: string, spec: { tiles: string[] }) => {
      sourceAdds += 1;
      sources.set(id, spec);
    },
    getLayer: (id: string) => layers.get(id),
    addLayer: (layer: Omit<FakeLayer, 'visibility'>) => {
      layers.set(layer.id, { ...layer, visibility: 'visible' });
    },
    setLayoutProperty: (id: string, prop: string, value: string) => {
      const layer = layers.get(id);
      if (layer && prop === 'visibility') layer.visibility = value as 'visible' | 'none';
    },
  };
  return { map: map as unknown as MapLibreMap, sources, layers, sourceAdds: () => sourceAdds };
}

describe('syncIdecorHydroLayers', () => {
  it('lists the four IDECOR hydro overlays', () => {
    expect(IDECOR_HYDRO_LAYERS.map((layer) => layer.id)).toEqual([
      'idecor_consorcios',
      'idecor_cursos',
      'idecor_cuencas',
      'idecor_canales_riego',
    ]);
  });

  it('does nothing when the map stub has no style API', () => {
    expect(() => syncIdecorHydroLayers({} as MapLibreMap, { idecor_cursos: true })).not.toThrow();
    expect(() =>
      syncIdecorHydroLayers(
        { getSource: () => undefined, addSource: () => undefined } as unknown as MapLibreMap,
        {}
      )
    ).not.toThrow();
  });

  it('adds Martin sources and keeps every overlay hidden until its toggle is on', () => {
    const { map, sources, layers } = fakeMap();
    syncIdecorHydroLayers(map, {});

    for (const layer of IDECOR_HYDRO_LAYERS) {
      expect(sources.get(layer.id)?.tiles).toEqual([getMartinTileUrl(layer.table)]);
      expect(layers.get(`${layer.id}-line`)?.['source-layer']).toBe(layer.table);
      expect(layers.get(`${layer.id}-line`)?.visibility).toBe('none');
      if (layer.kind === 'fill') {
        expect(layers.get(`${layer.id}-fill`)?.visibility).toBe('none');
      } else {
        expect(layers.has(`${layer.id}-fill`)).toBe(false);
      }
    }
  });

  it('shows only the toggled overlay and does not add the source twice', () => {
    const { map, sources, layers, sourceAdds } = fakeMap();

    syncIdecorHydroLayers(map, { idecor_cuencas: true });
    syncIdecorHydroLayers(map, { idecor_cuencas: true });

    expect(sourceAdds()).toBe(IDECOR_HYDRO_LAYERS.length);
    expect(sources.size).toBe(IDECOR_HYDRO_LAYERS.length);
    expect(layers.get('idecor_cuencas-fill')?.visibility).toBe('visible');
    expect(layers.get('idecor_cuencas-line')?.visibility).toBe('visible');
    expect(layers.get('idecor_cursos-line')?.visibility).toBe('none');
  });
});
