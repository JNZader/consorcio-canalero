import { describe, expect, it } from 'vitest';

import {
  alongRoadAzimuth,
  buildConduccionArrowCollection,
  destinationPoint,
} from '../../src/components/map2d/roadFlowArrows';
import type { RoadFlowCrossingCollection } from '../../src/lib/api/roadFlow';

describe('alongRoadAzimuth', () => {
  it('keeps the road bearing when flow agrees with digitization', () => {
    expect(alongRoadAzimuth(90, 90)).toBeCloseTo(90);
  });

  it('reverses the road bearing when flow is anti-parallel', () => {
    expect(alongRoadAzimuth(270, 90)).toBeCloseTo(270);
  });
});

describe('destinationPoint', () => {
  it('moves due east from the equator by the requested metres', () => {
    const [lon, lat] = destinationPoint(0, 0, 90, 40);
    expect(lat).toBeCloseTo(0, 5);
    expect(lon).toBeGreaterThan(0);
    expect(lon).toBeCloseTo(40 / 111_320, 3);
  });
});

describe('buildConduccionArrowCollection', () => {
  const crossings: RoadFlowCrossingCollection = {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [-62.5, -32.5] },
        properties: {
          id: 'd1',
          tipo: 'conduccion',
          tramo_ref: 't1',
          canal_ref: 'c1',
          direccion_flujo_deg: 90,
          rumbo_camino_deg: 90,
          lado_cruce: 'izq_a_der',
          area_aporte_ha: 12,
          orden_ranking: null,
          confianza: null,
          nota: null,
        },
      },
      {
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [-62.4, -32.4] },
        properties: {
          id: 'f1',
          tipo: 'flujo_natural',
          tramo_ref: 't2',
          canal_ref: null,
          direccion_flujo_deg: 0,
          rumbo_camino_deg: 90,
          lado_cruce: 'izq_a_der',
          area_aporte_ha: 99,
          orden_ranking: 1,
          confianza: 'alta',
          nota: null,
        },
      },
    ],
  };

  it('emits a shaft and a tip only for conduccion points', () => {
    const arrows = buildConduccionArrowCollection(crossings);
    expect(arrows.features).toHaveLength(2);
    const types = arrows.features.map((f) => f.geometry.type);
    expect(types).toContain('LineString');
    expect(types).toContain('Point');
    expect(arrows.features.every((f) => f.properties.tipo === 'conduccion')).toBe(true);
    expect(arrows.features.every((f) => f.properties.tramo_ref === 't1')).toBe(true);
  });
});
