import type { Feature, FeatureCollection } from 'geojson';
import { describe, expect, it } from 'vitest';

import {
  buildActiveLegendItems,
  buildBasinFeatureById,
  buildDemLayerOptions,
  buildInitialDraftAssignments,
  buildSuggestedZoneSummaries,
  buildSuggestedZonesDisplay,
  buildVectorLayerItems,
  buildZoneDefinitionById,
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
  it('builds suggested zone display using reassigned basin names/colors', () => {
    const basins = polygonCollection([
      pointFeature('b1', { draft_zone_id: 'z1', nombre: 'Cuenca Norte' }),
    ]);

    const result = buildSuggestedZonesDisplay(basins, { b1: 'z2' }, { z2: 'Candil' });
    expect(result?.features[0]?.properties?.__zone_id).toBe('z2');
    expect(result?.features[0]?.properties?.__color).toBe('#2196F3');
  });

  it('builds initial draft assignments and zone definitions from suggested zones', () => {
    const suggestedZones = polygonCollection([
      pointFeature('feature-1', {
        draft_zone_id: 'z1',
        nombre: 'Zona Norte',
        family: 'A',
        __color: '#123456',
        member_basin_ids: ['b1', 'b2'],
      }),
    ]);

    expect(buildInitialDraftAssignments(suggestedZones)).toEqual({ b1: 'z1', b2: 'z1' });
    expect(buildZoneDefinitionById(suggestedZones)).toEqual({
      z1: { defaultName: 'Zona Norte', family: 'A', color: '#123456' },
    });
  });

  it('indexes basin features and computes suggested zone summaries', () => {
    const basins = polygonCollection([
      pointFeature('b1', { superficie_ha: 10 }),
      pointFeature('b2', { superficie_ha: 20 }),
    ]);

    const basinFeatureById = buildBasinFeatureById(basins);
    expect(Object.keys(basinFeatureById)).toEqual(['b1', 'b2']);

    expect(
      buildSuggestedZoneSummaries(
        { z1: { defaultName: 'Zona 1', family: null, color: '#111111' } },
        { b1: 'z1', b2: 'z1' },
        basinFeatureById,
      ),
    ).toEqual([{ id: 'z1', defaultName: 'Zona 1', family: null, basinCount: 2, superficieHa: 30 }]);
  });

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
    ).toEqual([
      { id: 'basins', label: 'Subcuencas' },
      { id: 'waterways', label: 'Hidrografía' },
      { id: 'roads', label: 'Red vial' },
      { id: 'soil', label: 'Suelos IDECOR' },
      { id: 'catastro', label: 'Catastro rural' },
      { id: 'puntos_conflicto', label: 'Puntos conflicto' },
    ]);

    expect(
      buildDemLayerOptions(
        [{ id: 'dem-1', tipo: 'slope', nombre: 'Pendiente cruda' }],
        { slope: 'Pendiente' },
      ),
    ).toEqual([{ value: 'dem-1', label: 'Pendiente' }]);
  });
});
