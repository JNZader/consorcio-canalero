/**
 * ypfEstacionBombeoLayer
 *
 * Colocated registry for the static "Estación de bombeo YPF" landmark point
 * in Monte Leña. Sibling of `escuelasLayers.ts` but radically simpler:
 *
 *   - ONE hardcoded point. No KMZ, no ETL, no static asset file — the
 *     FeatureCollection is inlined right here.
 *   - NO visibility toggle. The layer is always mounted AND always visible
 *     from map init.
 *   - NO click handling. The circle renders but does not participate in the
 *     InfoPanel click stack (see `buildClickableLayers`).
 *
 * Rendering model
 * ---------------
 * One NATIVE MapLibre `circle` layer. Same proven pattern as escuelas — no
 * icon asset, no `loadImage`, no Promise-shaped mount, no silent-fail path.
 * Radius is slightly larger (5→9 vs. 4→8) so the single landmark reads as
 * MORE prominent than the cluster of blue escuelas points.
 *
 * Color: Material Deep Orange 800 (`#d84315`) — visually distinct from the
 * Pilar Azul blue (escuelas `#1976d2`) and the Pilar Verde green family.
 */

import type { FeatureCollection, Point } from 'geojson';
import type { CircleLayerSpecification } from 'maplibre-gl';

/** Source id for the hardcoded YPF pump station FeatureCollection. */
export const YPF_ESTACION_BOMBEO_SOURCE_ID = 'ypf-estacion-bombeo' as const;

/** Canonical layer id — the MapLibre-native circle layer discriminator. */
export const YPF_ESTACION_BOMBEO_LAYER_ID = 'ypf-estacion-bombeo-circle' as const;

/** Spanish display label used by the legend and the feature `nombre` property. */
export const YPF_ESTACION_BOMBEO_LABEL = 'Estación de bombeo YPF' as const;

/**
 * Circle fill color — Material Deep Orange 800. Kept as a public constant so
 * the LeyendaPanel swatch and the MapLibre paint stay in lock-step.
 */
export const YPF_ESTACION_BOMBEO_COLOR = '#d84315' as const;

/**
 * Coordinates for the Monte Leña YPF pump station.
 * GeoJSON order is `[lng, lat]` (opposite of Leaflet).
 */
const YPF_ESTACION_BOMBEO_COORDS: [number, number] = [-62.5436402, -32.5728979];

/**
 * Hardcoded FeatureCollection with a single Point feature. No PII — only a
 * minimal `nombre` property so any future InfoPanel wiring has a label to
 * show. (The current feature request explicitly asks for NO click handler,
 * but leaving `nombre` in place costs nothing and matches the escuelas
 * convention.)
 */
export const YPF_ESTACION_BOMBEO_GEOJSON: FeatureCollection<Point> = {
  type: 'FeatureCollection',
  features: [
    {
      type: 'Feature',
      geometry: { type: 'Point', coordinates: YPF_ESTACION_BOMBEO_COORDS },
      properties: { nombre: YPF_ESTACION_BOMBEO_LABEL },
    },
  ],
};

type CirclePaint = NonNullable<CircleLayerSpecification['paint']>;

/**
 * Paint for the `ypf-estacion-bombeo-circle` layer.
 *
 *   - `circle-radius` interpolates on zoom from 5 @ z10 to 9 @ z16 —
 *     deliberately 1px larger at each stop than `buildEscuelasCirclePaint()`
 *     so this single landmark reads as more prominent than the escuelas.
 *   - `circle-color` `#d84315` (Material Deep Orange 800) — visually
 *     distinct from every other layer in the style.
 *   - `circle-stroke-color` white + width 2 guarantees the point reads on
 *     any basemap (satellite imagery, OSM light, DEM overlays).
 */
export function buildYpfEstacionBombeoPaint(): CirclePaint {
  return {
    'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 5, 16, 9],
    'circle-color': YPF_ESTACION_BOMBEO_COLOR,
    'circle-stroke-color': '#ffffff',
    'circle-stroke-width': 2,
  };
}
