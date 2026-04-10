import type { FeatureCollection } from 'geojson';
import { renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { useMapDerivedState } from '../../src/components/map2d/useMapDerivedState';

function featureCollection(features: any[]): FeatureCollection {
  return { type: 'FeatureCollection', features };
}

describe('useMapDerivedState', () => {
  it('builds derived collections, zoning summaries and panel options', () => {
    const { result } = renderHook(() =>
      useMapDerivedState({
        capas: {
          zona: featureCollection([
            { type: 'Feature', geometry: { type: 'Point', coordinates: [-62.6, -32.6] }, properties: {} },
          ]),
        },
        caminos: featureCollection([
          { type: 'Feature', geometry: { type: 'LineString', coordinates: [] }, properties: { color: '#fff' } },
        ]),
        assets: [{ tipo: 'puente', longitud: -62.6, latitud: -32.6, nombre: 'Activo' }],
        publicLayers: [{ id: 'pub-1', data: featureCollection([]) }],
        soilMap: featureCollection([
          { type: 'Feature', geometry: { type: 'Point', coordinates: [-62.6, -32.6] }, properties: { cap: 'III' } },
        ]),
        basins: featureCollection([
          {
            type: 'Feature',
            geometry: { type: 'Point', coordinates: [-62.6, -32.6] },
            properties: { id: 'b1', nombre: 'Subcuenca 1', draft_zone_id: 'z1', superficie_ha: 12 },
          },
        ]),
        suggestedZones: featureCollection([
          {
            type: 'Feature',
            geometry: { type: 'Point', coordinates: [-62.6, -32.6] },
            properties: { draft_zone_id: 'z1', nombre: 'Zona 1', family: 'A', member_basin_ids: ['b1'] },
          },
        ]),
        waterways: [
          {
            nombre: 'Canales existentes',
            style: { color: '#0B3D91' },
            data: featureCollection([
              { type: 'Feature', geometry: { type: 'LineString', coordinates: [] }, properties: {} },
            ]),
          },
        ],
        allGeoLayers: [{ id: 'dem-1', tipo: 'slope', nombre: 'Pendiente' }],
        approvedZones: null,
        draftBasinAssignments: {},
        suggestedZoneNames: { z1: 'Zona Norte' },
        hiddenClasses: {},
        hiddenRanges: {},
        activeDemLayerId: 'dem-1',
        selectedDraftBasinId: 'b1',
        selectedImage: { sensor: 'Sentinel-2', target_date: '2026-04-01' },
        comparison: {
          left: { target_date: '2026-03-01' },
          right: { target_date: '2026-04-01' },
        },
        vectorVisibility: {
          approved_zones: false,
          basins: true,
          soil: true,
          waterways: true,
          infrastructure: true,
        },
        hasApprovedZones: false,
        intersectionsLength: 1,
      }),
    );

    expect(result.current.zonaCollection?.features).toHaveLength(1);
    expect(result.current.infrastructureCollection?.features).toHaveLength(1);
    expect(result.current.suggestedZoneSummaries[0]).toMatchObject({ id: 'z1', basinCount: 1 });
    expect(result.current.selectedDraftBasinName).toBe('Subcuenca 1');
    expect(result.current.selectedDraftBasinZoneId).toBe('z1');
    expect(result.current.hasSingleImage).toBe(true);
    expect(result.current.hasComparison).toBe(true);
    expect(result.current.vectorLayerItems.some((item) => item.id === 'public_layers')).toBe(true);
    expect(result.current.demLayerOptions).toEqual([{ value: 'dem-1', label: 'Pendiente' }]);
  });
});
