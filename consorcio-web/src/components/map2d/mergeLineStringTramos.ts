import type { Feature, LineString, Position } from 'geojson';

function isLineString(geometry: Feature['geometry']): geometry is LineString {
  return geometry?.type === 'LineString' && geometry.coordinates.length >= 2;
}

function sameVertex(a: Position, b: Position): boolean {
  return a[0] === b[0] && a[1] === b[1];
}

function vertexDistance2(a: Position, b: Position): number {
  const dx = a[0] - b[0];
  const dy = a[1] - b[1];
  return dx * dx + dy * dy;
}

function orientedCoordinates(previousEnd: Position, coords: Position[]): Position[] {
  const start = coords[0];
  const end = coords[coords.length - 1];
  if (!start || !end) {
    return coords;
  }
  const oriented =
    vertexDistance2(previousEnd, end) < vertexDistance2(previousEnd, start)
      ? [...coords].reverse()
      : coords;
  const first = oriented[0];
  if (first && sameVertex(previousEnd, first)) {
    return oriented.slice(1);
  }
  return oriented;
}

/** Concatenate selected LineStrings in click order into one profile geometry. */
export function mergeLineStringTramos(features: readonly Feature[]): LineString | null {
  const lines = features.filter((feature) => isLineString(feature.geometry));
  const first = lines[0];
  if (!first || !isLineString(first.geometry)) {
    return null;
  }
  const coordinates: Position[] = [...first.geometry.coordinates];
  for (const line of lines.slice(1)) {
    if (!isLineString(line.geometry)) {
      continue;
    }
    const next = line.geometry.coordinates;
    const previousEnd = coordinates[coordinates.length - 1];
    if (!previousEnd) {
      coordinates.push(...next);
      continue;
    }
    coordinates.push(...orientedCoordinates(previousEnd, next));
  }
  if (coordinates.length < 2) {
    return null;
  }
  return { type: 'LineString', coordinates };
}
