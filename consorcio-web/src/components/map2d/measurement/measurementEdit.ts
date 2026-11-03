import type { LineString, Polygon } from 'geojson';

/** Bearing from north, degrees clockwise, of the last segment. */
export function rumboDegrees(from: readonly [number, number], to: readonly [number, number]): number {
  const lat1 = (from[1] * Math.PI) / 180;
  const lat2 = (to[1] * Math.PI) / 180;
  const dLon = ((to[0] - from[0]) * Math.PI) / 180;
  const y = Math.sin(dLon) * Math.cos(lat2);
  const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLon);
  return (Math.atan2(y, x) * 180) / Math.PI;
}

export function formatRumbo(degrees: number): string {
  const wrapped = ((degrees % 360) + 360) % 360;
  return `rumbo ${wrapped.toFixed(0)}°`;
}

export function dropLastVertex(coordinates: readonly (readonly number[])[]): number[][] | null {
  if (coordinates.length <= 2) return null;
  return coordinates.slice(0, -1).map((pair) => [pair[0]!, pair[1]!]);
}

export function dropLastPolygonVertex(
  ring: readonly (readonly number[])[]
): number[][] | null {
  if (ring.length < 3) return null;
  const first = ring[0]!;
  const last = ring[ring.length - 1]!;
  const isClosed = ring.length >= 4 && first[0] === last[0] && first[1] === last[1];
  const openVertices = (isClosed ? ring.slice(0, -1) : ring).map((pair) => [pair[0]!, pair[1]!]);
  if (openVertices.length <= 3) return null;
  const trimmed = openVertices.slice(0, -1);
  return isClosed ? [...trimmed, [trimmed[0]![0]!, trimmed[0]![1]!]] : trimmed;
}

export function moveLineVertex(line: LineString, index: number, next: readonly [number, number]): LineString {
  const coordinates = line.coordinates.map((pair, current) =>
    current === index ? [next[0], next[1]] : [pair[0]!, pair[1]!]
  );
  return { type: 'LineString', coordinates };
}

export function movePolygonVertex(
  polygon: Polygon,
  index: number,
  next: readonly [number, number]
): Polygon {
  const ring = polygon.coordinates[0] ?? [];
  const coordinates = ring.map((pair, current) => {
    const atClose = current === ring.length - 1 && index === 0;
    if (current === index || atClose) return [next[0], next[1]];
    return [pair[0]!, pair[1]!];
  });
  return { type: 'Polygon', coordinates: [coordinates] };
}
