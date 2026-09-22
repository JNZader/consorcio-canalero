/**
 * redVialOficialLayers
 *
 * Staff-only overlay of `/capas/red_vial_oficial_clip.geojson`: IDECOR
 * features that are NOT already in the operational 380-road padrón
 * (`SOURCE_IDS.ROADS` / `caminos.geojson`). Provincial IDECOR is omitted
 * because Red Vial already covers it; the clip is AU9 / RN1V09.
 *
 * One orange line layer. Filter on `estado=falta_en_padron` is defense in
 * depth if the GeoJSON is regenerated with both estados.
 */

import type { FilterSpecification, LineLayerSpecification } from 'maplibre-gl';

import { SOURCE_IDS } from './map2dConfig';

export const RED_VIAL_OFICIAL_GEOJSON_URL = '/capas/red_vial_oficial_clip.geojson' as const;

export const RED_VIAL_OFICIAL_SOURCE_ID = SOURCE_IDS.RED_VIAL_OFICIAL;

export const RED_VIAL_OFICIAL_ESTADO = {
  FALTA_EN_PADRON: 'falta_en_padron',
} as const;

export type RedVialOficialEstado =
  (typeof RED_VIAL_OFICIAL_ESTADO)[keyof typeof RED_VIAL_OFICIAL_ESTADO];

export const RED_VIAL_OFICIAL_LAYER_IDS = {
  FALTA: `${SOURCE_IDS.RED_VIAL_OFICIAL}-falta`,
  /** Removed from the overlay; kept so stale map instances can still unmount it. */
  EN_PADRON: `${SOURCE_IDS.RED_VIAL_OFICIAL}-en_padron`,
} as const;

export const RED_VIAL_OFICIAL_PAINT = {
  falta_en_padron: {
    color: '#ea580c',
    width: 3,
    opacity: 1,
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
