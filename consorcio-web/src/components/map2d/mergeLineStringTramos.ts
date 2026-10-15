import distance from '@turf/distance';
import type { Feature, LineString, MultiLineString, Position } from 'geojson';

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
  usedNodes: Set<number>
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

function canonicalCoords(coords: Position[]): string {
  const forward = coords.map((point) => `${point[0]},${point[1]}`).join(';');
  const backward = [...coords]
    .reverse()
    .map((point) => `${point[0]},${point[1]}`)
    .join(';');
  // Ida y vuelta es el mismo tramo: la clave no depende del sentido.
  return forward <= backward ? forward : backward;
}

/**
 * The tramo's two ends, order-independent and rounded to about a metre.
 *
 * Two tramos that share both ends describe the same stretch of road, which is
 * how the source repeats one: T391-09 carries the same 1.899 km twice (ids
 * 10164 and 52583, eight and seven vertices) and T391-08 repeats a 1.96 km
 * stretch. Deduping by coordinates alone missed both.
 */
function endpointKey(coords: Position[]): string {
  const first = coords[0];
  const last = coords[coords.length - 1];
  if (!first || !last) {
    return '';
  }
  const a = `${first[0]?.toFixed(5)},${first[1]?.toFixed(5)}`;
  const b = `${last[0]?.toFixed(5)},${last[1]?.toFixed(5)}`;
  return a <= b ? `${a}|${b}` : `${b}|${a}`;
}

function featureId(feature: Feature): string {
  const properties = (feature.properties ?? {}) as Record<string, unknown>;
  return String(feature.id ?? properties.id ?? properties.rtn ?? '');
}

/** A deduped tramo: its id, its own coordinates, and its own length. */
interface Parte {
  id: string;
  coords: Position[];
  length: number;
}

/**
 * 2-opt over the walk the greedy produced: reverse a slice of the order — which
 * also flips every part inside it — whenever that shortens the total gap.
 *
 * The greedy exploits the geometry (two branch tips can be near each other) but
 * commits early, and a planned topological walk measured worse, so this undoes a
 * bad commitment without planning the whole route. The cost of a reversal touches
 * only its two boundaries, so a move is scored with two distance calls instead of
 * rebuilding the walk.
 */
function improveWithTwoOpt(ordered: readonly Parte[]): Parte[] {
  const walk = [...ordered];
  if (walk.length < 3) {
    return walk;
  }
  const tailOf = (parte: Parte): Position => parte.coords[parte.coords.length - 1] as Position;
  const headOf = (parte: Parte): Position => parte.coords[0] as Position;
  const gapTo = (from: Position, to: Position): number => distance(from, to, { units: 'meters' });

  for (let round = 0; round < 8; round += 1) {
    let improved = false;
    for (let i = 0; i < walk.length - 1; i += 1) {
      for (let j = i + 1; j < walk.length; j += 1) {
        const before =
          (i > 0 ? gapTo(tailOf(walk[i - 1] as Parte), headOf(walk[i] as Parte)) : 0) +
          (j + 1 < walk.length ? gapTo(tailOf(walk[j] as Parte), headOf(walk[j + 1] as Parte)) : 0);
        const after =
          (i > 0 ? gapTo(tailOf(walk[i - 1] as Parte), tailOf(walk[j] as Parte)) : 0) +
          (j + 1 < walk.length ? gapTo(headOf(walk[i] as Parte), headOf(walk[j + 1] as Parte)) : 0);
        if (after < before - 0.5) {
          const reversed = walk
            .slice(i, j + 1)
            .reverse()
            .map((parte) => ({ ...parte, coords: [...parte.coords].reverse() }));
          walk.splice(i, j - i + 1, ...reversed);
          improved = true;
        }
      }
    }
    if (!improved) {
      break;
    }
  }
  return walk;
}

/**
 * Or-opt over the walk the 2-opt left: take a short run of parts out of the
 * order and put it back somewhere else, in either direction, whenever that
 * shortens the total gap.
 *
 * 2-opt can only reverse a slice, so it cannot fix a part that simply sits in the
 * wrong place — S331 and T135-11 stayed far above their floor after it. Moving a
 * run is the next local move, and it is still local: the walk stays a walk, no
 * route is planned.
 *
 * Runs up to three parts, either orientation, full cost recomputed (the walks
 * here are at most a few dozen parts). Deterministic, so the cache key holds.
 */
function improveWithOrOpt(ordered: readonly Parte[]): Parte[] {
  const tailOf = (parte: Parte): Position => parte.coords[parte.coords.length - 1] as Position;
  const headOf = (parte: Parte): Position => parte.coords[0] as Position;
  const gapOf = (list: readonly Parte[]): number => {
    let total = 0;
    for (let i = 0; i + 1 < list.length; i += 1) {
      total += distance(tailOf(list[i] as Parte), headOf(list[i + 1] as Parte), {
        units: 'meters',
      });
    }
    return total;
  };

  let best = [...ordered];
  let bestGap = gapOf(best);
  for (let round = 0; round < 6; round += 1) {
    let improved = false;
    for (let length = 1; length <= 3; length += 1) {
      for (let start = 0; start + length <= best.length; start += 1) {
        const run = best.slice(start, start + length);
        const rest = [...best.slice(0, start), ...best.slice(start + length)];
        const reversedRun = run
          .slice()
          .reverse()
          .map((parte) => ({ ...parte, coords: [...parte.coords].reverse() }));
        for (let at = 0; at <= rest.length; at += 1) {
          for (const candidate of [run, reversedRun]) {
            const trial = [...rest.slice(0, at), ...candidate, ...rest.slice(at)];
            const gap = gapOf(trial);
            if (gap < bestGap - 0.5) {
              best = trial;
              bestGap = gap;
              improved = true;
            }
          }
        }
      }
    }
    if (!improved) {
      break;
    }
  }
  return best;
}

