import { describe, expect, it } from 'vitest';

import { parseMapPermalink, serializeMapPermalink } from '../../src/components/map2d/mapPermalink';

const CATALOG = ['roads', 'waterways', 'catastro', 'canales_relevados'];

describe('parseMapPermalink', () => {
  it('reads camera, preset, layers and raster', () => {
    const parsed = parseMapPermalink(
      '?lat=-32.4&lng=-62.7&zoom=12.5&preset=agua&l=waterways,canales_relevados&r=flood_risk'
    );
    expect(parsed.lat).toBeCloseTo(-32.4);
    expect(parsed.lng).toBeCloseTo(-62.7);
    expect(parsed.zoom).toBeCloseTo(12.5);
    expect(parsed.preset).toBe('agua');
    expect(parsed.layers).toEqual(['waterways', 'canales_relevados']);
    expect(parsed.rasterTipo).toBe('flood_risk');
  });

  it('treats l=none as empty layer list', () => {
    expect(parseMapPermalink('?l=none').layers).toEqual([]);
  });

  it('ignores unknown presets and per-canal ids', () => {
    const parsed = parseMapPermalink('?preset=nope&l=roads,canal_relevado_foo');
    expect(parsed.preset).toBeUndefined();
    expect(parsed.layers).toEqual(['roads']);
  });
});

describe('serializeMapPermalink', () => {
  it('writes a shareable query and keeps unrelated params', () => {
    const qs = serializeMapPermalink('?foo=bar', {
      lat: -32.123456,
      lng: -62.987654,
      zoom: 11,
      preset: 'caminos',
      layers: ['roads', 'unknown'],
      rasterTipo: 'hand',
    }, CATALOG);
    const params = new URLSearchParams(qs);
    expect(params.get('foo')).toBe('bar');
    expect(params.get('preset')).toBe('caminos');
    expect(params.get('l')).toBe('roads');
    expect(params.get('r')).toBe('hand');
    expect(params.get('lat')).toBe('-32.12346');
  });

  it('encodes all-off layers as l=none', () => {
    const qs = serializeMapPermalink('', { layers: [] }, CATALOG);
    expect(new URLSearchParams(qs).get('l')).toBe('none');
  });
});
