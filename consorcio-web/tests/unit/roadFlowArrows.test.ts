import { describe, expect, it } from 'vitest';

import {
  alongRoadAzimuth,
  buildConduccionArrowCollection,
  pickArrowCollection,
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

describe('buildConduccionArrowCollection', () => {
  it('emits one POINT per conduccion, never a 40 m line', () => {
    const arrows = buildConduccionArrowCollection(crossings);
    expect(arrows.features).toHaveLength(1);
    expect(arrows.features[0].geometry.type).toBe('Point');
    expect(arrows.features[0].properties.along_azimuth_deg).toBeCloseTo(90);
    expect(arrows.features[0].properties.tramo_ref).toBe('t1');
  });
});

describe('pickArrowCollection', () => {
  it('prefers the dense flechas payload when the run stored it', () => {
    const flechas = {
      type: 'FeatureCollection' as const,
      features: [
        {
          type: 'Feature' as const,
          geometry: { type: 'Point' as const, coordinates: [-62, -32] },
          properties: { id: 'x', tramo_ref: 't9', along_azimuth_deg: 12 },
        },
      ],
    };
    const picked = pickArrowCollection(flechas, crossings);
    expect(picked.features).toHaveLength(1);
    expect(picked.features[0].properties.tramo_ref).toBe('t9');
  });

  it('falls back to sparse conduccion points when flechas is empty', () => {
    const picked = pickArrowCollection({ type: 'FeatureCollection', features: [] }, crossings);
    expect(picked.features).toHaveLength(1);
    expect(picked.features[0].properties.tramo_ref).toBe('t1');
  });
});
