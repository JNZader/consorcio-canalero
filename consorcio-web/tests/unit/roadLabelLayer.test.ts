import { describe, expect, it } from 'vitest';

import {
  MAP_GLYPHS_URL,
  ROAD_LABEL_MIN_ZOOM,
  ROAD_LABEL_TEXT_FIELD,
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
  });

  it('points glyphs at a PBF template MapLibre 4.x can fetch', () => {
    expect(MAP_GLYPHS_URL).toContain('{fontstack}');
    expect(MAP_GLYPHS_URL).toContain('{range}.pbf');
  });
});
