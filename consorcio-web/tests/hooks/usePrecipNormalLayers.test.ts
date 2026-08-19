import { describe, expect, it } from 'vitest';

import {
  buildPrecipNormalCatalogEndpoint,
  dedupePrecipNormalLayers,
  findPrecipNormalLayer,
  selectDemLayers,
} from '../../src/hooks/useGeoLayers';

function layer(period: unknown, createdAt: string, id = String(period)) {
  return {
    id,
    nombre: id,
    tipo: 'precip_normal',
    fuente: 'gee',
    formato: 'geotiff',
    area_id: null,
    created_at: createdAt,
    variante: 'relevado' as const,
    label: id,
    metadata_extra: { mes: period },
  };
}

describe('precipitation catalog contract', () => {
  it('uses the GEE precip-normal source for public and authenticated catalogs', () => {
    expect(buildPrecipNormalCatalogEndpoint(null)).toContain(
      '/layers/public?limit=100&tipo=precip_normal&fuente=gee'
    );
    expect(buildPrecipNormalCatalogEndpoint('token')).toContain(
      '/layers?limit=100&tipo=precip_normal&fuente=gee'
    );
  });

  it('keeps precipitation out of the legacy DEM selector', () => {
    const dem = { ...layer('anual', '2026-01-01', 'dem'), tipo: 'dem_raw', fuente: 'dem_pipeline' };
    expect(selectDemLayers([dem, layer('anual', '2026-01-01')]).map((item) => item.id)).toEqual(['dem']);
  });

  it('keeps twelve normalized months plus annual after regeneration deduplication', () => {
    const periods = [...Array.from({ length: 12 }, (_, index) => index + 1), 'anual'];
    const layers = periods.flatMap((period) => [
      layer(period, '2026-01-01', `old-${period}`),
      layer(String(period), '2026-02-01', `new-${period}`),
    ]);

    const deduped = dedupePrecipNormalLayers(layers);

    expect(deduped).toHaveLength(13);
    expect(deduped.map((item) => item.id)).toEqual([
      'new-1', 'new-2', 'new-3', 'new-4', 'new-5', 'new-6',
      'new-7', 'new-8', 'new-9', 'new-10', 'new-11', 'new-12', 'new-anual',
    ]);
  });

  it('looks up normalized numeric months and annual', () => {
    const layers = dedupePrecipNormalLayers([layer('01', '2026-01-01'), layer('anual', '2026-01-01')]);

    expect(findPrecipNormalLayer(layers, 1)?.metadata_extra?.mes).toBe('01');
    expect(findPrecipNormalLayer(layers, 'ANUAL')?.id).toBe('anual');
  });
});
