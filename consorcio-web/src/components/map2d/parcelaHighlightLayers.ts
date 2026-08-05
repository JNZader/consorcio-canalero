/**
 * parcelaHighlightLayers.ts
 *
 * Paints the parcels currently accumulated in a multi-parcel ficha selection
 * (T4). Purely a VISUAL cue: it tells the user which parcels the panel's
 * hectares came from, so a selection built by ctrl-clicking across a large map
 * is auditable at a glance instead of being invisible state.
 *
 * It reuses the catastro VECTOR TILE source (`map2d-catastro`, source-layer
 * `parcelas_catastro`) and filters it by the whitelisted `nomenclatura`
 * property. Tile geometry is clipped per tile and simplified per zoom — which is
 * precisely why the ANALYSIS union is computed server-side — but for painting a
 * highlight it is exactly the geometry already on screen, so there is nothing to
 * fetch, nothing to reproject, and no chance of the highlight and the parcel
 * outline disagreeing by a pixel.
 *
 * Same add-source-once / add-layer-once / remove-when-empty shape as
 * `fichaOverlayLayers.ts`, and like it this module is the SINGLE writer of its
 * layers.
 */

import type maplibregl from 'maplibre-gl';

import { SOURCE_IDS } from './map2dConfig';

/** Layer ids of the selection highlight. The SOURCE is catastro's, not ours. */
export const PARCELA_HIGHLIGHT_FILL_LAYER = 'ficha-parcela-highlight-fill';
export const PARCELA_HIGHLIGHT_LINE_LAYER = 'ficha-parcela-highlight-line';

/** The catastro vector source + its source-layer, owned by `syncCatastroLayers`. */
const CATASTRO_SOURCE = SOURCE_IDS.CATASTRO;
const CATASTRO_SOURCE_LAYER = 'parcelas_catastro';

/**
 * Highlight styling. A saturated amber against the catastro layer's muted brown
 * fill (`#8d6e63` at 0.12) so a selected parcel is unmistakable on both the OSM
 * and the satellite basemap, with a thick outline carrying the shape at zooms
 * where the fill is a few pixels wide.
 */
export const PARCELA_HIGHLIGHT_COLOR = '#f59f00';
export const PARCELA_HIGHLIGHT_FILL_OPACITY = 0.35;
export const PARCELA_HIGHLIGHT_LINE_WIDTH = 2.5;

/**
 * MapLibre filter matching the selected nomenclaturas.
 *
 * Exported for tests: the whole feature rests on this property name matching the
 * catastro tile whitelist (`layerPropertyWhitelists.catastro`), and on the click
 * resolver reading the SAME property (`useMapInteractionEffects.resolveParcela`).
 */
export function buildParcelaHighlightFilter(
  nomenclaturas: readonly string[]
): maplibregl.FilterSpecification {
  return [
    'in',
    ['get', 'nomenclatura'],
    ['literal', [...nomenclaturas]],
  ] as unknown as maplibregl.FilterSpecification;
}

function removeParcelaHighlight(map: maplibregl.Map) {
  for (const layerId of [PARCELA_HIGHLIGHT_LINE_LAYER, PARCELA_HIGHLIGHT_FILL_LAYER]) {
    if (map.getLayer(layerId)) map.removeLayer(layerId);
  }
}

/**
 * Add / update / remove the selection highlight idempotently.
 *
 * - An EMPTY selection removes both layers, so nothing lingers over a cleared
 *   ficha or after a mode switch.
 * - A single-parcel selection is highlighted too: the user who is about to
 *   ctrl-click a second parcel needs to see what the first one was.
 * - `catastroVisible: false` removes the highlight. Turning the catastro layer
 *   off only flips its LAYERS' visibility — `syncCatastroLayers` keeps the
 *   vector SOURCE on the map — so without this flag the amber highlight kept
 *   painting parcels whose outlines the user had just hidden, which reads as the
 *   map ignoring the layer switch.
 * - If the catastro source is not on the map at all (the style has not finished
 *   loading), this is a NO-OP rather than an error — the caller re-runs on every
 *   selection change, so the highlight appears as soon as the source is there.
 * - `overlayActive: true` drops the FILL and keeps only the outline. See
 *   `THE FILL LIES OVER THE FICHA OVERLAY` below — do NOT "simplify" this away.
 */
