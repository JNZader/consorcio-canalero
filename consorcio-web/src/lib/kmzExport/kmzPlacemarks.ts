/**
 * kmzPlacemarks
 *
 * Feature → `<Placemark>` emitter used by `kmzBuilder`. Kept in a separate
 * module so the geometry dispatch + XML escape + name resolution can be
 * tested independently of the zip packaging.
 *
 * STUB — Pair 1: emits a minimal `<Placemark>` so the builder contract
 * tests pass. Pair 2 replaces this with the real geometry emitter.
 *
 * Why the stub exists: the builder tests pin "at least one <Placemark>
 * inside a Folder" but do NOT yet pin the geometry serialization. Pair 2
 * tests will pin the geometry, and Pair 2 GREEN rewrites this function.
 */

import type { Feature } from 'geojson';

import type { KmzLayerEntry } from './kmzLayerRegistry';

/**
 * Emit a KML `<Placemark>` element for the given GeoJSON feature.
 *
 * Pair 1 STUB — minimal structure. The index arg is reserved for the
 * Pair 4 null-name fallback; accepted now so the builder call site is
 * already on the final signature.
 */
export function buildPlacemark(
  _feature: Feature,
  entry: KmzLayerEntry,
  _index: number,
): string {
  return (
    `<Placemark>` +
    `<name>stub</name>` +
    `<styleUrl>#${entry.key}-style</styleUrl>` +
    `</Placemark>`
  );
}
