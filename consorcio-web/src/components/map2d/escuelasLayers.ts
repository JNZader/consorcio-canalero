/**
 * escuelasLayers
 *
 * Colocated registry for the single Pilar Azul (Escuelas rurales) symbol
 * layer. Mirrors the shape of `canalesLayers.ts` but narrowed to one layer
 * + one icon, since schools render as point symbols (MapLibre `symbol`
 * type) rather than line geometries.
 *
 * Consumers:
 *   - `mapLayerEffectHelpers.ts::syncEscuelasLayer` (Batch D) composes
 *     `registerEscuelaIcon` with `ensureGeoJsonSource` + `addLayer` for an
 *     idempotent mount pipeline.
 *   - `LeyendaPanel.tsx` (Batch F) references `ESCUELA_ICON_URL` to render
 *     the legend chip with the exact same raster.
 *   - `InfoPanel.tsx` (Batch E) discriminates clicks by
 *     `feature.layer.id === ESCUELAS_LAYER_ID`.
 *
 * @see design `sdd/escuelas-rurales/design` §6 MapLibre Layer Design
 */

import type { SymbolLayerSpecification } from 'maplibre-gl';
import type maplibregl from 'maplibre-gl';

import { SOURCE_IDS } from './map2dConfig';

/**
 * Source id for the static escuelas FeatureCollection.
 *
 * Batch D consolidation: now imported from `SOURCE_IDS.ESCUELAS`
 * (`map2dConfig.ts`) so the value is authoritative in exactly one place. The
 * string `'escuelas'` is ALSO the master-toggle key in
 * `defaultVisibleVectors` (design §7) — same pattern as Pilar Azul canales,
 * where the source id equals the toggle id and no translation table is
 * needed. Re-exported here so colocated consumers (`syncEscuelasLayer`,
 * InfoPanel, LeyendaPanel tests) keep a single import path.
 */
export const ESCUELAS_SOURCE_ID = SOURCE_IDS.ESCUELAS;

/** Canonical layer id — the MapLibre-native discriminator used by InfoPanel. */
export const ESCUELAS_LAYER_ID = 'escuelas-symbol' as const;

/** Registered image name referenced from the `icon-image` layout expression. */
export const ESCUELA_ICON_NAME = 'escuela' as const;

/** Public asset path for the rasterized Tabler `IconSchool` PNG. */
export const ESCUELA_ICON_URL = '/capas/escuelas/escuela-icon.png' as const;

// ---------------------------------------------------------------------------
// Icon registration (race-safe)
// ---------------------------------------------------------------------------

/**
 * Promise-wrapped `map.loadImage` with a `hasImage` guard on BOTH sides of
 * the async boundary. This prevents two things:
 *
 *   1. Re-downloading the PNG when the image is already registered
 *      (fast path — no loadImage call at all).
 *   2. A race where two concurrent registrations both see `hasImage=false`
 *      before the first callback fires, then both attempt to `addImage`.
 *      The second `addImage` would throw an "Image already exists" error
 *      from MapLibre. Double-guarding inside the callback makes the second
 *      call a silent no-op.
 *
 * Design §6.2 locks the exact sequence:
 *   `loadImage → hasImage guard → addImage(name, img, {pixelRatio: 2})`.
 */
export function registerEscuelaIcon(map: maplibregl.Map): Promise<void> {
  if (map.hasImage(ESCUELA_ICON_NAME)) return Promise.resolve();
  return new Promise<void>((resolve, reject) => {
    map.loadImage(ESCUELA_ICON_URL, (err, image) => {
      if (err) {
        reject(err);
        return;
      }
      if (!image) {
        reject(new Error('map.loadImage resolved without an image'));
        return;
      }
      // Post-load double-check — another registration may have won the race
      // between our initial `hasImage` and this callback. Safe no-op on
      // retry; no exception from MapLibre.
      if (!map.hasImage(ESCUELA_ICON_NAME)) {
        map.addImage(ESCUELA_ICON_NAME, image, { pixelRatio: 2 });
      }
      resolve();
    });
  });
}

// ---------------------------------------------------------------------------
// Layout factory — design §6.3
// ---------------------------------------------------------------------------

type SymbolLayout = NonNullable<SymbolLayerSpecification['layout']>;

/**
 * Layout for the escuelas-symbol layer.
 *
 *   - `icon-image` keys to `ESCUELA_ICON_NAME` registered above.
 *   - `icon-size` is interpolated on zoom so the icon reads at a consistent
 *     visual size across the whole legible zoom range (10–16). At z10 the
 *     map is a wide regional view — 0.4 keeps the stack of 7 schools
 *     unobtrusive; at z16 the map is parcel-level — 0.8 makes the icon
 *     obviously clickable.
 *   - `icon-allow-overlap: true` because two schools can share the same
 *     locality and we want BOTH to render, not just one.
 *   - `text-field` reads `nombre` directly from the feature properties.
 *     Label is raw (per design §2 — no humanization in Batch C, that lives
 *     in `EscuelaCard.tsx` at render time for the InfoPanel only).
 *   - `text-offset: [0, 1.2]` drops the label 1.2 em below the icon.
 *   - `text-optional: true` means the icon still draws when the label
 *     doesn't fit (e.g., at z10 with clustered labels colliding).
 */
export function buildEscuelasSymbolLayout(): SymbolLayout {
  return {
    'icon-image': ESCUELA_ICON_NAME,
    'icon-size': ['interpolate', ['linear'], ['zoom'], 10, 0.4, 16, 0.8],
    'icon-allow-overlap': true,
    'icon-anchor': 'center',
    'text-field': ['get', 'nombre'],
    'text-size': 11,
    'text-offset': [0, 1.2],
    'text-optional': true,
    'text-anchor': 'top',
    'text-allow-overlap': false,
  };
}

// ---------------------------------------------------------------------------
// Paint factory — design §6.3
// ---------------------------------------------------------------------------

type SymbolPaint = NonNullable<SymbolLayerSpecification['paint']>;

/**
 * Paint for the escuelas-symbol layer.
 *
 *   - `text-color` `#1a237e` matches the blue Pilar Azul family (slightly
 *     darker than the raster icon fill so the label reads as secondary).
 *   - `text-halo-color` `#ffffff` + `text-halo-width: 1.5` guarantees the
 *     label stays legible over any combination of Canales lines and
 *     satellite imagery underneath.
 */
export function buildEscuelasSymbolPaint(): SymbolPaint {
  return {
    'text-color': '#1a237e',
    'text-halo-color': '#ffffff',
    'text-halo-width': 1.5,
  };
}
