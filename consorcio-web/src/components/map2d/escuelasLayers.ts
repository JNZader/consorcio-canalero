/**
 * escuelasLayers
 *
 * Colocated registry for the Pilar Azul (Escuelas rurales) map layers.
 *
 * Rendering model
 * ---------------
 * Seven static points are rendered with a NATIVE MapLibre `circle` layer
 * (`escuelas-symbol` — id preserved for backwards-compat with click precedence
 * tests) plus a companion `symbol` layer (`escuelas-label`) that carries only
 * the text label. No image asset, no `loadImage`, no `addImage`, no
 * Promise-shaped mount path.
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
 * Consumers
 * ---------
 *   - `mapLayerEffectHelpers.ts::syncEscuelasLayer` composes
 *     `ensureGeoJsonSource` + circle `addLayer` + label `addLayer` for an
 *     idempotent, SYNCHRONOUS mount pipeline.
 *   - `LeyendaPanel.tsx` renders a 12×12 blue circle swatch matching the map
 *     `circle-color` / `circle-stroke` paint (no image reference).
 *   - `InfoPanel.tsx` discriminates clicks via
 *     `feature.layer.id === ESCUELAS_LAYER_ID` — the circle layer is the
 *     click target; the label layer is not registered as clickable.
 */

import type { CircleLayerSpecification, SymbolLayerSpecification } from 'maplibre-gl';

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

/**
 * Companion text-label layer id.
 *
 * A second layer (`type: 'symbol'`, text-only — no `icon-image`) draws the
 * `nombre` property under the circle. Keeping the label in its own layer
 * means the circle layer stays a pure click target and the label cannot
 * accidentally steal a click.
 */
export const ESCUELAS_LABEL_LAYER_ID = 'escuelas-label' as const;

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

// ---------------------------------------------------------------------------
// Label (companion symbol) layout / paint factories
// ---------------------------------------------------------------------------

type SymbolLayout = NonNullable<SymbolLayerSpecification['layout']>;
type SymbolPaint = NonNullable<SymbolLayerSpecification['paint']>;

/**
 * Layout for the companion `escuelas-label` symbol layer.
 *
 *   - `text-field` reads `nombre` directly from the feature properties.
 *     Label is raw (same rule as before — no humanization on the map; that
 *     lives in `EscuelaCard.tsx` at render time for the InfoPanel only).
 *   - `text-offset: [0, 1.2]` drops the label 1.2 em below the anchor so it
 *     sits under the circle dot.
 *   - `text-optional: true` means the layer still renders when the label
 *     collides at very low zoom (the circle is the primary signal).
 */
export function buildEscuelasLabelLayout(): SymbolLayout {
  return {
    'text-field': ['get', 'nombre'],
    'text-size': 11,
    'text-offset': [0, 1.2],
    'text-optional': true,
    'text-anchor': 'top',
    'text-allow-overlap': false,
  };
}

/**
 * Paint for the companion `escuelas-label` symbol layer.
 *
 *   - `text-color` `#1a237e` matches the Pilar Azul blue family (slightly
 *     darker than the circle fill so the label reads as secondary).
 *   - `text-halo-color` white + `text-halo-width: 1.5` guarantees the label
 *     stays legible over any combination of canales lines and satellite
 *     imagery underneath.
 */
export function buildEscuelasLabelPaint(): SymbolPaint {
  return {
    'text-color': '#1a237e',
    'text-halo-color': '#ffffff',
    'text-halo-width': 1.5,
  };
}
