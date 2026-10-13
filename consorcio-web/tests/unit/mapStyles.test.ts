import { describe, expect, it } from 'vitest';

import {
  ANALYSIS_LEGEND_ITEMS,
  DEFAULT_LEGEND_ITEMS,
  MAP_LAYER_COLORS,
  TILE_LAYERS,
  getLayerStyle,
} from '../../src/constants/mapStyles';

describe('mapStyles', () => {
  it('returns configured styles for known layers', () => {
    const candilStyle = getLayerStyle('candil');

    expect(candilStyle.color).toBe(MAP_LAYER_COLORS.candil);
    expect(candilStyle.fillColor).toBe(MAP_LAYER_COLORS.candil);
  });

  it('returns fallback style for unknown layers', () => {
    expect(getLayerStyle('unknown')).toEqual(
      expect.objectContaining({
        color: '#3388ff',
        weight: 2,
        fillOpacity: 0.1,
      })
    );
  });

  it('includes analysis legend extension and map tile presets', () => {
    expect(ANALYSIS_LEGEND_ITEMS.length).toBe(DEFAULT_LEGEND_ITEMS.length + 1);
    expect(ANALYSIS_LEGEND_ITEMS.at(-1)?.label).toMatch(/Area de analisis/i);
    expect(TILE_LAYERS.osm.url).toContain('World_Street_Map');
    expect(TILE_LAYERS.osm.url).toContain('server.arcgisonline.com');
    expect(TILE_LAYERS.osm.url).not.toContain('tile.openstreetmap.org');
    expect(TILE_LAYERS.osm.url).not.toContain('basemaps.cartocdn.com');
    expect(TILE_LAYERS.osm.attribution).toContain('OpenStreetMap');
    expect(TILE_LAYERS.osm.attribution).toContain('Esri');
    expect(TILE_LAYERS.osm.attribution).not.toContain('CARTO');
    expect(TILE_LAYERS.satellite.attribution).toContain('Esri');
    expect(TILE_LAYERS.satellite.attribution).toContain('Maxar');
    expect(TILE_LAYERS.satellite.attribution).toContain('Earthstar Geographics');
  });
});
