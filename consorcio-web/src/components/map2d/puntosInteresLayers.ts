/**
 * puntosInteresLayers
 *
 * Staff-only circle layer for unpublished map pins. Circle, not symbol:
 * this style has no glyphs URL (see `escuelasLayers.ts`).
 */

import type { CircleLayerSpecification } from 'maplibre-gl';

import { PUNTO_INTERES_TIPOS } from '../../lib/api/puntosInteres';
import { SOURCE_IDS } from './map2dConfig';

export const PUNTOS_INTERES_SOURCE_ID = SOURCE_IDS.PUNTOS_INTERES;
export const PUNTOS_INTERES_LAYER_ID = 'puntos_interes-circle' as const;

type CirclePaint = NonNullable<CircleLayerSpecification['paint']>;

const TIPO_COLORS = {
  [PUNTO_INTERES_TIPOS.ALCANTARILLA]: '#c45c26',
  [PUNTO_INTERES_TIPOS.ALTEO]: '#e0a100',
  [PUNTO_INTERES_TIPOS.TAPONAMIENTO]: '#c62828',
  [PUNTO_INTERES_TIPOS.OTRO]: '#6d4c41',
} as const;

export function buildPuntosInteresCirclePaint(): CirclePaint {
  return {
    'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 5, 16, 10],
    'circle-color': [
      'match',
      ['get', 'tipo'],
      PUNTO_INTERES_TIPOS.ALCANTARILLA,
      TIPO_COLORS[PUNTO_INTERES_TIPOS.ALCANTARILLA],
      PUNTO_INTERES_TIPOS.ALTEO,
      TIPO_COLORS[PUNTO_INTERES_TIPOS.ALTEO],
      PUNTO_INTERES_TIPOS.TAPONAMIENTO,
      TIPO_COLORS[PUNTO_INTERES_TIPOS.TAPONAMIENTO],
      TIPO_COLORS[PUNTO_INTERES_TIPOS.OTRO],
    ],
    'circle-stroke-color': '#ffffff',
    'circle-stroke-width': 2,
  };
}