/**
 * Order the parts so the profile READS along the trace instead of jumping.
 *
 * One part per tramo means the catalog order (by tramo id) is NOT the order
 * along the road. Measured over the 380 published tramos: with the id order, 243
 * of the 282 part boundaries were gaps over 25 m — 1141 km of jumping in total —
 * so the chart visibly mixed tramos up. Walking from a free end and always
 * appending the part nearest to where the walk currently is (reversing it when
 * its far end is closer) leaves only the returns from a branch back to its
 * junction, which a branched trace cannot avoid.
 *
 * Deterministic on purpose: the part order is part of the elevation-profile
 * cache key, so the same selection must always produce the same bytes. The walk
 * starts at the first free end in id order and ties break the same way.
 */
function chainByContinuity(partes: readonly Parte[]): Parte[] {
  if (partes.length < 2) {
    return [...partes];
  }

  const ends = partes.flatMap((parte) => [parte.coords[0], parte.coords[parte.coords.length - 1]]);
  const cluster = clusterEndpoints(ends);
  const degree = new Map<number, number>();
  for (const node of cluster) {
    degree.set(node, (degree.get(node) ?? 0) + 1);
  }
  const degreeAt = (index: number, which: 0 | 1): number =>
    degree.get(cluster[index * 2 + which]) ?? 0;

  // Seed: the first part (id order) with a free end, ORIENTED so the walk starts
  // at that free end. Without the orientation the very first boundary is a jump.
  let seed = 0;
  let reverseSeed = false;
  for (let i = 0; i < partes.length; i += 1) {
    if (degreeAt(i, 0) <= 1) {
      seed = i;
      break;
    }
    if (degreeAt(i, 1) <= 1) {
      seed = i;
      reverseSeed = true;
      break;
    }
  }

  const used = new Array<boolean>(partes.length).fill(false);
  used[seed] = true;
  const head = reverseSeed ? [...partes[seed].coords].reverse() : partes[seed].coords;
  const ordered: Parte[] = [{ ...partes[seed], coords: head }];
  let cursor = head[head.length - 1];

  for (let appended = 1; appended < partes.length; appended += 1) {
    let best = -1;
    let bestGap = Number.POSITIVE_INFINITY;
    let reverseBest = false;
    for (let i = 0; i < partes.length; i += 1) {
      if (used[i]) {
        continue;
      }
      const from = partes[i].coords[0];
      const to = partes[i].coords[partes[i].coords.length - 1];
      const gapFrom = distance(cursor, from, { units: 'meters' });
      const gapTo = distance(cursor, to, { units: 'meters' });
      const gap = Math.min(gapFrom, gapTo);
      if (gap < bestGap) {
        bestGap = gap;
        best = i;
        reverseBest = gapTo < gapFrom;
      }
    }
    if (best < 0) {
      break;
    }
    used[best] = true;
    const coords = reverseBest ? [...partes[best].coords].reverse() : partes[best].coords;
    ordered.push({ ...partes[best], coords });
    cursor = coords[coords.length - 1];
  }
  return improveWithOrOpt(improveWithTwoOpt(ordered));
}

/**
 * Every tramo as its own part, deduped and chained along the trace.
 *
 * The profile samples each part, so a branched or gapped road is covered whole
 * instead of one chosen path. The parts are walked in trace order (see
 * `chainByContinuity`), NOT in catalog order: ordering by tramo id made the
 * chart jump between disconnected tramos. The order stays deterministic — it is
 * part of the elevation-profile cache key — because the chain starts from the
 * id order and breaks ties the same way.
 */
export function mergeLineStringParts(features: readonly Feature[]): MultiLineString | null {
  const vistos = new Set<string>();
  const porExtremos = new Map<string, Array<{ id: string; coords: Position[]; length: number }>>();
  for (const feature of features) {
    if (!isLineString(feature.geometry)) {
      continue;
    }
    const linea = asLine([...(feature.geometry as LineString).coordinates]);
    if (!linea) {
      continue;
    }
    const clave = canonicalCoords(linea.coordinates);
    if (vistos.has(clave)) {
      continue;
    }
    vistos.add(clave);
    const largo = pieceLengthM(linea.coordinates);
    const candidatos = porExtremos.get(endpointKey(linea.coordinates)) ?? [];
    // Mismo par de extremos y casi el mismo largo: la fuente trae el mismo tramo
    // dos veces, se queda el mas detallado. Si el largo difiere mucho son dos
    // recorridos distintos entre los mismos nodos y los dos cuentan.
    const gemelo = candidatos.find(
      (candidato) => Math.abs(candidato.length - largo) <= 0.25 * Math.max(candidato.length, largo)
    );
    if (gemelo) {
      if (largo > gemelo.length) {
        gemelo.id = featureId(feature);
        gemelo.coords = linea.coordinates;
        gemelo.length = largo;
      }
    } else {
      candidatos.push({ id: featureId(feature), coords: linea.coordinates, length: largo });
    }
    porExtremos.set(endpointKey(linea.coordinates), candidatos);
  }
  const partes = [...porExtremos.values()].flat();
  if (partes.length === 0) {
    return null;
  }
  partes.sort((a, b) => a.id.localeCompare(b.id, undefined, { numeric: true }));
  return {
    type: 'MultiLineString',
    coordinates: chainByContinuity(partes).map((parte) => parte.coords),
  };
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
