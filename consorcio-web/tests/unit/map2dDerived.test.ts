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
      approvedZones: polygonCollection([
        pointFeature('a1', { nombre: 'Cuenca A', __color: '#abcdef' }),
      ]),
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
      })
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
      buildDemLayerOptions([{ id: 'dem-1', tipo: 'slope', nombre: 'Pendiente cruda' }], {
        slope: 'Pendiente',
      })
    ).toEqual([{ value: 'dem-1', label: 'Pendiente' }]);
  });

  it('usa el label de la capa (con sufijo de variante), no el tipo', () => {
    // Las tres variantes de una capa comparten tipo pero traen label distinto.
    // Armar la etiqueta desde el tipo las mostraba IGUAL en el selector.
    const opciones = buildDemLayerOptions(
      [
        {
          id: 'nat',
          tipo: 'flow_acc',
          nombre: 'natural_flow_acc_z',
          label: 'Acumulacion de Flujo (natural)',
        },
        { id: 'rel', tipo: 'flow_acc', nombre: 'flow_acc_z', label: 'Acumulacion de Flujo' },
        {
          id: 'esc',
          tipo: 'flow_acc',
          nombre: 'escenario_flow_acc_z',
          label: 'Acumulacion de Flujo (escenario)',
        },
      ],
      { flow_acc: 'Acumulacion de Flujo' }
    );
    const labels = opciones.map((o) => o.label);
    // Las tres etiquetas tienen que ser distintas: es lo que hace elegible cada variante.
    expect(new Set(labels).size).toBe(3);
    expect(labels).toEqual([
      'Acumulacion de Flujo (natural)',
      'Acumulacion de Flujo',
      'Acumulacion de Flujo (escenario)',
    ]);
  });

  it('cae al label por tipo cuando la capa no trae label propio', () => {
    expect(
      buildDemLayerOptions([{ id: 'x', tipo: 'twi', nombre: 'twi_z' }], { twi: 'TWI' })
    ).toEqual([{ value: 'x', label: 'TWI' }]);
  });

  it('assigns every layer item a valid family category', () => {
    const validCategories = new Set<string>(Object.values(LAYER_CATEGORY));
    const items = buildVectorLayerItems({
      basins: polygonCollection([pointFeature('b1')]),
      approvedZonesCollection: polygonCollection([pointFeature('z1')]),
      roadsCollection: polygonCollection([pointFeature('r1')]),
      intersectionsLength: 1,
      showPilarVerde: true,
      showPilarAzul: true,
      showEscuelas: true,
    });

    expect(items.length).toBeGreaterThan(0);
    for (const item of items) {
      expect(validCategories.has(item.category)).toBe(true);
    }
  });

  // Subcuencas públicas a pedido del consorcio (2026-07-30). Antes el toggle
  // estaba gateado por `isAdmin`; ahora la única condición es tener datos.
  it('muestra subcuencas sin isAdmin, siempre que haya features', () => {
    const items = buildVectorLayerItems({
      basins: polygonCollection([pointFeature('b1')]),
      approvedZonesCollection: null,
      roadsCollection: null,
      intersectionsLength: 0,
    });

    expect(items.some((item) => item.id === 'basins')).toBe(true);
  });

  it('oculta subcuencas cuando la colección viene vacía o nula', () => {
    const base = {
      approvedZonesCollection: null,
      roadsCollection: null,
      intersectionsLength: 0,
    };

    expect(
      buildVectorLayerItems({ ...base, basins: polygonCollection([]) }).some(
        (item) => item.id === 'basins'
      )
    ).toBe(false);
    expect(
      buildVectorLayerItems({ ...base, basins: null }).some((item) => item.id === 'basins')
    ).toBe(false);
  });
});
