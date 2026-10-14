import type { Feature, LineString, Position } from 'geojson';
import distance from '@turf/distance';
import length from '@turf/length';

import { mergeLineStringTramos } from '../mergeLineStringTramos';

/** Click-to-road snap. Wider than the 2 m graph snap so a freehand trace still sticks. */
export const MEASURE_SNAP_M = 25;

function asFeature(line: LineString): Feature<LineString> {
  return { type: 'Feature', geometry: line, properties: {} };
}

function projectOnLine(
  point: Position,
  line: LineString,
): { point: Position; alongM: number; offsetM: number } {
  const coords = line.coordinates;
  const first = coords[0] ?? point;
  let best = { point: first, alongM: 0, offsetM: Number.POSITIVE_INFINITY };
  let chain = 0;
  for (let index = 0; index < coords.length - 1; index += 1) {
    const start = coords[index];
    const end = coords[index + 1];
    if (!start || !end) {
      continue;
    }
    const segmentM = distance(start, end, { units: 'meters' });
    const dx = end[0] - start[0];
    const dy = end[1] - start[1];
    const len2 = dx * dx + dy * dy;
    const t =
      len2 === 0
        ? 0
        : Math.max(0, Math.min(1, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / len2));
    const projected: Position = [start[0] + t * dx, start[1] + t * dy];
    const offsetM = distance(point, projected, { units: 'meters' });
    if (offsetM < best.offsetM) {
      best = { point: projected, alongM: chain + t * segmentM, offsetM };
    }
    chain += segmentM;
  }
  return best;
}

function sliceLine(line: LineString, fromM: number, toM: number): LineString {
  const lo = Math.min(fromM, toM);
  const hi = Math.max(fromM, toM);
  const coords = line.coordinates;
  const out: Position[] = [];
  let chain = 0;
  for (let index = 0; index < coords.length - 1; index += 1) {
    const start = coords[index];
    const end = coords[index + 1];
    if (!start || !end) {
      continue;
    }
    const segmentM = distance(start, end, { units: 'meters' });
    const startM = chain;
    const endM = chain + segmentM;
    chain = endM;
    if (endM < lo - 1e-6) {
      continue;
    }
    if (startM > hi + 1e-6) {
      break;
    }
    const t0 = segmentM === 0 ? 0 : (lo - startM) / segmentM;
    const t1 = segmentM === 0 ? 1 : (hi - startM) / segmentM;
    const clip0 = Math.max(0, Math.min(1, t0));
    const clip1 = Math.max(0, Math.min(1, t1));
    const a: Position = [start[0] + (end[0] - start[0]) * clip0, start[1] + (end[1] - start[1]) * clip0];
    const b: Position = [start[0] + (end[0] - start[0]) * clip1, start[1] + (end[1] - start[1]) * clip1];
    if (out.length === 0) {
      out.push(a);
    }
    out.push(b);
  }
  return out.length >= 2 ? { type: 'LineString', coordinates: out } : line;
}

/**
 * If both ends of a distance trace sit on the road axis (selected lines, else
 * the coloured-road network), measure along that axis — same geodesic as Info.
 */
export function snapDistanceToRoads(
  drawn: LineString,
  roads: readonly Feature[],
): { meters: number; geometry: LineString; snapped: boolean } {
  const drawnFeature = asFeature(drawn);
  const fallback = {
    meters: length(drawnFeature, { units: 'meters' }),
    geometry: drawn,
    snapped: false,
  };
  const start = drawn.coordinates[0];
  const end = drawn.coordinates[drawn.coordinates.length - 1];
  if (!start || !end || drawn.coordinates.length < 2) {
    return fallback;
  }
  const lineFeatures = roads.filter((feature) => feature.geometry?.type === 'LineString');
  if (lineFeatures.length === 0) {
    return fallback;
  }
  const axis = mergeLineStringTramos(lineFeatures);
  if (!axis) {
    return fallback;
  }
  const from = projectOnLine(start, axis);
  const to = projectOnLine(end, axis);
  if (from.offsetM > MEASURE_SNAP_M || to.offsetM > MEASURE_SNAP_M) {
    return fallback;
  }
  const sliced = sliceLine(axis, from.alongM, to.alongM);
  return {
    meters: length(asFeature(sliced), { units: 'meters' }),
    geometry: sliced,
    snapped: true,
  };
}
