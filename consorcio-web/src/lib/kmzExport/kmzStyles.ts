/**
 * kmzStyles
 *
 * Phase 2 of the `kmz-export-all-layers` change. Builds the KML `<Style>`
 * blocks that live once at the top of `doc.kml` and are referenced by
 * every Placemark via `<styleUrl>#<key>-style</styleUrl>`.
 *
 * KML color convention
 * --------------------
 * KML colors are `AABBGGRR` (alpha first, then BGR REVERSED from standard
 * web hex). See the KML Reference §ColorStyle:
 *   https://developers.google.com/kml/documentation/kmlreference#colorstyle
 *
 *   Web hex:  #RRGGBB[AA]
 *   KML hex:   AABBGGRR
 *
 * Example: `#1976d2` (web) → `ffd27619` (KML, alpha `ff`).
 *
 * Geometry dispatch
 * -----------------
 *   - `point`   → `<IconStyle>` with a Google-hosted `placemark_circle.png`
 *                 tinted by `<color>`.
 *   - `line`    → `<LineStyle>` only (width 3).
 *   - `polygon` → BOTH `<LineStyle>` (stroke, alpha `ff`) AND `<PolyStyle>`
 *                 (fill, alpha `88`). Catastro is an outline-only exception
 *                 (fill alpha `00`). Canales propuestos is documented-solid
 *                 because KML has no native dash pattern.
 *
 * Pure strings — no external libs. Each builder is exported for testability;
 * the orchestrator uses `buildKmzStyles(registry)`.
 */

import type { KmzLayerEntry } from './kmzLayerRegistry';

// ---------------------------------------------------------------------------
// Primitive: hex → KML color.
// ---------------------------------------------------------------------------

/** Google-hosted solid-circle icon. Used since ~2009 in KML samples —
 *  minimal availability risk vs. hosting our own asset inside the KMZ. */
const PLACEMARK_CIRCLE_HREF = 'http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png';

/** Default alpha when the input hex has no embedded alpha and no override. */
const DEFAULT_ALPHA = 'ff';

/** Semi-transparent polygon fill convention for overlay layers. */
const POLYGON_FILL_ALPHA = '88';

/** Fully-opaque alpha for strokes and points. */
const FULL_ALPHA = 'ff';

/** Outline-only alpha — used by catastro where the fill would obscure
 *  the underlying base map. */
const TRANSPARENT_ALPHA = '00';

/** Keys whose polygon style must NOT paint a fill (outline-only).
 *  Kept as a tiny set so the dispatch stays readable; extend if another
 *  polygon layer ever joins catastro in this convention. */
const OUTLINE_ONLY_POLYGON_KEYS = new Set<string>(['catastro']);

const HEX_RE = /^[0-9a-fA-F]+$/;

/**
 * Convert a web hex color (`#RRGGBB` or `#RRGGBBAA`, leading `#` optional)
 * to KML's `AABBGGRR` form.
 *
 *   - `alphaOverride` wins over any embedded alpha.
 *   - Missing alpha (and no override) → `ff` (fully opaque).
 *   - Invalid input throws — colors are pinned by tests, so a silent
 *     fallback would mask real bugs.
 *
 * @param hex            `#RRGGBB` or `#RRGGBBAA` (or the same without `#`).
 * @param alphaOverride  Two hex chars (`00`–`ff`). Optional.
 */
