/**
 * fichaOverlayLayers.ts
 *
 * On-map overlay of the ficha analysis CLIPPED to the analyzed zone (A(b) slice 1,
 * soils only). Mirrors the `syncMartinSuggestionLayers` add-source + add-layer +
 * visibility pattern in `mapRasterOverlayHelpers.ts`: one GeoJSON source, a `fill`
 * layer plus a thin `line` outline, added idempotently and removed when hidden.
 *
 * The polygons arrive already clipped from the server — this module never clips,
 * unions or reprojects. It only paints them, coloring each feature by its
 * `properties.clase` with the SAME soil-capability palette the ficha panel uses
 * (`SOIL_CAPABILITY_COLORS` / `getSoilColor` from `useSoilMap`). There is no
 * second palette here.
 */

import type maplibregl from 'maplibre-gl';
import type { FeatureCollection } from 'geojson';

import { SOIL_CAPABILITY_COLORS } from '../../hooks/useSoilMap';
import type { FichaOverlayDataset } from '../../lib/api/ficha';

/** Source + layer ids for the ficha overlay (one set, slice 1 paints soils). */
export const FICHA_OVERLAY_SOURCE = 'ficha-overlay';
export const FICHA_OVERLAY_FILL_LAYER = `${FICHA_OVERLAY_SOURCE}-fill`;
export const FICHA_OVERLAY_LINE_LAYER = `${FICHA_OVERLAY_SOURCE}-line`;

/** Fallback for an unclassified / unknown clase — matches `getSoilColor`'s default. */
export const SOIL_OVERLAY_FALLBACK_COLOR = '#8d6e63';

/**
 * MapLibre `match` expression coloring a feature by `properties.clase`, reusing
 * the panel's `SOIL_CAPABILITY_COLORS` (I…VIII). Any other clase (e.g.
 * `"sin clasificar"`) falls back to the same neutral brown `getSoilColor` uses,
 * so the overlay and the panel never disagree on a color.
 */
export function buildSoilOverlayColorExpression(): maplibregl.ExpressionSpecification {
  const cases: (string | string[])[] = [];
  for (const [clase, color] of Object.entries(SOIL_CAPABILITY_COLORS)) {
    cases.push(clase, color);
  }
  return [
    'match',
    ['get', 'clase'],
    ...cases,
    SOIL_OVERLAY_FALLBACK_COLOR,
  ] as unknown as maplibregl.ExpressionSpecification;
}

function removeFichaOverlay(map: maplibregl.Map) {
  if (map.getLayer(FICHA_OVERLAY_LINE_LAYER)) {
    map.removeLayer(FICHA_OVERLAY_LINE_LAYER);
  }
  if (map.getLayer(FICHA_OVERLAY_FILL_LAYER)) {
    map.removeLayer(FICHA_OVERLAY_FILL_LAYER);
  }
  if (map.getSource(FICHA_OVERLAY_SOURCE)) {
    map.removeSource(FICHA_OVERLAY_SOURCE);
  }
}

const EMPTY_FC: FeatureCollection = { type: 'FeatureCollection', features: [] };

/**
 * Add / update / remove the ficha overlay layers idempotently.
 *
 * - `visible: false` or no `featureCollection` → the source + both layers are
 *   removed, so nothing lingers over a new selection (the coordinator clears the
 *   ficha on every mode/selection switch; this mirrors that).
 * - `visible: true` with a FeatureCollection → the source is added (or its data
 *   updated) and the fill + line layers are (re)created, colored by `clase`.
 */
export function syncFichaOverlayLayers(
  map: maplibregl.Map,
  params: {
    featureCollection: FeatureCollection | null | undefined;
    dataset: FichaOverlayDataset;
    visible: boolean;
  }
) {
  const { featureCollection, visible } = params;

  if (!visible || !featureCollection) {
    removeFichaOverlay(map);
    return;
  }

  const existing = map.getSource(FICHA_OVERLAY_SOURCE) as maplibregl.GeoJSONSource | undefined;
  if (existing) {
    existing.setData(featureCollection);
  } else {
    map.addSource(FICHA_OVERLAY_SOURCE, {
      type: 'geojson',
      data: featureCollection,
    });
  }

  if (!map.getLayer(FICHA_OVERLAY_FILL_LAYER)) {
    map.addLayer({
      id: FICHA_OVERLAY_FILL_LAYER,
      type: 'fill',
      source: FICHA_OVERLAY_SOURCE,
      paint: {
        'fill-color': buildSoilOverlayColorExpression(),
        'fill-opacity': 0.55,
      },
    });
  }

  if (!map.getLayer(FICHA_OVERLAY_LINE_LAYER)) {
    map.addLayer({
      id: FICHA_OVERLAY_LINE_LAYER,
      type: 'line',
      source: FICHA_OVERLAY_SOURCE,
      paint: {
        'line-color': buildSoilOverlayColorExpression(),
        'line-width': 0.6,
      },
    });
  }
}

/** Convenience for a clean teardown (unmount / map removal). */
export function clearFichaOverlayLayers(map: maplibregl.Map) {
  syncFichaOverlayLayers(map, {
    featureCollection: EMPTY_FC,
    dataset: 'suelos',
    visible: false,
  });
}
