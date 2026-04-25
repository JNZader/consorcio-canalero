/**
 * kmzPlacemarks
 *
 * Feature → `<Placemark>` emitter used by `kmzBuilder`. Kept in a separate
 * module so the geometry dispatch + XML escape + name resolution can be
 * tested independently of the zip packaging.
 *
 * Supported geometries (GeoJSON → KML):
 *   - `Point`           → `<Point><coordinates>lng,lat[,z]</coordinates></Point>`
 *   - `LineString`      → `<LineString><coordinates>…</coordinates></LineString>`
 *   - `Polygon`         → `<Polygon>` with `<outerBoundaryIs>` + zero-or-more
 *                         `<innerBoundaryIs>` (holes).
 *   - `MultiPoint`      → `<MultiGeometry>` wrapping N `<Point>`.
 *   - `MultiLineString` → `<MultiGeometry>` wrapping N `<LineString>`.
 *   - `MultiPolygon`    → `<MultiGeometry>` wrapping N `<Polygon>`.
 *
 * Anything else (incl. `GeometryCollection` or a geometry missing its
 * `coordinates` array) emits a `<!-- no geometry -->` comment inside the
 * Placemark instead of throwing. Keeps bad data from crashing an export.
 *
 * Name resolution priority:
 *   1. `feature.properties.nombre`
 *   2. `feature.properties.name`
 *   3. Fallback `${entry.label} ${index + 1}` (Pair 4 pins the 1-based).
 *
 * Escuelas-only humanization: leading `"Esc. "` → `"Escuela "`, mirroring
 * `EscuelaCard.tsx`'s presentational rule so the KMZ reads the same as
 * the in-app card.
 *
 * All name text is XML-escaped (5 entities). Description is NOT emitted
 * in Phase 3 — Pair 3 adds PII strip as a defensive helper for when
 * descriptions are added later.
 */

import type {
  Feature,
  Geometry,
  LineString,
  MultiLineString,
  MultiPoint,
  MultiPolygon,
  Point,
  Polygon,
  Position,
} from 'geojson';

import type { KmzLayerEntry } from './kmzLayerRegistry';
import { stripPii } from './kmzPiiStrip';
import simplify from '@turf/simplify';

// ---------------------------------------------------------------------------
// XML escape — the 5 entity set.
// ---------------------------------------------------------------------------

/** Escape the 5 XML entities (`&`, `<`, `>`, `"`, `'`) in text content. */
export function escapeXml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

// ---------------------------------------------------------------------------
// Coordinate formatting.
// ---------------------------------------------------------------------------

/**
 * Serialize a single GeoJSON `Position` (`[lng, lat]` or `[lng, lat, z]`)
 * to the KML `lng,lat[,z]` primitive. Drops extra trailing coords defensively.
 */
function coord(pos: Position): string {
  if (pos.length >= 3 && Number.isFinite(pos[2])) {
    return `${pos[0]},${pos[1]},${pos[2]}`;
  }
  return `${pos[0]},${pos[1]}`;
}

/** Serialize an array of positions space-separated (KML convention). */
function coordList(positions: readonly Position[]): string {
  return positions.map(coord).join(' ');
}

// ---------------------------------------------------------------------------
// Per-geometry emitters.
// ---------------------------------------------------------------------------

function emitPoint(g: Point): string {
  return `<Point><coordinates>${coord(g.coordinates)}</coordinates></Point>`;
}

function emitLineString(g: LineString): string {
  return `<LineString><coordinates>${coordList(g.coordinates)}</coordinates></LineString>`;
}

function emitPolygon(g: Polygon): string {
  if (!g.coordinates || g.coordinates.length === 0) return '<!-- no geometry -->';
  const [outer, ...inner] = g.coordinates;
  const outerBlock = `<outerBoundaryIs><LinearRing><coordinates>${coordList(outer)}</coordinates></LinearRing></outerBoundaryIs>`;
  const innerBlocks = inner
    .map(
      (ring) =>
        `<innerBoundaryIs><LinearRing><coordinates>${coordList(ring)}</coordinates></LinearRing></innerBoundaryIs>`
    )
    .join('');
  return `<Polygon>${outerBlock}${innerBlocks}</Polygon>`;
}

function emitMultiPoint(g: MultiPoint): string {
  if (!g.coordinates || g.coordinates.length === 0) return '<!-- no geometry -->';
  const children = g.coordinates.map((c) => emitPoint({ type: 'Point', coordinates: c })).join('');
  return `<MultiGeometry>${children}</MultiGeometry>`;
}

function emitMultiLineString(g: MultiLineString): string {
  if (!g.coordinates || g.coordinates.length === 0) return '<!-- no geometry -->';
  const children = g.coordinates
    .map((c) => emitLineString({ type: 'LineString', coordinates: c }))
    .join('');
  return `<MultiGeometry>${children}</MultiGeometry>`;
}

function emitMultiPolygon(g: MultiPolygon): string {
  if (!g.coordinates || g.coordinates.length === 0) return '<!-- no geometry -->';
  const children = g.coordinates
    .map((c) => emitPolygon({ type: 'Polygon', coordinates: c }))
    .join('');
  return `<MultiGeometry>${children}</MultiGeometry>`;
}

