/**
 * escuelasLayers
 *
 * Colocated registry for the Pilar Azul (Escuelas rurales) map layers.
 *
 * Rendering model
 * ---------------
 * Seven static points are rendered with a NATIVE MapLibre `circle` layer
 * (`escuelas-symbol` — id preserved for backwards-compat with click precedence
 * tests). No image asset, no `loadImage`, no `addImage`, no Promise-shaped
 * mount path, and NO companion `symbol` label layer.
 *
 * History
 * -------
 * Batch B through F rendered the points with `type: 'symbol'` + `icon-image`
 * bound to a 64×64 rasterized Tabler `IconSchool` PNG. That approach had two
 * successive silent-fail paths:
 *
 *   1. MapLibre GL JS 4.x removed the callback overload of `map.loadImage`.
 *      The pre-v4 `loadImage(url, (err, img) => ...)` idiom silently dropped
 *      the callback and left the wrapping Promise pending forever (fixed in
 *      commit `2758ab4`).
 *   2. Even after the Promise fix, the symbol layer still failed to paint in
 *      the browser. Symbol layers hide silently whenever the referenced
 *      `icon-image` is not yet registered — any transient race, cache issue,
 *      or asset serving glitch repeats the same invisible symptom.
 *
 * For SEVEN static points, the asset pipeline buys nothing. The native
 * `circle` layer is deterministic, synchronous, and has no silent-fail modes.
 * The icon asset and its ETL export script are removed as part of this
 * refactor.
 *
 * A short-lived companion text-only `symbol` layer was also added to render
 * the `nombre` property as a text label beneath each circle. That layer was
 * removed after live testing surfaced a hard MapLibre error: any `symbol`
 * layer with `text-field` requires a `glyphs` URL on the map style, and this
 * deployment deliberately does NOT configure a glyphs endpoint. Rather than
 * wire up glyph infra for a single text-only label, the layer is dropped
 * entirely — the feature name is already shown on click via `EscuelaCard`
 * inside `InfoPanel`, which is the designed UX.
 *
 * Consumers
 * ---------
 *   - `mapLayerEffectHelpers.ts::syncEscuelasLayer` composes
 *     `ensureGeoJsonSource` + circle `addLayer` for an idempotent, SYNCHRONOUS
 *     mount pipeline.
 *   - `LeyendaPanel.tsx` renders a 12×12 blue circle swatch matching the map
 *     `circle-color` / `circle-stroke` paint (no image reference).
 *   - `InfoPanel.tsx` discriminates clicks via
 *     `feature.layer.id === ESCUELAS_LAYER_ID` — the circle layer is the
 *     click target.
 */

import type { CircleLayerSpecification } from 'maplibre-gl';

import { SOURCE_IDS } from './map2dConfig';

/**
 * Source id for the static escuelas FeatureCollection.
 *
 * Imported from `SOURCE_IDS.ESCUELAS` (`map2dConfig.ts`) so the value is
 * authoritative in exactly one place. The string `'escuelas'` is ALSO the
 * master-toggle key in `defaultVisibleVectors` — same pattern as Pilar Azul
 * canales, where the source id equals the toggle id and no translation table
 * is needed. Re-exported here so colocated consumers (`syncEscuelasLayer`,
 * InfoPanel, LeyendaPanel tests) keep a single import path.
 */
export const ESCUELAS_SOURCE_ID = SOURCE_IDS.ESCUELAS;

/**
 * Canonical layer id — the MapLibre-native discriminator used by InfoPanel.
 *
 * The `-symbol` suffix is RETAINED for backwards compatibility with the click
 * precedence ordering pinned at index 10 in
 * `useMapInteractionEffectsClickableLayers.test.ts` and the InfoPanel
 * discriminator branch. Renaming the id would cascade into multiple tests and
 * the `InfoPanel` routing without any visual payoff.
 */
export const ESCUELAS_LAYER_ID = 'escuelas-symbol' as const;

// ---------------------------------------------------------------------------
// Circle paint / layout factories
// ---------------------------------------------------------------------------

type CirclePaint = NonNullable<CircleLayerSpecification['paint']>;

/**
 * Paint for the `escuelas-symbol` circle layer.
 *
 *   - `circle-radius` is interpolated on zoom so the points stay legible
 *     across the whole useful zoom range (z10 regional → z16 parcel-level).
 *   - `circle-color` `#1976d2` matches the Pilar Azul blue family (same
 *     family used by the old rasterized icon — visual continuity for the
 *     user).
 *   - `circle-stroke-color` white + `circle-stroke-width: 2` guarantees the
 *     point reads against any basemap (satellite imagery, OSM light, DEM
 *     overlays).
 */
export function buildEscuelasCirclePaint(): CirclePaint {
  return {
    'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 4, 16, 8],
    'circle-color': '#1976d2',
    'circle-stroke-color': '#ffffff',
    'circle-stroke-width': 2,
  };
}
