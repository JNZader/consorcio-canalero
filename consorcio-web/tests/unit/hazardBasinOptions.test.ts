import type { Feature, FeatureCollection, Polygon } from 'geojson';
import { describe, expect, it } from 'vitest';

import { buildHazardBasinOptions } from '../../src/components/map2d/hazardBasinOptions';

const BASIN_ID = 'b1a2c3d4-1111-4222-8333-444455556666';

const BASIN_GEOMETRY: Polygon = {
  type: 'Polygon',
  coordinates: [
    [
      [-62.75, -32.66],
      [-62.35, -32.66],
      [-62.35, -32.44],
      [-62.75, -32.44],
      [-62.75, -32.66],
    ],
  ],
};

function basinFeature(properties: Record<string, unknown>): Feature {
  return { type: 'Feature', properties, geometry: BASIN_GEOMETRY };
}

function collection(...features: Feature[]): FeatureCollection {
  return { type: 'FeatureCollection', features };
}

describe('buildHazardBasinOptions', () => {
  it('builds options from the real API shape: properties.id + nombre + geometry', () => {
    const basins = collection(
      basinFeature({ id: BASIN_ID, nombre: 'Cuenca Alta', cuenca: 'Alta', superficie_ha: 1234.5 })
    );

    expect(buildHazardBasinOptions(basins)).toEqual([
      { id: BASIN_ID, label: 'Cuenca Alta', geometry: BASIN_GEOMETRY },
    ]);
  });

  it('drops features without a non-empty string id', () => {
    const basins = collection(
      basinFeature({ nombre: 'Sin id' }),
      basinFeature({ id: '', nombre: 'Id vacío' }),
      basinFeature({ id: 42, nombre: 'Id numérico' }),
      basinFeature({ id: BASIN_ID })
    );

    expect(buildHazardBasinOptions(basins).map((option) => option.id)).toEqual([BASIN_ID]);
  });

  it('falls back to "Cuenca <id>" when nombre is missing or blank', () => {
    expect(buildHazardBasinOptions(collection(basinFeature({ id: BASIN_ID })))[0]?.label).toBe(
      `Cuenca ${BASIN_ID}`
    );
  });

  it('returns no options for null, undefined, or empty collections', () => {
    expect(buildHazardBasinOptions(null)).toEqual([]);
    expect(buildHazardBasinOptions(undefined)).toEqual([]);
    expect(buildHazardBasinOptions(collection())).toEqual([]);
  });
});
