import type { Map as MapLibreMap } from 'maplibre-gl';
import { describe, expect, it } from 'vitest';

import {
  IDECOR_HYDRO_LAYERS,
  syncIdecorHydroLayers,
} from '../../src/components/map2d/idecorHydroLayers';

interface FakeSource {
  type: string;
  data?: string;
  tiles?: string[];
}

interface FakeLayer {
  id: string;
  type: string;
  source: string;
  'source-layer'?: string;
  paint: Record<string, unknown>;
  visibility: 'visible' | 'none';
}

function fakeMap() {
  const sources = new Map<string, FakeSource>();
  const layers = new Map<string, FakeLayer>();
  let sourceAdds = 0;
  const map = {
    getSource: (id: string) => sources.get(id),
    addSource: (id: string, spec: FakeSource) => {
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

  it('lazy-mounts GeoJSON sources only when a layer is toggled on', () => {
    const { map, sources, layers, sourceAdds } = fakeMap();
    syncIdecorHydroLayers(map, {});

    // Nothing added while all toggles are off (saves 789 KB download)
    expect(sources.size).toBe(0);
    expect(layers.size).toBe(0);

    // Toggle one layer on
    syncIdecorHydroLayers(map, { idecor_cuencas: true });
    expect(sourceAdds()).toBe(1);
    expect(sources.get('idecor_cuencas')?.type).toBe('geojson');
    expect(sources.get('idecor_cuencas')?.data).toBe('/capas/idecor/cuencas.geojson');
    expect(layers.get('idecor_cuencas-fill')?.visibility).toBe('visible');
    expect(layers.get('idecor_cuencas-line')?.visibility).toBe('visible');

    // Toggle it off: stays in sources, becomes hidden
    syncIdecorHydroLayers(map, { idecor_cuencas: false });
    expect(sourceAdds()).toBe(1);
    expect(layers.get('idecor_cuencas-fill')?.visibility).toBe('none');
    expect(layers.get('idecor_cuencas-line')?.visibility).toBe('none');
  });

  it('shows only the toggled overlay and does not add the source twice', () => {
    const { map, sources, layers, sourceAdds } = fakeMap();

    syncIdecorHydroLayers(map, { idecor_cuencas: true });
    syncIdecorHydroLayers(map, { idecor_cuencas: true });

    expect(sourceAdds()).toBe(1);
    expect(sources.size).toBe(1);
    expect(layers.get('idecor_cuencas-fill')?.visibility).toBe('visible');
    expect(layers.get('idecor_cuencas-line')?.visibility).toBe('visible');
  });
});