/**
 * Dispatch on geometry type. Returns either a KML geometry fragment or
 * `<!-- no geometry -->` for nulls / unknowns / malformed input.
 */
function emitGeometry(geometry: Geometry | null | undefined): string {
  if (!geometry) return '<!-- no geometry -->';
  const typed = geometry as Geometry & { coordinates?: unknown };
  if (!('coordinates' in typed) || typed.coordinates == null) {
    return '<!-- no geometry -->';
  }

  switch (geometry.type) {
    case 'Point':
      return emitPoint(geometry);
    case 'LineString':
      return emitLineString(geometry);
    case 'Polygon':
      return emitPolygon(geometry);
    case 'MultiPoint':
      return emitMultiPoint(geometry);
    case 'MultiLineString':
      return emitMultiLineString(geometry);
    case 'MultiPolygon':
      return emitMultiPolygon(geometry);
    default:
      // `GeometryCollection` or anything unexpected → swallow silently.
      return '<!-- no geometry -->';
  }
}

// ---------------------------------------------------------------------------
// Name resolution.
// ---------------------------------------------------------------------------

const ESCUELAS_KEY = 'escuelas';
const ESC_PREFIX = 'Esc. ';

/**
 * Humanize a raw escuelas name: `"Esc. Foo"` → `"Escuela Foo"`. Mirrors
 * `EscuelaCard.tsx::formatEscuelaName` so the in-app card and the exported
 * KMZ read identically. Applied ONLY when `entry.key === 'escuelas'`.
 */
function humanizeEscuelasName(raw: string): string {
  if (raw.startsWith(ESC_PREFIX)) {
    return `Escuela ${raw.slice(ESC_PREFIX.length)}`;
  }
  return raw;
}

/**
 * Pick the name for a feature using the documented priority chain:
 *   non-empty properties.nombre → non-empty properties.name →
 *   `${entry.label} ${index + 1}`  (1-indexed fallback).
 *
 * Empty strings short-circuit to the fallback so features with
 * `nombre: ''` still get a meaningful `<name>` element.
 *
 * Note: `nombre` / `name` are NOT on the PII denylist, so they survive
 * `stripPii`. We call `stripPii` up-front defensively — if a future
 * change extends the denylist, names remain safe and any future
 * `<description>` / `<ExtendedData>` emission inherits sanitized props.
 */
function resolveName(feature: Feature, entry: KmzLayerEntry, index: number): string {
  const rawProps = feature.properties ?? {};
  const props = stripPii(rawProps);
  const nombre = props.nombre;
  if (typeof nombre === 'string' && nombre.length > 0) {
    return entry.key === ESCUELAS_KEY ? humanizeEscuelasName(nombre) : nombre;
  }
  const name = props.name;
  if (typeof name === 'string' && name.length > 0) {
    return entry.key === ESCUELAS_KEY ? humanizeEscuelasName(name) : name;
  }
  return `${entry.label} ${index + 1}`;
}

// ---------------------------------------------------------------------------
// Geometry simplification.
// ---------------------------------------------------------------------------

/** Count total vertex count for a GeoJSON geometry. */
function countVertices(geometry: Geometry): number {
  switch (geometry.type) {
    case 'Point':
      return 1;
    case 'MultiPoint':
      return geometry.coordinates.length;
    case 'LineString':
      return geometry.coordinates.length;
    case 'MultiLineString':
      return geometry.coordinates.reduce((sum, line) => sum + line.length, 0);
    case 'Polygon':
      return geometry.coordinates.reduce((sum, ring) => sum + ring.length, 0);
    case 'MultiPolygon':
      return geometry.coordinates.reduce(
        (sum, polygon) => sum + polygon.reduce((s, ring) => s + ring.length, 0),
        0,
      );
    default:
      return 0;
  }
}

/**
 * Simplify geometry if it has >= 100 vertices.
 * Returns the original geometry (or null/undefined) untouched when under the threshold.
 */
function maybeSimplifyGeometry(geometry: Geometry | null | undefined): Geometry | null | undefined {
  if (!geometry) return geometry;
  if (countVertices(geometry) < 100) return geometry;
  return simplify(geometry, { tolerance: 0.00005, highQuality: true, mutate: false });
}

// ---------------------------------------------------------------------------
// Public entry point.
// ---------------------------------------------------------------------------

/**
 * Emit a KML `<Placemark>` element for the given GeoJSON feature.
 *
 * `index` is the feature's position inside its source FeatureCollection,
 * used ONLY for the null-name fallback (`"${entry.label} ${index + 1}"`).
 */
export function buildPlacemark(feature: Feature, entry: KmzLayerEntry, index: number): string {
  const displayName = resolveName(feature, entry, index);
  const geometryBlock = emitGeometry(maybeSimplifyGeometry(feature.geometry));

  return `<Placemark><name>${escapeXml(displayName)}</name><styleUrl>#${entry.key}-style</styleUrl>${geometryBlock}</Placemark>`;
}
