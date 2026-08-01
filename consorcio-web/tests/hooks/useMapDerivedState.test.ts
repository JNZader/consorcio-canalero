import type { FeatureCollection } from 'geojson';
import { renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { LAYER_LEGEND_CONFIG } from '../../src/config/rasterLegend';
import { useMapDerivedState } from '../../src/components/map2d/useMapDerivedState';

function featureCollection(features: any[]): FeatureCollection {
  return { type: 'FeatureCollection', features };
}

describe('useMapDerivedState', () => {
  it('builds derived collections and panel options', () => {
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
        hiddenClasses: {},
        hiddenRanges: {},
        activeDemLayerId: 'dem-1',
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
        },
        hasApprovedZones: false,
        intersectionsLength: 1,
      }),
    );

    expect(result.current.zonaCollection?.features).toHaveLength(1);
    expect(result.current.hasSingleImage).toBe(true);
    expect(result.current.hasComparison).toBe(true);
    expect(result.current.demLayerOptions).toEqual([{ value: 'dem-1', label: 'Pendiente' }]);
  });

  it('exposes flood_risk/drainage_need composites as raster dropdown options with a resolvable legend', () => {
    const { result } = renderHook(() =>
      useMapDerivedState({
        capas: {},
        caminos: null,
        soilMap: null,
        basins: null,
        waterways: [],
        allGeoLayers: [
          { id: 'dem-1', tipo: 'dem_raw', nombre: 'Elevacion (DEM)' },
          { id: 'flood-1', tipo: 'flood_risk', nombre: 'flood_risk_area' },
          { id: 'drain-1', tipo: 'drainage_need', nombre: 'drainage_need_area' },
        ],
        approvedZones: null,
        hiddenClasses: {},
        hiddenRanges: {},
        activeDemLayerId: null,
        selectedImage: null,
        comparison: null,
        vectorVisibility: {},
        hasApprovedZones: false,
        intersectionsLength: 0,
      })
    );

    const options = result.current.demLayerOptions;
    // Composites are no longer excluded — they surface as selectable options.
    expect(options).toEqual([
      { value: 'dem-1', label: 'Elevacion (DEM)' },
      { value: 'flood-1', label: 'Riesgo de Inundacion' },
      { value: 'drain-1', label: 'Necesidad de Drenaje' },
    ]);
    // Their legend config resolves so RasterLegend renders once selected.
    expect(LAYER_LEGEND_CONFIG.flood_risk).toBeDefined();
    expect(LAYER_LEGEND_CONFIG.drainage_need).toBeDefined();
  });
});
