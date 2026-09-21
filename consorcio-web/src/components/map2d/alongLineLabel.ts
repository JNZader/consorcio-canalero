/**
 * Shared along-line symbol labels (roads, canales, waterways).
 * Requires `MAP_GLYPHS_URL` on the style (same as road labels).
 */
import type { ExpressionSpecification, SymbolLayerSpecification } from 'maplibre-gl';

export const ALONG_LINE_LABEL_MIN_ZOOM = 11;

export const ALONG_LINE_LABEL_TEXT_SIZE: ExpressionSpecification = [
  'interpolate',
  ['linear'],
  ['zoom'],
  11,
  14,
  14,
  18,
];

/** Canal KMZ code, then the short name. */
export const CANAL_LABEL_TEXT_FIELD: ExpressionSpecification = [
  'coalesce',
  ['get', 'codigo'],
  ['get', 'nombre'],
];

export function buildAlongLineLabelLayer(options: {
  id: string;
  source: string;
  textField: string | ExpressionSpecification;
  minzoom?: number;
}): SymbolLayerSpecification {
  return {
    id: options.id,
    type: 'symbol',
    source: options.source,
    minzoom: options.minzoom ?? ALONG_LINE_LABEL_MIN_ZOOM,
    layout: {
      'symbol-placement': 'line',
      'symbol-spacing': 280,
      'text-field': options.textField,
      'text-font': ['Noto Sans Regular'],
      'text-size': ALONG_LINE_LABEL_TEXT_SIZE,
      'text-keep-upright': true,
      'text-rotation-alignment': 'map',
      'text-pitch-alignment': 'viewport',
      'text-letter-spacing': 0.04,
      'text-max-angle': 35,
      'text-optional': true,
      'text-allow-overlap': false,
      'text-ignore-placement': false,
    },
    paint: {
      'text-color': '#ffffff',
      'text-halo-color': 'rgba(0,0,0,0.75)',
      'text-halo-width': 1.6,
      'text-opacity': 0.95,
    },
  };
}
