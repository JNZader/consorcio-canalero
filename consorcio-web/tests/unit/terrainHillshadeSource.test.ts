import { describe, expect, it } from 'vitest';

import {
  TERRAIN_HILLSHADE_SOURCE_ID,
  buildHillshadeDemSource,
} from '../../src/components/terrain/terrainHillshadeSource';

describe('terrainHillshadeSource 3D-07', () => {
  it('clones raster-dem tiles off terrain-rgb', () => {
    expect(TERRAIN_HILLSHADE_SOURCE_ID).toBe('terrain-hillshade-dem');
    const spec = buildHillshadeDemSource({
      type: 'raster-dem',
      tiles: ['https://tiles.example/glo30/{z}/{x}/{y}.png'],
      tileSize: 512,
      maxzoom: 12,
    });
    expect(spec).toEqual({
      type: 'raster-dem',
      tiles: ['https://tiles.example/glo30/{z}/{x}/{y}.png'],
      tileSize: 512,
      maxzoom: 12,
      minzoom: undefined,
    });
    spec?.tiles.push('mutated');
    const again = buildHillshadeDemSource({
      tiles: ['https://tiles.example/glo30/{z}/{x}/{y}.png'],
    });
    expect(again?.tiles).toEqual(['https://tiles.example/glo30/{z}/{x}/{y}.png']);
  });

  it('accepts a single url when tiles are empty', () => {
    expect(buildHillshadeDemSource({ url: 'https://dem.example/{z}/{x}/{y}.png' })?.tiles).toEqual([
      'https://dem.example/{z}/{x}/{y}.png',
    ]);
  });

  it('returns null without DEM tiles', () => {
    expect(buildHillshadeDemSource(undefined)).toBeNull();
    expect(buildHillshadeDemSource({})).toBeNull();
    expect(buildHillshadeDemSource({ tiles: [] })).toBeNull();
  });
});
