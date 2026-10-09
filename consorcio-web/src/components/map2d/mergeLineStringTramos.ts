import type { Feature, LineString, Position } from 'geojson';

function isLineString(geometry: Feature['geometry']): geometry is LineString {
  return geometry?.type === 'LineString' && geometry.coordinates.length >= 2;
}

function sameVertex(a: Position, b: Position): boolean {
  return Math.abs(a[0] - b[0]) < 1e-8 && Math.abs(a[1] - b[1]) < 1e-8;
}

function attachPiece(chain: Position[], piece: Position[]): Position[] | null {
  const head = chain[0];
  const tail = chain[chain.length - 1];
  const start = piece[0];
  const end = piece[piece.length - 1];
  if (!head || !tail || !start || !end) {
    return null;
  }
  if (sameVertex(tail, start)) {
    return [...chain, ...piece.slice(1)];
  }
  if (sameVertex(tail, end)) {
    return [...chain, ...[...piece].reverse().slice(1)];
  }
  if (sameVertex(head, end)) {
    return [...piece.slice(0, -1), ...chain];
  }
  if (sameVertex(head, start)) {
    return [...[...piece].reverse().slice(0, -1), ...chain];
  }
  return null;
}

/**
 * Walk shared vertices into one LineString. Catalog order is ignored so a
 * split road (T269-03) does not jump across the map and blow the 25 km cap.
 * Pieces that do not touch the chain are left out.
 */
export function mergeLineStringTramos(features: readonly Feature[]): LineString | null {
  const remaining = features
    .filter((feature) => isLineString(feature.geometry))
    .map((feature) => [...(feature.geometry as LineString).coordinates]);
  const first = remaining.shift();
  if (!first) {
    return null;
  }
  let chain = first;
  let attached = true;
  while (attached && remaining.length > 0) {
    attached = false;
    for (let index = 0; index < remaining.length; index += 1) {
      const piece = remaining[index];
      if (!piece) {
        continue;
      }
      const next = attachPiece(chain, piece);
      if (!next) {
        continue;
      }
      chain = next;
      remaining.splice(index, 1);
      attached = true;
      break;
    }
  }
  if (chain.length < 2) {
    return null;
  }
  return { type: 'LineString', coordinates: chain };
}
