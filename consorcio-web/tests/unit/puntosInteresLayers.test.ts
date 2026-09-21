import { describe, expect, it } from 'vitest';

import {
  PUNTOS_INTERES_HIT_LAYER_ID,
  PUNTOS_INTERES_LABEL_LAYER_ID,
  PUNTOS_INTERES_LAYER_ID,
  PUNTOS_INTERES_SOURCE_ID,
  buildPuntosInteresCirclePaint,
  buildPuntosInteresHitPaint,
  buildPuntosInteresLabelLayer,
  isPuntoInteresLayerId,
  PUNTO_INTERES_LABEL_TEXT_SIZE,
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

describe('puntosInteresLayers · hit and label', () => {
  it('builds an invisible 16px hit target', () => {
    const paint = buildPuntosInteresHitPaint();
    expect(paint['circle-radius']).toBe(16);
    expect(paint['circle-opacity']).toBe(0);
  });

  it('labels the pin with titulo in white on a dark halo', () => {
    const layer = buildPuntosInteresLabelLayer(PUNTOS_INTERES_LABEL_LAYER_ID, PUNTOS_INTERES_SOURCE_ID);
    expect(layer.type).toBe('symbol');
    expect(layer.layout?.['text-field']).toEqual(['get', 'titulo']);
    expect(layer.paint?.['text-color']).toBe('#ffffff');
    expect(layer.paint?.['text-halo-color']).toBe('rgba(0,0,0,0.75)');
    expect(layer.layout?.['text-size']).toEqual(PUNTO_INTERES_LABEL_TEXT_SIZE);
    expect(layer.paint?.['text-halo-width']).toBe(1.6);
  });

  it('treats circle, hit and label as the same POI click target', () => {
    expect(isPuntoInteresLayerId(PUNTOS_INTERES_LAYER_ID)).toBe(true);
    expect(isPuntoInteresLayerId(PUNTOS_INTERES_HIT_LAYER_ID)).toBe(true);
    expect(isPuntoInteresLayerId(PUNTOS_INTERES_LABEL_LAYER_ID)).toBe(true);
    expect(isPuntoInteresLayerId('escuelas-symbol')).toBe(false);
  });
});

describe('layerRenderRegistry · puntos_interes', () => {
  it('registers hit, circle and label ml layers', () => {
    const entry = LAYER_RENDER_REGISTRY.puntos_interes;
    expect(entry.mlLayers).toEqual([
      { id: PUNTOS_INTERES_HIT_LAYER_ID, opacityProp: 'circle-opacity', defaultOpacity: 0 },
      { id: PUNTOS_INTERES_LAYER_ID, opacityProp: 'circle-opacity', defaultOpacity: 1 },
      { id: PUNTOS_INTERES_LABEL_LAYER_ID, opacityProp: 'text-opacity', defaultOpacity: 0.95 },
    ]);
  });
});
