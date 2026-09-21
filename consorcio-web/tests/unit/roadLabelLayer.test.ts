import { describe, expect, it } from 'vitest';

import {
  MAP_GLYPHS_URL,
  ROAD_HIT_LINE_WIDTH,
  ROAD_LABEL_MIN_ZOOM,
  ROAD_LABEL_TEXT_FIELD,
  buildRoadHitLayer,
  buildRoadLabelLayer,
} from '../../src/components/map2d/roadLabelLayer';

describe('buildRoadLabelLayer', () => {
  it('places the ficha Ruta code along the line, not the long nombre', () => {
    expect(ROAD_LABEL_TEXT_FIELD).toEqual([
      'coalesce',
      ['get', 'rtn'],
      ['get', 'ruta'],
      ['get', 'fna'],
    ]);
    expect(JSON.stringify(ROAD_LABEL_TEXT_FIELD)).not.toContain('nombre');
  });

  it('uses satellite-safe white text and a dark halo', () => {
    const layer = buildRoadLabelLayer('map2d-roads-label', 'map2d-roads');
    expect(layer.type).toBe('symbol');
    expect(layer.minzoom).toBe(ROAD_LABEL_MIN_ZOOM);
    expect(layer.layout?.['symbol-placement']).toBe('line');
    expect(layer.paint?.['text-color']).toBe('#ffffff');
    expect(layer.paint?.['text-halo-color']).toBe('rgba(0,0,0,0.75)');
    expect(layer.layout?.['text-size']).toEqual(['interpolate', ['linear'], ['zoom'], 11, 14, 14, 18]);
    expect(layer.paint?.['text-halo-width']).toBe(1.6);
  });

  it('points glyphs at a PBF template MapLibre 4.x can fetch', () => {
    expect(MAP_GLYPHS_URL).toContain('{fontstack}');
    expect(MAP_GLYPHS_URL).toContain('{range}.pbf');
  });
});

describe('buildRoadHitLayer', () => {
  it('is a wide invisible line so a 2 px road is clickable', () => {
    const layer = buildRoadHitLayer('map2d-roads-hit', 'map2d-roads');
    expect(layer.type).toBe('line');
    expect(layer.paint?.['line-width']).toBe(ROAD_HIT_LINE_WIDTH);
    expect(layer.paint?.['line-width']).toBeGreaterThan(8);
    expect(layer.paint?.['line-opacity']).toBe(0);
  });
});
