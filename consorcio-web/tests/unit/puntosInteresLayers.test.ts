import { describe, expect, it } from 'vitest';

import {
  PUNTOS_INTERES_LAYER_ID,
  PUNTOS_INTERES_SOURCE_ID,
  buildPuntosInteresCirclePaint,
} from '../../src/components/map2d/puntosInteresLayers';
import { SOURCE_IDS } from '../../src/components/map2d/map2dConfig';
import { LAYER_RENDER_REGISTRY } from '../../src/components/map2d/layerRenderRegistry';

describe('puntosInteresLayers · constants', () => {
  it('exposes the source id matching SOURCE_IDS.PUNTOS_INTERES', () => {
    expect(PUNTOS_INTERES_SOURCE_ID).toBe(SOURCE_IDS.PUNTOS_INTERES);
    expect(PUNTOS_INTERES_SOURCE_ID).toBe('puntos_interes');
  });

  it('exposes the circle layer id', () => {
    expect(PUNTOS_INTERES_LAYER_ID).toBe('puntos_interes-circle');
  });
});

describe('buildPuntosInteresCirclePaint', () => {
  it('strokes the circle with a 2px white outline', () => {
    const paint = buildPuntosInteresCirclePaint();
    expect(paint['circle-stroke-color']).toBe('#ffffff');
    expect(paint['circle-stroke-width']).toBe(2);
  });

  it('colors by tipo via match', () => {
    const paint = buildPuntosInteresCirclePaint();
    expect(paint['circle-color']).toEqual([
      'match',
      ['get', 'tipo'],
      'alcantarilla',
      '#c45c26',
      'alteo',
      '#e0a100',
      'taponamiento',
      '#c62828',
      '#6d4c41',
    ]);
  });

  it('interpolates radius from 5 at z10 to 10 at z16', () => {
    const paint = buildPuntosInteresCirclePaint();
    expect(paint['circle-radius']).toEqual(['interpolate', ['linear'], ['zoom'], 10, 5, 16, 10]);
  });
});

describe('layerRenderRegistry · puntos_interes', () => {
  it('registers a circle ml layer', () => {
    const entry = LAYER_RENDER_REGISTRY.puntos_interes;
    expect(entry.mlLayers).toEqual([
      { id: PUNTOS_INTERES_LAYER_ID, opacityProp: 'circle-opacity', defaultOpacity: 1 },
    ]);
  });
});
