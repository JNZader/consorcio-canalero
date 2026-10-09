import type { Feature, LineString, Position } from 'geojson';
import distance from '@turf/distance';

const SNAP_M = 2;

function isLineString(geometry: Feature['geometry']): geometry is LineString {
  return geometry?.type === 'LineString' && geometry.coordinates.length >= 2;
}

function pieceLengthM(coords: Position[]): number {
  let total = 0;
  for (let index = 1; index < coords.length; index += 1) {
    const previous = coords[index - 1];
    const current = coords[index];
    if (!previous || !current) {
      continue;
    }
    total += distance(previous, current, { units: 'meters' });
  }
  return total;
}

function clusterEndpoints(points: Position[]): number[] {
  const parent = points.map((_, index) => index);
  const find = (index: number): number => {
    const root = parent[index];
    if (root === undefined || root === index) {
      return index;
    }
    parent[index] = find(root);
    return parent[index] ?? index;
  };
  for (let i = 0; i < points.length; i += 1) {
    for (let j = i + 1; j < points.length; j += 1) {
      const a = points[i];
      const b = points[j];
      if (!a || !b) {
        continue;
      }
      if (distance(a, b, { units: 'meters' }) <= SNAP_M) {
        parent[find(j)] = find(i);
      }
    }
  }
  const compact = new Map<number, number>();
  let next = 0;
  return points.map((_, index) => {
    const root = find(index);
    const existing = compact.get(root);
    if (existing !== undefined) {
      return existing;
    }
    compact.set(root, next);
    next += 1;
    return next - 1;
  });
}

type Edge = {
  readonly id: number;
  readonly a: number;
  readonly b: number;
  readonly length: number;
  readonly coords: Position[];
};

function buildEdges(pieces: Position[][]): {
  edges: Edge[];
  clusterOf: (point: Position) => number | null;
} {
  const points: Position[] = [];
  const ends: Array<{ start: number; end: number; coords: Position[] }> = [];
  for (const coords of pieces) {
    const start = coords[0];
    const end = coords[coords.length - 1];
    if (!start || !end) {
      continue;
    }
    ends.push({ start: points.length, end: points.length + 1, coords });
    points.push(start, end);
  }
  const cluster = clusterEndpoints(points);
  const byPair = new Map<string, Edge>();
  let nextId = 0;
  for (const piece of ends) {
    const a = cluster[piece.start];
    const b = cluster[piece.end];
    if (a === undefined || b === undefined || a === b) {
      continue;
    }
    const key = a < b ? `${a}:${b}` : `${b}:${a}`;
    const length = pieceLengthM(piece.coords);
    const coords = cluster[piece.start] === a ? piece.coords : [...piece.coords].reverse();
    const existing = byPair.get(key);
    if (!existing || length > existing.length) {
      byPair.set(key, { id: existing?.id ?? nextId, a, b, length, coords });
      if (!existing) {
        nextId += 1;
      }
    }
  }
  const clusterOf = (point: Position): number | null => {
    for (let index = 0; index < points.length; index += 1) {
      const candidate = points[index];
      if (candidate && distance(candidate, point, { units: 'meters' }) <= SNAP_M) {
        return cluster[index] ?? null;
      }
    }
    return null;
  };
  return { edges: [...byPair.values()], clusterOf };
}

function otherNode(edge: Edge, node: number): number {
  return edge.a === node ? edge.b : edge.a;
}

function coordsFrom(edge: Edge, node: number): Position[] {
  return edge.a === node ? edge.coords : [...edge.coords].reverse();
}

function longestExtension(
  node: number,
  adj: Map<number, Edge[]>,
  usedEdges: Set<number>,
  usedNodes: Set<number>,
): { coords: Position[]; length: number } {
  let best = { coords: [] as Position[], length: 0 };
  for (const edge of adj.get(node) ?? []) {
    if (usedEdges.has(edge.id)) {
      continue;
    }
    const next = otherNode(edge, node);
    if (usedNodes.has(next)) {
      continue;
    }
    usedEdges.add(edge.id);
    usedNodes.add(next);
    const rest = longestExtension(next, adj, usedEdges, usedNodes);
    usedNodes.delete(next);
    usedEdges.delete(edge.id);
    const piece = coordsFrom(edge, node);
    const coords = [...piece.slice(1), ...rest.coords];
    const length = edge.length + rest.length;
    if (length > best.length) {
      best = { coords, length };
    }
  }
  return best;
}

function pathThroughEdge(edge: Edge, adj: Map<number, Edge[]>): Position[] {
  const usedEdges = new Set<number>([edge.id]);
  const usedNodes = new Set<number>([edge.a, edge.b]);
  const left = longestExtension(edge.a, adj, usedEdges, usedNodes);
  const right = longestExtension(edge.b, adj, usedEdges, usedNodes);
  const mid = coordsFrom(edge, edge.a);
  return [...left.coords].reverse().concat(mid, right.coords);
}

function adjacency(edges: Edge[]): Map<number, Edge[]> {
  const adj = new Map<number, Edge[]>();
  for (const edge of edges) {
    const aList = adj.get(edge.a) ?? [];
    aList.push(edge);
    adj.set(edge.a, aList);
    const bList = adj.get(edge.b) ?? [];
    bList.push(edge);
    adj.set(edge.b, bList);
  }
  return adj;
}

function seedEdge(
  seed: Position[],
  edges: Edge[],
  clusterOf: (point: Position) => number | null,
): Edge | null {
  const start = seed[0];
  const end = seed[seed.length - 1];
  if (!start || !end) {
    return null;
  }
  const a = clusterOf(start);
  const b = clusterOf(end);
  if (a === null || b === null || a === b) {
    return null;
  }
  return (
    edges.find(
      (edge) => (edge.a === a && edge.b === b) || (edge.a === b && edge.b === a),
    ) ?? null
  );
}

/**
 * Build one longitudinal LineString: snap endpoints (~2 m), drop duplicate
 * edges, then the longest simple path through the first piece (the click).
 * T-branches and disconnected leftovers stay out so 10 km of road is not 45 km.
 */
export function mergeLineStringTramos(features: readonly Feature[]): LineString | null {
  const pieces = features
    .filter((feature) => isLineString(feature.geometry))
    .map((feature) => [...(feature.geometry as LineString).coordinates]);
  if (pieces.length === 0) {
    return null;
  }
  if (pieces.length === 1) {
    const only = pieces[0];
    return only && only.length >= 2 ? { type: 'LineString', coordinates: only } : null;
  }
  const { edges, clusterOf } = buildEdges(pieces);
  if (edges.length === 0) {
    const only = pieces[0];
    return only && only.length >= 2 ? { type: 'LineString', coordinates: only } : null;
  }
  const adj = adjacency(edges);
  const seed = pieces[0] ? seedEdge(pieces[0], edges, clusterOf) : null;
  const through = seed ?? edges.reduce((best, edge) => (edge.length > best.length ? edge : best));
  const coordinates = pathThroughEdge(through, adj);
  if (coordinates.length < 2) {
    return null;
  }
  return { type: 'LineString', coordinates };
}
