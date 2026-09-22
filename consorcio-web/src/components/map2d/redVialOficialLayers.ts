/**
 * redVialOficialLayers
 *
 * Staff-only overlay of `/capas/red_vial_oficial_clip.geojson` (IDECOR
 * provincial + nacional clipped to the consorcio contour). NOT the operational
 * 380-road padrón (`SOURCE_IDS.ROADS` / `caminos.geojson`).
 *
 * Two line layers, one source, split on `estado`:
 *   - `falta_en_padron` — orange solid (the gap: AU9 / RN1V09)
 *   - `en_padron`       — green dashed, lower opacity (already in our 380)
 *
 * `line-dasharray` is not reliably data-driven in MapLibre, so the split is
 * two filtered layers rather than a match expression.
 */

import type { FilterSpecification, LineLayerSpecification } from 'maplibre-gl';

import { SOURCE_IDS } from './map2dConfig';

export const RED_VIAL_OFICIAL_GEOJSON_URL = '/capas/red_vial_oficial_clip.geojson' as const;

export const RED_VIAL_OFICIAL_SOURCE_ID = SOURCE_IDS.RED_VIAL_OFICIAL;

export const RED_VIAL_OFICIAL_ESTADO = {
  EN_PADRON: 'en_padron',
  FALTA_EN_PADRON: 'falta_en_padron',
} as const;

export type RedVialOficialEstado =
  (typeof RED_VIAL_OFICIAL_ESTADO)[keyof typeof RED_VIAL_OFICIAL_ESTADO];

export const RED_VIAL_OFICIAL_LAYER_IDS = {
  EN_PADRON: `${SOURCE_IDS.RED_VIAL_OFICIAL}-en_padron`,
  FALTA: `${SOURCE_IDS.RED_VIAL_OFICIAL}-falta`,
} as const;

export const RED_VIAL_OFICIAL_PAINT = {
  falta_en_padron: {
    color: '#ea580c',
    width: 3,
    opacity: 1,
  },
  en_padron: {
    color: '#22c55e',
    width: 2,
    opacity: 0.45,
    dasharray: [2, 2],
  },
} as const;

type LinePaint = NonNullable<LineLayerSpecification['paint']>;

export function buildRedVialOficialEstadoFilter(estado: RedVialOficialEstado): FilterSpecification {
  return ['==', ['get', 'estado'], estado];
}

export function buildRedVialOficialFaltaPaint(): LinePaint {
  return {
    'line-color': RED_VIAL_OFICIAL_PAINT.falta_en_padron.color,
    'line-width': RED_VIAL_OFICIAL_PAINT.falta_en_padron.width,
    'line-opacity': RED_VIAL_OFICIAL_PAINT.falta_en_padron.opacity,
  };
}

export function buildRedVialOficialEnPadronPaint(): LinePaint {
  return {
    'line-color': RED_VIAL_OFICIAL_PAINT.en_padron.color,
    'line-width': RED_VIAL_OFICIAL_PAINT.en_padron.width,
    'line-opacity': RED_VIAL_OFICIAL_PAINT.en_padron.opacity,
    'line-dasharray': [...RED_VIAL_OFICIAL_PAINT.en_padron.dasharray],
  };
}