export function webHexToKmlColor(hex: string, alphaOverride?: string): string {
  const stripped = hex.startsWith('#') ? hex.slice(1) : hex;

  if (!HEX_RE.test(stripped) || (stripped.length !== 6 && stripped.length !== 8)) {
    throw new Error(`webHexToKmlColor: invalid hex "${hex}" — expected #RRGGBB or #RRGGBBAA`);
  }

  const r = stripped.slice(0, 2).toLowerCase();
  const g = stripped.slice(2, 4).toLowerCase();
  const b = stripped.slice(4, 6).toLowerCase();
  const embeddedAlpha = stripped.length === 8 ? stripped.slice(6, 8).toLowerCase() : undefined;

  const alpha = (alphaOverride ?? embeddedAlpha ?? DEFAULT_ALPHA).toLowerCase();
  if (!HEX_RE.test(alpha) || alpha.length !== 2) {
    throw new Error(
      `webHexToKmlColor: invalid alphaOverride "${alphaOverride}" — expected two hex chars`
    );
  }

  // KML expects AABBGGRR.
  return `${alpha}${b}${g}${r}`;
}

// ---------------------------------------------------------------------------
// Per-geometry builders — each returns a self-contained <Style> element.
// ---------------------------------------------------------------------------

/**
 * Point style — colored circle icon. Used for `escuelas` + `ypf-estacion-bombeo`.
 * The `<color>` element tints `placemark_circle.png` (a white circle on
 * transparent — multiplying with `color` yields the registry hue).
 */
export function buildPointStyle(entry: KmzLayerEntry): string {
  const color = webHexToKmlColor(entry.color, FULL_ALPHA);
  return `<Style id="${entry.key}-style"><IconStyle><color>${color}</color><scale>1.1</scale><Icon><href>${PLACEMARK_CIRCLE_HREF}</href></Icon></IconStyle></Style>`;
}

/**
 * Line style — width 3. Note: KML has NO native dash pattern, so
 * `canales_propuestos` (which is dashed on MapLibre) emits as solid here.
 * The representative color hint (Etapa 1 red) keeps the differentiation
 * visually — see proposal §5 and registry inline comments.
 */
export function buildLineStyle(entry: KmzLayerEntry): string {
  const color = webHexToKmlColor(entry.color, FULL_ALPHA);
  return `<Style id="${entry.key}-style"><LineStyle><color>${color}</color><width>3</width></LineStyle></Style>`;
}

/**
 * Polygon style — LineStyle (stroke, fully opaque) + PolyStyle (fill,
 * semi-transparent by default; fully transparent for catastro).
 * `strokeColor` defaults to `color` when missing.
 */
export function buildPolygonStyle(entry: KmzLayerEntry): string {
  const strokeHex = entry.strokeColor ?? entry.color;
  const strokeColor = webHexToKmlColor(strokeHex, FULL_ALPHA);

  // Catastro exception: outline-only — fill fully transparent so the
  // underlying MapLibre basemap (or Google Earth base) stays readable.
  const fillAlpha = OUTLINE_ONLY_POLYGON_KEYS.has(entry.key)
    ? TRANSPARENT_ALPHA
    : POLYGON_FILL_ALPHA;
  const fillColor = webHexToKmlColor(entry.color, fillAlpha);

  return `<Style id="${entry.key}-style"><LineStyle><color>${strokeColor}</color><width>2</width></LineStyle><PolyStyle><color>${fillColor}</color><fill>1</fill><outline>1</outline></PolyStyle></Style>`;
}

// ---------------------------------------------------------------------------
// Dispatcher.
// ---------------------------------------------------------------------------

/**
 * Build ALL style blocks for the given registry, in registry order.
 * Caller concatenates this directly into `<Document>…</Document>`.
 */
export function buildKmzStyles(registry: readonly KmzLayerEntry[]): string {
  return registry
    .map((entry) => {
      switch (entry.geometryHint) {
        case 'point':
          return buildPointStyle(entry);
        case 'line':
          return buildLineStyle(entry);
        case 'polygon':
          return buildPolygonStyle(entry);
        default: {
          // Exhaustiveness guard — KmzLayerGeometry is a closed union, but
          // if somebody adds a new variant the compiler will flag this.
          const _exhaustive: never = entry.geometryHint;
          throw new Error(
            `buildKmzStyles: unknown geometryHint for key "${entry.key}" — ${String(_exhaustive)}`
          );
        }
      }
    })
    .join('');
}