export function syncParcelaHighlightLayers(
  map: maplibregl.Map,
  nomenclaturas: readonly string[],
  catastroVisible = true,
  overlayActive = false
) {
  if (nomenclaturas.length === 0 || !catastroVisible || !map.getSource(CATASTRO_SOURCE)) {
    removeParcelaHighlight(map);
    return;
  }

  const filter = buildParcelaHighlightFilter(nomenclaturas);

  /* ── THE FILL LIES OVER THE FICHA OVERLAY ───────────────────────────────────
     Reported on a multi-parcel selection near the consortium boundary, root
     cause confirmed empirically (the backend is NOT at fault: the raster simply
     has no coverage out there, and the overlay correctly paints nothing).

     Two independent failures, both caused by this fill and both only while the
     ficha overlay is on:

     1. IT INVENTS DATA. The highlight fills the parcel's WHOLE geometry,
        including the part the raster does not cover, and it is added AFTER the
        overlay (`MapaMapLibre.tsx`: the overlay effect runs before this one, so
        this layer sits on top). `#f59f00` at 0.35 over a satellite basemap lands
        within a few points of `#fc8d59`, the "Alto" class in `rasterLegend.ts` —
        so a no-coverage area reads as a solid high-risk zone. That is a
        fabricated reading of a legend, which is the one thing this map must
        never do.
     2. IT TINTS THE REAL CLASSES. Where the raster DOES have coverage, a 0.35
        amber wash sits over every class and pulls all of them towards orange, so
        even the honest part of the overlay is mis-read.

     The MINIMAL fix: while the overlay is active, paint the OUTLINE only. The
     line already answers the question the fill was there for ("which parcels are
     in this selection?") without asserting anything about the interior — and the
     interior is exactly what the overlay owns. With the overlay OFF the fill
     comes back untouched: there is nothing to lie about and nothing to tint, and
     a filled parcel is far easier to spot at low zoom.

     Removed, not made transparent: an `fill-opacity: 0` layer would still be a
     hit-target and would still have to be kept in sync. */
  if (overlayActive) {
    if (map.getLayer(PARCELA_HIGHLIGHT_FILL_LAYER)) {
      map.removeLayer(PARCELA_HIGHLIGHT_FILL_LAYER);
    }
  } else if (map.getLayer(PARCELA_HIGHLIGHT_FILL_LAYER)) {
    map.setFilter?.(PARCELA_HIGHLIGHT_FILL_LAYER, filter);
  } else {
    map.addLayer({
      id: PARCELA_HIGHLIGHT_FILL_LAYER,
      type: 'fill',
      source: CATASTRO_SOURCE,
      'source-layer': CATASTRO_SOURCE_LAYER,
      filter,
      paint: {
        'fill-color': PARCELA_HIGHLIGHT_COLOR,
        'fill-opacity': PARCELA_HIGHLIGHT_FILL_OPACITY,
      },
    });
  }

  if (map.getLayer(PARCELA_HIGHLIGHT_LINE_LAYER)) {
    map.setFilter?.(PARCELA_HIGHLIGHT_LINE_LAYER, filter);
  } else {
    map.addLayer({
      id: PARCELA_HIGHLIGHT_LINE_LAYER,
      type: 'line',
      source: CATASTRO_SOURCE,
      'source-layer': CATASTRO_SOURCE_LAYER,
      filter,
      paint: {
        'line-color': PARCELA_HIGHLIGHT_COLOR,
        'line-width': PARCELA_HIGHLIGHT_LINE_WIDTH,
      },
    });
  }
}

/** Convenience for a clean teardown (unmount / map removal). */
export function clearParcelaHighlightLayers(map: maplibregl.Map) {
  syncParcelaHighlightLayers(map, []);
}
