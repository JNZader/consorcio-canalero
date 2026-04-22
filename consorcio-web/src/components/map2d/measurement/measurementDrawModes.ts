/**
 * Measurement draw modes — centralised style + options for the DEDICATED
 * mapbox-gl-draw instance used by the measurement toolbar.
 *
 * This draw instance is intentionally separate from `LineDrawControl`'s
 * draw: measurements are ephemeral, canales (in `LineDrawControl`) are
 * persistent form state. Keeping two separate `MapboxDraw` instances
 * means `clear()` on the measurement side NEVER touches canales, and
 * styles can diverge freely.
 *
 * Visual design decisions:
 * - Accent: Mantine orange 6 (`#fd7e14`). Distinct from the canales blue
 *   (`#1971c2`) so users can tell measurements apart from canales at a
 *   glance even when both layers are on screen.
 * - Lines use `line-width: 3` (canales use 4) so a canal drawn on top of
 *   a measurement stays legible.
 * - Polygon fills use `fill-opacity: 0.2` so the basemap stays visible
 *   while the shape is being drawn — measurement polygons are ephemeral.
 * - Vertex circles are white-stroked on orange so they're clickable on
 *   both satellite and OSM basemaps.
 *
 * The shape of each style entry mirrors MapboxDraw's theme format (see
 * @types/mapbox__mapbox-gl-draw `ThemeLayerId` union). We use plain
 * object literals here rather than `as const` on each entry because
 * `MapboxDrawOptions['styles']` is typed `object[]`.
 */

import MapboxDraw from '@mapbox/mapbox-gl-draw';

// `MapboxDrawOptions['styles']` is typed as `object[]`, so we expose a
// permissive alias rather than inventing our own narrow type.
type DrawStyle = object;

const ACCENT = '#fd7e14'; // Mantine orange 6 — measurement accent
const ACCENT_STRONG = '#e8590c'; // Mantine orange 8 — active/selected
const WHITE = '#ffffff';

export const MEASUREMENT_DRAW_STYLES: DrawStyle[] = [
  // ── Polygon fills ─────────────────────────────────────────────────────
  {
    id: 'gl-draw-polygon-fill-measurement',
    type: 'fill',
    filter: ['all', ['==', '$type', 'Polygon'], ['!=', 'mode', 'static']],
    paint: {
      'fill-color': ACCENT,
      'fill-outline-color': ACCENT_STRONG,
      'fill-opacity': 0.2,
    },
  },
  // ── Polygon strokes ───────────────────────────────────────────────────
  {
    id: 'gl-draw-polygon-stroke-measurement',
    type: 'line',
    filter: ['all', ['==', '$type', 'Polygon'], ['!=', 'mode', 'static']],
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: {
      'line-color': ACCENT,
      'line-width': 3,
      'line-opacity': 0.95,
    },
  },
  // ── Line strings ──────────────────────────────────────────────────────
  {
    id: 'gl-draw-line-measurement',
    type: 'line',
    filter: ['all', ['==', '$type', 'LineString'], ['!=', 'mode', 'static']],
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: {
      'line-color': ACCENT,
      'line-width': 3,
      'line-opacity': 0.95,
    },
  },
  // ── Vertices (circles sitting on polygon/line corners) ────────────────
  {
    id: 'gl-draw-polygon-and-line-vertex-measurement',
    type: 'circle',
    filter: ['all', ['==', 'meta', 'vertex'], ['==', '$type', 'Point']],
    paint: {
      'circle-radius': 5,
      'circle-color': ACCENT,
      'circle-stroke-width': 2,
      'circle-stroke-color': WHITE,
    },
  },
  // ── Active vertex (bigger so the user can see where they clicked) ─────
  {
    id: 'gl-draw-vertex-active-measurement',
    type: 'circle',
    filter: [
      'all',
      ['==', 'meta', 'vertex'],
      ['==', '$type', 'Point'],
      ['==', 'active', 'true'],
    ],
    paint: {
      'circle-radius': 7,
      'circle-color': ACCENT_STRONG,
      'circle-stroke-width': 2,
      'circle-stroke-color': WHITE,
    },
  },
  // ── Midpoints (MapboxDraw adds these between vertices for editing) ────
  {
    id: 'gl-draw-polygon-midpoint-measurement',
    type: 'circle',
    filter: ['all', ['==', '$type', 'Point'], ['==', 'meta', 'midpoint']],
    paint: {
      'circle-radius': 3,
      'circle-color': ACCENT,
      'circle-opacity': 0.7,
    },
  },
];

export const MEASUREMENT_DRAW_OPTIONS: MapboxDraw.MapboxDrawOptions = {
  displayControlsDefault: false,
  controls: {},
  styles: MEASUREMENT_DRAW_STYLES,
  userProperties: true,
};

/**
 * Instantiates a fresh MapboxDraw configured for measurement.
 *
 * Always returns a NEW instance — the hook manages lifecycle, so the
 * factory is intentionally stateless. Never share the returned instance
 * across components; add it to exactly one map, then remove it.
 */
export function createMeasurementDraw(): MapboxDraw {
  return new MapboxDraw(MEASUREMENT_DRAW_OPTIONS);
}
