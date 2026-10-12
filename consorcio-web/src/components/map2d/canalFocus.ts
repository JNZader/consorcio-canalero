import type { Feature, FeatureCollection, Geometry, Position } from 'geojson';

export type CanalFocusBbox = [number, number, number, number];

const TOGGLE_PREFIX = /^canal_(relevado|propuesto)_/;

/** `canal_relevado_foo_bar` → `foo-bar` (index slug). */
export function canalSlugFromToggleId(toggleId: string): string {
  return toggleId.replace(TOGGLE_PREFIX, '').replace(/_/g, '-');
}

export function featureMatchesCanalToggle(feature: Feature, toggleId: string): boolean {
  const slug = canalSlugFromToggleId(toggleId);
  const props = (feature.properties ?? {}) as Record<string, unknown>;
  const candidates = [feature.id, props.id, props.gid, props.slug, props.codigo];
  return candidates.some((value) => {
    if (value == null) return false;
    const text = String(value);
    return text === slug || text === toggleId || text.replace(/-/g, '_') === toggleId.replace(TOGGLE_PREFIX, '');
  });
}

export function findCanalFeature(
  collections: readonly FeatureCollection[],
  toggleId: string,
): Feature | null {
  for (const collection of collections) {
    for (const feature of collection.features) {
      if (featureMatchesCanalToggle(feature, toggleId)) return feature;
    }
  }
  return null;
}

function walkPositions(geometry: Geometry, visit: (position: Position) => void): void {
  if (geometry.type === 'GeometryCollection') {
    for (const part of geometry.geometries) walkPositions(part, visit);
    return;
  }
  if (geometry.type === 'Point') {
    visit(geometry.coordinates);
    return;
  }
  if (geometry.type === 'MultiPoint' || geometry.type === 'LineString') {
    for (const position of geometry.coordinates) visit(position);
    return;
  }
  if (geometry.type === 'MultiLineString' || geometry.type === 'Polygon') {
    for (const ring of geometry.coordinates) {
      for (const position of ring) visit(position);
    }
    return;
  }
  for (const polygon of geometry.coordinates) {
    for (const ring of polygon) {
      for (const position of ring) visit(position);
    }
  }
}

export function bboxFromGeometry(geometry: Geometry | null | undefined): CanalFocusBbox | null {
  if (!geometry) return null;
  let minX = Number.POSITIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;
  walkPositions(geometry, (position) => {
    const x = position[0];
    const y = position[1];
    if (!Number.isFinite(x) || !Number.isFinite(y)) return;
    minX = Math.min(minX, x);
    minY = Math.min(minY, y);
    maxX = Math.max(maxX, x);
    maxY = Math.max(maxY, y);
  });
  if (!Number.isFinite(minX) || !Number.isFinite(minY) || !Number.isFinite(maxX) || !Number.isFinite(maxY)) {
    return null;
  }
  return [minX, minY, maxX, maxY];
}

export function canalFocusBbox(
  collections: readonly FeatureCollection[],
  toggleId: string,
): CanalFocusBbox | null {
  const feature = findCanalFeature(collections, toggleId);
  return feature ? bboxFromGeometry(feature.geometry) : null;
}

export const CANAL_FOCUS_PADDING = { top: 40, bottom: 40, left: 40, right: 40 } as const;

export function canalCollections(
  relevados: FeatureCollection | null | undefined,
  propuestas: FeatureCollection | null | undefined,
): FeatureCollection[] {
  return [relevados, propuestas].filter(
    (collection): collection is FeatureCollection => collection != null,
  );
}

export function fitMapToCanal(
  map: { fitBounds: (bounds: [[number, number], [number, number]], options: object) => void } | null | undefined,
  collections: readonly FeatureCollection[],
  toggleId: string,
): boolean {
  const box = canalFocusBbox(collections, toggleId);
  if (!box || !map) return false;
  map.fitBounds(
    [
      [box[0], box[1]],
      [box[2], box[3]],
    ],
    { padding: CANAL_FOCUS_PADDING, duration: 600 },
  );
  return true;
}
