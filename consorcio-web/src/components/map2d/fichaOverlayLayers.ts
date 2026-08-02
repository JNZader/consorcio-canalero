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

import { LAYER_LEGEND_CONFIG } from '../../config/rasterLegend';
import { SOIL_CAPABILITY_COLORS } from '../../hooks/useSoilMap';
import type { FichaOverlayDataset } from '../../lib/api/ficha';

/** Source + layer ids for the ficha overlay (one set, slice 1 paints soils). */
export const FICHA_OVERLAY_SOURCE = 'ficha-overlay';
export const FICHA_OVERLAY_FILL_LAYER = `${FICHA_OVERLAY_SOURCE}-fill`;
export const FICHA_OVERLAY_LINE_LAYER = `${FICHA_OVERLAY_SOURCE}-line`;

/** Fallback for an unclassified / unknown clase — matches `getSoilColor`'s default. */
export const SOIL_OVERLAY_FALLBACK_COLOR = '#8d6e63';

/** Fallback for a flood/drainage clase not found in the legend ranges (neutral grey). */
export const RIESGO_OVERLAY_FALLBACK_COLOR = '#9e9e9e';

/**
 * Fill opacity of the clipped analysis (T3a, fix 1b).
 *
 * It used to be 0.55, and at that value the flood-risk "Alto" swatch (`#fc8d59`,
 * a pale orange) fused with the tan farmland of the satellite basemap: the owner
 * read the overlay as "wrong" because a whole class was effectively invisible.
 * 0.7 keeps the basemap legible underneath while the class colors stay their own.
 */
export const FICHA_OVERLAY_FILL_OPACITY = 0.7;

/**
 * Class-boundary outline (T3a, fix 1b). The line used to be painted with the SAME
 * per-class color expression as the fill, which is exactly the color that already
 * failed to separate "Alto" from the terrain. A neutral dark hairline at low
 * opacity separates adjacent classes regardless of how close their fills are, and
 * reads as an outline rather than as a fifth palette entry.
 */
export const FICHA_OVERLAY_LINE_COLOR = '#212121';
export const FICHA_OVERLAY_LINE_WIDTH = 1;
export const FICHA_OVERLAY_LINE_OPACITY = 0.55;

/**
 * Color a flood_risk / drainage_need class LABEL (Bajo / Medio / Alto / Crítico)
 * from `LAYER_LEGEND_CONFIG[dataset].ranges`. THE single lookup: the on-map paint
 * expression below and the `RiesgoBins` table chips both go through it, so the
 * table is literally the overlay's legend and the two can never drift apart.
 */
export function riesgoClassColor(dataset: 'flood_risk' | 'drainage_need', clase: string): string {
  const ranges = LAYER_LEGEND_CONFIG[dataset]?.ranges ?? [];
  return ranges.find((range) => range.label === clase)?.color ?? RIESGO_OVERLAY_FALLBACK_COLOR;
}

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

/**
 * MapLibre `match` expression coloring a flood_risk / drainage_need feature by
 * `properties.clase` (Bajo / Medio / Alto / Crítico) using the SAME per-class
 * colors the panel's legend reads from `LAYER_LEGEND_CONFIG[dataset].ranges`. No
 * second palette — the backend emits the class LABEL and this maps label → color
 * from the shared legend config, so the overlay and the `RiesgoBins` legend agree.
 */
export function buildRiesgoOverlayColorExpression(
  dataset: 'flood_risk' | 'drainage_need'
): maplibregl.ExpressionSpecification {
  const ranges = LAYER_LEGEND_CONFIG[dataset]?.ranges ?? [];
  const cases: (string | string[])[] = [];
  for (const range of ranges) {
    cases.push(range.label, riesgoClassColor(dataset, range.label));
  }
  return [
    'match',
    ['get', 'clase'],
    ...cases,
    RIESGO_OVERLAY_FALLBACK_COLOR,
  ] as unknown as maplibregl.ExpressionSpecification;
}

/** Dataset-aware color expression: soils palette for `suelos`, legend ranges for rasters. */
export function buildOverlayColorExpression(
  dataset: FichaOverlayDataset
): maplibregl.ExpressionSpecification {
  return dataset === 'suelos'
    ? buildSoilOverlayColorExpression()
    : buildRiesgoOverlayColorExpression(dataset);
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
  const { featureCollection, dataset, visible } = params;

  if (!visible || !featureCollection) {
    removeFichaOverlay(map);
    return;
  }

  const colorExpression = buildOverlayColorExpression(dataset);

  const existing = map.getSource(FICHA_OVERLAY_SOURCE) as maplibregl.GeoJSONSource | undefined;
  if (existing) {
    existing.setData(featureCollection);
  } else {
    map.addSource(FICHA_OVERLAY_SOURCE, {
      type: 'geojson',
      data: featureCollection,
    });
  }

  if (map.getLayer(FICHA_OVERLAY_FILL_LAYER)) {
    // Layer already mounted (e.g. dataset switched) → repaint with the current
    // dataset's palette so a soils overlay never keeps painting flood classes.
    map.setPaintProperty?.(FICHA_OVERLAY_FILL_LAYER, 'fill-color', colorExpression);
  } else {
    map.addLayer({
      id: FICHA_OVERLAY_FILL_LAYER,
      type: 'fill',
      source: FICHA_OVERLAY_SOURCE,
      paint: {
        'fill-color': colorExpression,
        'fill-opacity': FICHA_OVERLAY_FILL_OPACITY,
      },
    });
  }

  // The outline is dataset-INDEPENDENT (a neutral dark hairline), so a dataset
  // switch has nothing to repaint here. It is reasserted anyway because this
  // function is the ONLY writer of that paint property and it runs on every
  // in-session dataset switch over a layer that is created once and reused: an
  // unconditional set costs one no-op call and removes any doubt about what the
  // line color is after N switches, while a conditional would have to track it.
  if (map.getLayer(FICHA_OVERLAY_LINE_LAYER)) {
    map.setPaintProperty?.(FICHA_OVERLAY_LINE_LAYER, 'line-color', FICHA_OVERLAY_LINE_COLOR);
  } else {
    map.addLayer({
      id: FICHA_OVERLAY_LINE_LAYER,
      type: 'line',
      source: FICHA_OVERLAY_SOURCE,
      paint: {
        'line-color': FICHA_OVERLAY_LINE_COLOR,
        'line-width': FICHA_OVERLAY_LINE_WIDTH,
        'line-opacity': FICHA_OVERLAY_LINE_OPACITY,
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
