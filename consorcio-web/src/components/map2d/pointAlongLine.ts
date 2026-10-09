import type { Position } from 'geojson';
import distance from '@turf/distance';

/**
 * Walk a WGS84 LineString by chainage (meters) and return [lng, lat].
 * Distances past the end clamp to the last vertex.
 */
export function pointAlongLineString(coords: Position[], distanceM: number): Position | null {
  if (coords.length === 0) {
    return null;
  }
  if (coords.length === 1 || distanceM <= 0) {
    return coords[0] ?? null;
  }

  let remaining = distanceM;
  for (let index = 0; index < coords.length - 1; index += 1) {
    const start = coords[index];
    const end = coords[index + 1];
    if (!start || !end) {
      continue;
    }
    const segmentM = distance(start, end, { units: 'meters' });
    if (remaining <= segmentM) {
      const t = segmentM === 0 ? 0 : remaining / segmentM;
      return [start[0] + (end[0] - start[0]) * t, start[1] + (end[1] - start[1]) * t];
    }
    remaining -= segmentM;
  }
  return coords[coords.length - 1] ?? null;
}
