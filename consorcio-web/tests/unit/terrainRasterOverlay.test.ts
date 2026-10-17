import { describe, expect, it } from 'vitest';

import type { GeoLayerInfo } from '../../src/hooks/useGeoLayers';
import {
  nextAutofillTerrainRasterId,
  pickActiveTerrainRasterLayer,
  resolveDefaultTerrainRasterId,
} from '../../src/components/terrain/terrainLayerConfig';

function layer(id: string, tipo: string): GeoLayerInfo {
  return {
    id,
    nombre: id,
    tipo,
    fuente: 'dem_pipeline',
    formato: 'cog',
    area_id: null,
    created_at: '2026-01-01',
    variante: 'relevado',
    label: tipo,
  };
}

const dem = layer('dem-1', 'dem_raw');
const drainage = layer('drain-1', 'drainage_need');
const layers = [dem, drainage];

describe('pickActiveTerrainRasterLayer', () => {
  it('returns null when the overlay is cleared — no DEM / drainage fallback', () => {
    expect(pickActiveTerrainRasterLayer(null, layers)).toBeUndefined();
  });

  it('keeps the selected raster when an id is set', () => {
    expect(pickActiveTerrainRasterLayer('drain-1', layers)?.id).toBe('drain-1');
  });
});

describe('nextAutofillTerrainRasterId', () => {
  it('does not put DEM or drainage back after the user clears the overlay', () => {
    expect(
      nextAutofillTerrainRasterId({
        userPicked: true,
        activeRasterLayerId: null,
        selectedImage: false,
        selectedImageLayerId: '__selected_sentinel_image__',
        fallbackLayerId: 'dem-1',
      }),
    ).toBe('keep');
  });

  it('still defaults to Sentinel before the user picks anything', () => {
    expect(
      nextAutofillTerrainRasterId({
        userPicked: false,
        activeRasterLayerId: 'dem-1',
        selectedImage: true,
        selectedImageLayerId: '__selected_sentinel_image__',
        fallbackLayerId: 'dem-1',
      }),
    ).toBe('__selected_sentinel_image__');
  });
});

describe('resolveDefaultTerrainRasterId', () => {
  it('prioritizes textureLayerId when provided', () => {
    expect(
      resolveDefaultTerrainRasterId({
        rasterLayers: layers,
        textureLayerId: 'custom-texture',
        demLayerId: 'dem-1',
      })
    ).toBe('custom-texture');
  });

  it('prioritizes demLayerId when textureLayerId is absent', () => {
    expect(
      resolveDefaultTerrainRasterId({
        rasterLayers: layers,
        demLayerId: 'custom-dem',
      })
    ).toBe('custom-dem');
  });

  it('prioritizes dem_raw layer even when pipeline layers like drainage_need come first in the array', () => {
    // Array where drainage_need is first (e.g. backend ordered by created_at DESC)
    const reversedLayers = [drainage, dem];
    expect(
      resolveDefaultTerrainRasterId({
        rasterLayers: reversedLayers,
      })
    ).toBe('dem-1');
  });

  it('falls back to the first available layer if dem_raw is not present', () => {
    const onlyDrainage = [drainage];
    expect(
      resolveDefaultTerrainRasterId({
        rasterLayers: onlyDrainage,
      })
    ).toBe('drain-1');
  });

  it('returns null if rasterLayers is empty and no explicit id was given', () => {
    expect(
      resolveDefaultTerrainRasterId({
        rasterLayers: [],
      })
    ).toBeNull();
  });
});
