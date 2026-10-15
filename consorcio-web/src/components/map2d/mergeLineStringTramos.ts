import type { Feature, LineString, Position } from 'geojson';
import distance from '@turf/distance';

const SNAP_M = 2;

function isLineString(geometry: Feature['geometry']): geometry is LineString {
  return geometry?.type === 'LineString' && geometry.coordinates.length >= 2;
}

function isRetrace(previous: Position, tip: Position, next: Position): boolean {
  const outbound = distance(previous, tip, { units: 'meters' });
  const inbound = distance(tip, next, { units: 'meters' });
  if (outbound < 0.01 || inbound < 0.01) {
    return true;
  }
  const v1x = tip[0] - previous[0];
  const v1y = tip[1] - previous[1];
  const v2x = next[0] - tip[0];
  const v2y = next[1] - tip[1];
  const denom = Math.hypot(v1x, v1y) * Math.hypot(v2x, v2y);
  if (denom === 0) {
    return true;
  }
  const cosine = (v1x * v2x + v1y * v2y) / denom;
  const back = distance(next, previous, { units: 'meters' });
  return cosine <= -0.85 && back <= outbound + SNAP_M;
}

/** Drop vertices that reverse along the previous edge (ida y vuelta). */
export function unfoldRetracingCoordinates(coords: Position[]): Position[] {
  if (coords.length < 3) {
    return coords.map((point) => [...point]);
  }
  const first = coords[0];
  const second = coords[1];
  if (!first || !second) {
    return coords.map((point) => [...point]);
  }
  const out: Position[] = [[...first], [...second]];
  for (let index = 2; index < coords.length; index += 1) {
    const point = coords[index];
    const previous = out[out.length - 2];
    const tip = out[out.length - 1];
    if (!point || !previous || !tip) {
      continue;
    }
    if (isRetrace(previous, tip, point)) {
      continue;
    }
    out.push([...point]);
  }
  return out.length >= 2 ? out : coords.map((point) => [...point]);
}

function asLine(coords: Position[] | undefined): LineString | null {
  if (!coords || coords.length < 2) {
    return null;
  }
  const unfolded = unfoldRetracingCoordinates(coords);
  return unfolded.length >= 2 ? { type: 'LineString', coordinates: unfolded } : null;
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

function buildEdges(pieces: Position[][]): Edge[] {
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
  return [...byPair.values()];
}

function otherNode(edge: Edge, node: number): number {
  return edge.a === node ? edge.b : edge.a;
}

function coordsFrom(edge: Edge, node: number): Position[] {
  return edge.a === node ? edge.coords : [...edge.coords].reverse();
}

type Extension = {
  coords: Position[];
  length: number;
  edges: number[];
  nodes: number[];
};

function longestExtension(
  node: number,
  adj: Map<number, Edge[]>,
  usedEdges: Set<number>,
  usedNodes: Set<number>,
): Extension {
  let best: Extension = { coords: [], length: 0, edges: [], nodes: [] };
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
      best = {
        coords,
        length,
        edges: [edge.id, ...rest.edges],
        nodes: [next, ...rest.nodes],
      };
    }
  }
  return best;
}

/**
 * Longest simple path through `edge`. Both extensions share one consumed-edge
 * and consumed-node set, so the axis can never walk a stretch twice: on a loop
 * the old code sent one side out and the other side back over the same edge,
 * reporting 4.16 km for a 2.77 km road (A581) and 15.48 km for 9.36 km
 * (T028-19).
 */
function pathThroughEdge(edge: Edge, adj: Map<number, Edge[]>): Position[] {
  const usedEdges = new Set<number>([edge.id]);
  const usedNodes = new Set<number>([edge.a, edge.b]);
  const left = longestExtension(edge.a, adj, usedEdges, usedNodes);
  for (const id of left.edges) {
    usedEdges.add(id);
  }
  for (const node of left.nodes) {
    usedNodes.add(node);
  }
  const right = longestExtension(edge.b, adj, usedEdges, usedNodes);
  const mid = coordsFrom(edge, edge.a);
  return [...left.coords].reverse().concat(mid, right.coords);
}

/**
 * Longest axis over every edge, not the one through the first selected piece.
 * Seeding at `pieces[0]` turned a stray 45.6 m tramo into the whole profile of a
 * 7.32 km road (T027-01).
 */
function longestAxis(edges: Edge[], adj: Map<number, Edge[]>): Position[] {
  const total = edges.reduce((sum, edge) => sum + edge.length, 0);
  let best: Position[] = [];
  let bestLength = 0;
  for (const edge of edges) {
    if (bestLength >= total) {
      break;
    }
    const path = pathThroughEdge(edge, adj);
    const length = pieceLengthM(path);
    if (length > bestLength) {
      best = path;
      bestLength = length;
    }
  }
  return best;
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

/**
 * Build one longitudinal LineString: snap endpoints (~2 m), drop duplicate
 * edges, then the longest simple path in the graph. T-branches and disconnected
 * leftovers stay out so 10 km of road is not 45 km.
 */
export function mergeLineStringTramos(features: readonly Feature[]): LineString | null {
  const pieces = features
    .filter((feature) => isLineString(feature.geometry))
    .map((feature) => [...(feature.geometry as LineString).coordinates]);
  if (pieces.length === 0) {
    return null;
  }
  if (pieces.length === 1) {
    return asLine(pieces[0]);
  }
  const edges = buildEdges(pieces);
  if (edges.length === 0) {
    return asLine(pieces[0]);
  }
  const adj = adjacency(edges);
  const axis = longestAxis(edges, adj);
  return axis.length >= 2 ? asLine(axis) : asLine(pieces[0]);
}

/** Metres of the same LineString the elevation profile samples. */
export function profileAxisLengthM(features: readonly Feature[]): number {
  const axis = mergeLineStringTramos(features);
  return axis ? pieceLengthM(axis.coordinates) : 0;
}

/** Unique-edge metres: overlapping copies count once; T-branches stay in. */
export function dedupedLineStringLengthM(features: readonly Feature[]): number {
  const pieces = features
    .filter((feature) => isLineString(feature.geometry))
    .map((feature) => [...(feature.geometry as LineString).coordinates]);
  if (pieces.length === 0) {
    return 0;
  }
  if (pieces.length === 1) {
    const only = pieces[0];
    return only && only.length >= 2 ? pieceLengthM(only) : 0;
  }
  const edges = buildEdges(pieces);
  if (edges.length === 0) {
    const only = pieces[0];
    return only && only.length >= 2 ? pieceLengthM(only) : 0;
  }
  return edges.reduce((sum, edge) => sum + edge.length, 0);
}
