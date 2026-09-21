/**
 * puntosInteresLayers
 *
 * Staff-only pins: painted circle + invisible hit target + `titulo` label.
 * Glyphs come from `MAP_GLYPHS_URL` (same as road labels). White text + dark
 * halo because the default basemap is satellite imagery.
 */

import type {
  CircleLayerSpecification,
  ExpressionSpecification,
  SymbolLayerSpecification,
} from 'maplibre-gl';

import { PUNTO_INTERES_TIPOS } from '../../lib/api/puntosInteres';
import { SOURCE_IDS } from './map2dConfig';

export const PUNTOS_INTERES_SOURCE_ID = SOURCE_IDS.PUNTOS_INTERES;
export const PUNTOS_INTERES_LAYER_ID = 'puntos_interes-circle' as const;
export const PUNTOS_INTERES_HIT_LAYER_ID = 'puntos_interes-hit' as const;
export const PUNTOS_INTERES_LABEL_LAYER_ID = 'puntos_interes-label' as const;

export const PUNTO_INTERES_LABEL_TEXT_SIZE: ExpressionSpecification = [
  'interpolate',
  ['linear'],
  ['zoom'],
  10,
  14,
  16,
  18,
];

const PUNTO_INTERES_LAYER_IDS = new Set<string>([
  PUNTOS_INTERES_LAYER_ID,
  PUNTOS_INTERES_HIT_LAYER_ID,
  PUNTOS_INTERES_LABEL_LAYER_ID,
]);

export function isPuntoInteresLayerId(layerId: string | undefined): boolean {
  return layerId != null && PUNTO_INTERES_LAYER_IDS.has(layerId);
}

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

/** Invisible 16 px target so a pin is selectable without a pixel-perfect hit. */
export function buildPuntosInteresHitPaint(): CirclePaint {
  return {
    'circle-radius': 16,
    'circle-color': '#000000',
    'circle-opacity': 0,
  };
}

export function buildPuntosInteresLabelLayer(
  id: string,
  source: string
): SymbolLayerSpecification {
  return {
    id,
    type: 'symbol',
    source,
    layout: {
      'text-field': ['get', 'titulo'],
      'text-font': ['Noto Sans Regular'],
      'text-size': PUNTO_INTERES_LABEL_TEXT_SIZE,
      'text-anchor': 'bottom',
      'text-offset': [0, -1.15],
      'text-optional': true,
      'text-allow-overlap': true,
      'text-ignore-placement': true,
    },
    paint: {
      'text-color': '#ffffff',
      'text-halo-color': 'rgba(0,0,0,0.75)',
      'text-halo-width': 1.6,
      'text-opacity': 0.95,
    },
  };
}
