/**
 * caminosHuecosLayers
 *
 * Staff-only overlay of `/capas/caminos_huecos.geojson`: OSM unclassified +
 * IGN terciaria that do NOT match our 380-road padrón. Not merged into
 * `red_vial` / `caminos.geojson`. Distinct from the IDECOR official overlay
 * (`red_vial_oficial`, AU9 / RN1V09).
 *
 * Two line layers, one source, split on `fuente`:
 *   - osm  — violet solid (vecinal / huella OSM)
 *   - ign  — cyan dashed (IGN terciaria residual after 150 m match)
 */

import type { FilterSpecification, LineLayerSpecification } from 'maplibre-gl';

import { SOURCE_IDS } from './map2dConfig';

export const CAMINOS_HUECOS_GEOJSON_URL = '/capas/caminos_huecos.geojson' as const;

export const CAMINOS_HUECOS_SOURCE_ID = SOURCE_IDS.CAMINOS_HUECOS;

export const CAMINOS_HUECOS_FUENTE = {
  OSM: 'osm',
  IGN: 'ign',
} as const;

export type CaminosHuecosFuente =
  (typeof CAMINOS_HUECOS_FUENTE)[keyof typeof CAMINOS_HUECOS_FUENTE];

export const CAMINOS_HUECOS_LAYER_IDS = {
  OSM: `${SOURCE_IDS.CAMINOS_HUECOS}-osm`,
  IGN: `${SOURCE_IDS.CAMINOS_HUECOS}-ign`,
} as const;

export const CAMINOS_HUECOS_PAINT = {
  osm: {
    color: '#c026d3',
    width: 3,
    opacity: 0.95,
  },
  ign: {
    color: '#0891b2',
    width: 3,
    opacity: 0.9,
    dasharray: [3, 2],
  },
} as const;

type LinePaint = NonNullable<LineLayerSpecification['paint']>;

export function buildCaminosHuecosFuenteFilter(fuente: CaminosHuecosFuente): FilterSpecification {
  return ['==', ['get', 'fuente'], fuente];
}

export function buildCaminosHuecosOsmPaint(): LinePaint {
  return {
    'line-color': CAMINOS_HUECOS_PAINT.osm.color,
    'line-width': CAMINOS_HUECOS_PAINT.osm.width,
    'line-opacity': CAMINOS_HUECOS_PAINT.osm.opacity,
  };
}

export function buildCaminosHuecosIgnPaint(): LinePaint {
  return {
    'line-color': CAMINOS_HUECOS_PAINT.ign.color,
    'line-width': CAMINOS_HUECOS_PAINT.ign.width,
    'line-opacity': CAMINOS_HUECOS_PAINT.ign.opacity,
    'line-dasharray': [...CAMINOS_HUECOS_PAINT.ign.dasharray],
  };
}
