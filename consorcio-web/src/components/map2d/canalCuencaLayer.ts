/**
 * canalCuencaLayer.ts
 *
 * On-map outline of the canal CATCHMENT for `tipo=canal_cuenca` (A7 slice 2).
 *
 * When a `canal_cuenca` ficha resolves, the backend echoes the catchment boundary
 * as `geometria_cuenca` (a GeoJSON Polygon/MultiPolygon, EPSG:4326). This module
 * paints it as a thin dedicated outline + faint fill so the user sees WHICH basin
 * the analysis covers. It is separate from `fichaOverlayLayers` (the A(b) "ver
 * recortado" clipped analysis, which clips TO this catchment): the outline shows
 * the extent, the overlay shows the classified content inside it.
 *
 * Idempotent add/update/remove, mirroring `syncFichaOverlayLayers`: a `null`
 * geometry removes the source + layers so nothing lingers across a mode/selection
 * switch (the coordinator nulls the request on every transition; this follows it).
 */

import type { Geometry } from 'geojson';
import type maplibregl from 'maplibre-gl';

/** Source + layer ids for the catchment outline (one dedicated set). */
export const CANAL_CUENCA_SOURCE = 'canal-cuenca-outline';
export const CANAL_CUENCA_FILL_LAYER = `${CANAL_CUENCA_SOURCE}-fill`;
export const CANAL_CUENCA_LINE_LAYER = `${CANAL_CUENCA_SOURCE}-line`;

/** Cyan family, matching the canal selection accent (`#06b6d4`). */
const CUENCA_OUTLINE_COLOR = '#0e7490';
const CUENCA_FILL_COLOR = '#06b6d4';

function removeCanalCuenca(map: maplibregl.Map) {
  if (map.getLayer(CANAL_CUENCA_LINE_LAYER)) map.removeLayer(CANAL_CUENCA_LINE_LAYER);
  if (map.getLayer(CANAL_CUENCA_FILL_LAYER)) map.removeLayer(CANAL_CUENCA_FILL_LAYER);
  if (map.getSource(CANAL_CUENCA_SOURCE)) map.removeSource(CANAL_CUENCA_SOURCE);
}

/**
 * Add / update / remove the catchment outline idempotently.
 *
 * - `geometry` null/undefined → the source + both layers are removed (cleared on
 *   mode/selection switch, or when the active ficha is not a `canal_cuenca`).
 * - a Polygon/MultiPolygon geometry → the source is added (or its data updated)
 *   and the faint fill + outline layers are (re)created.
 */
export function syncCanalCuencaLayer(map: maplibregl.Map, geometry: Geometry | null | undefined) {
  if (!geometry) {
    removeCanalCuenca(map);
    return;
  }

  const featureCollection = {
    type: 'FeatureCollection' as const,
    features: [{ type: 'Feature' as const, properties: {}, geometry }],
  };

  const existing = map.getSource(CANAL_CUENCA_SOURCE) as maplibregl.GeoJSONSource | undefined;
  if (existing) {
    existing.setData(featureCollection);
  } else {
    map.addSource(CANAL_CUENCA_SOURCE, {
      type: 'geojson',
      data: featureCollection,
    });
  }

  if (!map.getLayer(CANAL_CUENCA_FILL_LAYER)) {
    map.addLayer({
      id: CANAL_CUENCA_FILL_LAYER,
      type: 'fill',
      source: CANAL_CUENCA_SOURCE,
      paint: { 'fill-color': CUENCA_FILL_COLOR, 'fill-opacity': 0.12 },
    });
  }

  if (!map.getLayer(CANAL_CUENCA_LINE_LAYER)) {
    map.addLayer({
      id: CANAL_CUENCA_LINE_LAYER,
      type: 'line',
      source: CANAL_CUENCA_SOURCE,
      paint: {
        'line-color': CUENCA_OUTLINE_COLOR,
        'line-width': 2,
        'line-opacity': 0.9,
      },
    });
  }
}

/** Convenience teardown (unmount / map removal). */
export function clearCanalCuencaLayer(map: maplibregl.Map) {
  syncCanalCuencaLayer(map, null);
}
