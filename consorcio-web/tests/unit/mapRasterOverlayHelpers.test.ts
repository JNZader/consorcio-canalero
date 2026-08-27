import type maplibregl from 'maplibre-gl';
import { describe, expect, it, vi } from 'vitest';

import {
  syncHazardRiskLayers,
  syncPrecipNormalLayer,
} from '../../src/components/map2d/mapRasterOverlayHelpers';
import type { GeoLayerInfo } from '../../src/hooks/useGeoLayers';

function createMap() {
  const sources = new Map<string, { tiles?: string[]; setTiles?: (tiles: string[]) => void }>();
  const layers = new Set<string>();
  return {
    getSource: vi.fn((id: string) => sources.get(id)),
    getLayer: vi.fn((id: string) => (layers.has(id) ? { id } : undefined)),
    addSource: vi.fn((id: string, source: { tiles: string[] }) => sources.set(id, source)),
    addLayer: vi.fn((layer: { id: string }) => layers.add(layer.id)),
    removeSource: vi.fn((id: string) => sources.delete(id)),
    removeLayer: vi.fn((id: string) => layers.delete(id)),
    setLayoutProperty: vi.fn(),
  } as unknown as maplibregl.Map;
}

const annualPrecipitation: GeoLayerInfo = {
  id: 'precip-annual',
  nombre: 'precip_normal_anual',
  tipo: 'precip_normal',
  fuente: 'gee',
  formato: 'geotiff',
  area_id: null,
  created_at: '2026-08-01T00:00:00Z',
  variante: 'relevado' as const,
  label: 'Precipitation normal',
  metadata_extra: { mes: 'anual' },
};

function riskLayerEntry(
  id: string,
  tipo: string,
  variante: GeoLayerInfo['variante']
): GeoLayerInfo {
  return { ...annualPrecipitation, id, tipo, variante, metadata_extra: undefined };
}

describe('hazard raster lifecycle', () => {
  it('creates the precipitation raster with its annual rescale range', () => {
    const map = createMap();

    syncPrecipNormalLayer(map, {
      isHazardActive: true,
      precipMonth: 'anual',
      allGeoLayers: [annualPrecipitation],
    });

    expect(map.addSource).toHaveBeenCalledWith(
      'map2d-precip-normal',
      expect.objectContaining({ tiles: [expect.stringContaining('rescale_max=1800')] })
    );
    expect(map.addLayer).toHaveBeenCalledWith(
      expect.objectContaining({ paint: { 'raster-opacity': 0.55 } }),
      'vector-layers-start'
    );
  });

  it('switches a mounted risk source without changing the DEM source', () => {
    const map = createMap();
    const riskLayer = {
      ...annualPrecipitation,
      id: 'flood-risk',
      tipo: 'flood_risk',
      metadata_extra: undefined,
    };

    syncHazardRiskLayers(map, {
      isHazardActive: true,
      activeRiskClasses: ['Bajo', 'Alto'],
      allGeoLayers: [riskLayer],
    });

    expect(map.addSource).toHaveBeenCalledWith(
      'map2d-flood-risk',
      expect.objectContaining({ tiles: [expect.stringContaining('hide_ranges=1%2C3')] })
    );
    expect(map.getSource).not.toHaveBeenCalledWith('map2d-dem-raster');
  });

  it('never mounts a non-operational variant as current risk when relevado is absent', () => {
    const map = createMap();
    const nonOperationalOnly: GeoLayerInfo[] = (['natural', 'escenario'] as const).flatMap(
      (variante) => [
        riskLayerEntry(`flood-${variante}`, 'flood_risk', variante),
        riskLayerEntry(`drainage-${variante}`, 'drainage_need', variante),
      ]
    );

    syncHazardRiskLayers(map, {
      isHazardActive: true,
      activeRiskClasses: ['Bajo', 'Alto'],
      allGeoLayers: nonOperationalOnly,
    });

    expect(map.addSource).not.toHaveBeenCalledWith('map2d-flood-risk', expect.anything());
    expect(map.addSource).not.toHaveBeenCalledWith('map2d-drainage-need', expect.anything());
  });

  it('selects the relevado variant when the catalog also exposes natural and escenario', () => {
    const map = createMap();
    const mixedCatalog: GeoLayerInfo[] = [
      riskLayerEntry('flood-natural', 'flood_risk', 'natural'),
      riskLayerEntry('flood-relevado', 'flood_risk', 'relevado'),
      riskLayerEntry('flood-escenario', 'flood_risk', 'escenario'),
    ];

    syncHazardRiskLayers(map, {
      isHazardActive: true,
      activeRiskClasses: ['Bajo', 'Alto'],
      allGeoLayers: mixedCatalog,
    });

    expect(map.addSource).toHaveBeenCalledWith(
      'map2d-flood-risk',
      expect.objectContaining({ tiles: [expect.stringContaining('flood-relevado')] })
    );
  });

  it('does not create a raster source when the matching catalog entry is absent', () => {
    const map = createMap();

    syncPrecipNormalLayer(map, {
      isHazardActive: true,
      precipMonth: '01',
      allGeoLayers: [],
    });

    expect(map.addSource).not.toHaveBeenCalled();
  });
});
