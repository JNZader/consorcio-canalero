import type { Feature, Position } from 'geojson';
import distance from '@turf/distance';

const DEFAULT_MAX_M = 80;

function distPointToSegM(point: Position, start: Position, end: Position): number {
  const ax = start[0];
  const ay = start[1];
  const bx = end[0];
  const by = end[1];
  if (ax == null || ay == null || bx == null || by == null) {
    return Number.POSITIVE_INFINITY;
  }
  const dx = bx - ax;
  const dy = by - ay;
  const len2 = dx * dx + dy * dy;
  if (len2 === 0) {
    return distance(point, start, { units: 'meters' });
  }
  const px = point[0] ?? 0;
  const py = point[1] ?? 0;
  const t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / len2));
  const along: Position = [ax + t * dx, ay + t * dy];
  return distance(point, along, { units: 'meters' });
}

/** Closest LineString in `features` to a WGS84 point, or null if farther than `maxM`. */
export function nearestLineStringIndex(
  features: readonly Feature[],
  lon: number,
  lat: number,
  maxM = DEFAULT_MAX_M,
): number | null {
  let bestIdx: number | null = null;
  let best = maxM;
  const point: Position = [lon, lat];
  features.forEach((feature, index) => {
    const geometry = feature.geometry;
    if (geometry?.type !== 'LineString' || geometry.coordinates.length < 2) {
      return;
    }
    for (let i = 1; i < geometry.coordinates.length; i += 1) {
      const start = geometry.coordinates[i - 1];
      const end = geometry.coordinates[i];
      if (!start || !end) {
        continue;
      }
      const metres = distPointToSegM(point, start, end);
      if (metres < best) {
        best = metres;
        bestIdx = index;
      }
    }
  });
  return bestIdx;
}
