import type { Feature, FeatureCollection } from 'geojson';
import { describe, expect, it } from 'vitest';

import {
  LAYER_CATEGORY,
  buildActiveLegendItems,
  buildDemLayerOptions,
  buildVectorLayerItems,
} from '../../src/components/map2d/map2dDerived';

function pointFeature(id: string, properties: Record<string, unknown> = {}): Feature {
  return {
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [-62.68, -32.62] },
    properties: { id, ...properties },
  };
}

function polygonCollection(features: Feature[]): FeatureCollection {
  return { type: 'FeatureCollection', features };
}

describe('map2dDerived', () => {
  it('builds legend items based on visible data layers', () => {
    const items = buildActiveLegendItems({
      zonaCollection: polygonCollection([pointFeature('z')]),
      vectorVisibility: {
        approved_zones: true,
        basins: true,
        soil: true,
        waterways: true,
      },
      hasApprovedZones: true,
      approvedZones: polygonCollection([pointFeature('a1', { nombre: 'Cuenca A', __color: '#abcdef' })]),
      basins: polygonCollection([pointFeature('b1')]),
      soilMap: polygonCollection([pointFeature('s1', { cap: 'III' })]),
    });

    expect(items.some((item) => item.label === 'Zona Consorcio')).toBe(true);
    expect(items.some((item) => item.label === 'Cuenca A')).toBe(true);
    expect(items.some((item) => item.label === 'Subcuencas operativas')).toBe(true);
    expect(items.some((item) => item.label === 'Clase III')).toBe(true);
  });

  it('builds visible vector layer items and DEM select options', () => {
    expect(
      buildVectorLayerItems({
        basins: polygonCollection([pointFeature('b1')]),
        approvedZonesCollection: null,
        roadsCollection: polygonCollection([pointFeature('r1')]),
        intersectionsLength: 1,
        isAdmin: true,
      }),
      // Labels are normalised with the 3D viewer (Red Vial / Suelos IDECOR
      // 1:50.000 / Catastro rural IDECOR) — the source is the naming source of
      // truth. Each item now also carries a `category` (change rediseno-ux-mapa).
    ).toEqual([
      { id: 'basins', label: 'Subcuencas', category: 'hidrografia' },
      { id: 'waterways', label: 'Hidrografía', category: 'hidrografia' },
      { id: 'roads', label: 'Red Vial', category: 'territorio' },
      { id: 'soil', label: 'Suelos IDECOR 1:50.000', category: 'territorio' },
      { id: 'catastro', label: 'Catastro rural IDECOR', category: 'territorio' },
      { id: 'puntos_conflicto', label: 'Puntos conflicto', category: 'analisis' },
    ]);

    expect(
      buildDemLayerOptions(
        [{ id: 'dem-1', tipo: 'slope', nombre: 'Pendiente cruda' }],
        { slope: 'Pendiente' },
      ),
    ).toEqual([{ value: 'dem-1', label: 'Pendiente' }]);
  });

  it('assigns every layer item a valid family category', () => {
    const validCategories = new Set<string>(Object.values(LAYER_CATEGORY));
    const items = buildVectorLayerItems({
      basins: polygonCollection([pointFeature('b1')]),
      approvedZonesCollection: polygonCollection([pointFeature('z1')]),
      roadsCollection: polygonCollection([pointFeature('r1')]),
      intersectionsLength: 1,
      isAdmin: true,
      showPilarVerde: true,
      showPilarAzul: true,
      showEscuelas: true,
    });

    expect(items.length).toBeGreaterThan(0);
    for (const item of items) {
      expect(validCategories.has(item.category)).toBe(true);
    }
  });
});
