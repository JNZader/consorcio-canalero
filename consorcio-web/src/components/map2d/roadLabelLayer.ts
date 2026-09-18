/**
 * Along-line labels for the Red Vial (`rtn` / `ruta`).
 *
 * MapLibre 4.x requires a style `glyphs` URL for any `symbol` + `text-field`
 * layer — TinySDF local fonts only exist in GL JS ≥ 5.11. Both 2D and 3D
 * map styles must set `MAP_GLYPHS_URL` or this layer fails closed (no text,
 * no throw). That is the same failure that killed the escuelas name labels;
 * do not add another `text-field` layer without glyphs.
 *
 * Basemap is satellite/aerial by default → white text + dark halo
 * (maplibre-cartography).
 */
import type { SymbolLayerSpecification } from 'maplibre-gl';

/** SDF glyph template. Font folder names must match `text-font` exactly. */
export const MAP_GLYPHS_URL = 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf';

export const ROAD_LABEL_MIN_ZOOM = 11;

/**
 * Route number as shown in the ficha (`Ruta` → `rtn`). Public GeoJSON uses
 * `ruta`; IDECOR-shaped payloads use `rtn` / `fna`. Do not fall back to
 * `nombre` — that is the long "Camino Provincial T269-03" string.
 */
export const ROAD_LABEL_TEXT_FIELD = [
  'coalesce',
  ['get', 'rtn'],
  ['get', 'ruta'],
  ['get', 'fna'],
] as const;

export function buildRoadLabelLayer(id: string, source: string): SymbolLayerSpecification {
  return {
    id,
    type: 'symbol',
    source,
    minzoom: ROAD_LABEL_MIN_ZOOM,
    layout: {
      'symbol-placement': 'line',
      'symbol-spacing': 280,
      'text-field': [...ROAD_LABEL_TEXT_FIELD],
      'text-font': ['Noto Sans Regular'],
      'text-size': ['interpolate', ['linear'], ['zoom'], 11, 10, 14, 12],
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
      'text-halo-width': 1.2,
      'text-opacity': 0.95,
    },
  };
}
