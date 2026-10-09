import type { Feature } from 'geojson';

import { SOURCE_IDS } from './map2dConfig';

type FeatureWithLayer = Feature & { readonly layer?: { readonly id?: string } };

/** Canal first, then roads. Waterways are never a "tramo" selection. */
export const TRAMO_LAYER_PRIORITY = [
  `${SOURCE_IDS.CANALES_RELEVADOS}-line`,
  `${SOURCE_IDS.CANALES_PROPUESTOS}-line`,
  `${SOURCE_IDS.ROADS}-hit`,
] as const;

function isTramoLayer(layerId: string | undefined): boolean {
  return layerId !== undefined && (TRAMO_LAYER_PRIORITY as readonly string[]).includes(layerId);
}

function lineCoordinates(feature: Feature): number[][] {
  const geometry = feature.geometry;
  if (geometry?.type !== 'LineString') {
    return [];
  }
  return geometry.coordinates;
}

function pointToSegmentDist2(
  point: readonly [number, number],
  start: number[],
  end: number[],
): number {
  const vx = end[0] - start[0];
  const vy = end[1] - start[1];
  const wx = point[0] - start[0];
  const wy = point[1] - start[1];
  const c1 = vx * wx + vy * wy;
  if (c1 <= 0) {
    return wx * wx + wy * wy;
  }
  const c2 = vx * vx + vy * vy;
  if (c2 <= c1) {
    const dx = point[0] - end[0];
    const dy = point[1] - end[1];
    return dx * dx + dy * dy;
  }
  const t = c1 / c2;
  const dx = point[0] - (start[0] + t * vx);
  const dy = point[1] - (start[1] + t * vy);
  return dx * dx + dy * dy;
}

function pointToLineDist2(point: readonly [number, number], feature: Feature): number {
  const coords = lineCoordinates(feature);
  if (coords.length < 2) {
    return Number.POSITIVE_INFINITY;
  }
  let min = Number.POSITIVE_INFINITY;
  for (let index = 0; index < coords.length - 1; index += 1) {
    const start = coords[index];
    const end = coords[index + 1];
    if (!start || !end) {
      continue;
    }
    min = Math.min(min, pointToSegmentDist2(point, start, end));
  }
  return min;
}

export function pickPrimaryTramo(
  features: readonly Feature[],
  at?: readonly [number, number],
): Feature | null {
  const candidates = features.filter((feature) =>
    isTramoLayer((feature as FeatureWithLayer).layer?.id),
  );
  if (candidates.length === 0) {
    return null;
  }
  if (at) {
    return candidates.reduce((best, feature) =>
      pointToLineDist2(at, feature) < pointToLineDist2(at, best) ? feature : best,
    );
  }
  for (const layerId of TRAMO_LAYER_PRIORITY) {
    const hit = candidates.find((feature) => (feature as FeatureWithLayer).layer?.id === layerId);
    if (hit) {
      return hit;
    }
  }
  return null;
}

const ROAD_HIT_LAYER = `${SOURCE_IDS.ROADS}-hit`;

/** Live GEE caminos use `rtn`; the static geojson used `ruta`. */
export function roadRouteCode(properties: Record<string, unknown> | null | undefined): string | null {
  if (!properties) {
    return null;
  }
  for (const key of ['ruta', 'rtn'] as const) {
    const value = properties[key];
    if (typeof value === 'string' && value.trim().length > 0) {
      return value.trim();
    }
  }
  return null;
}

/** All LineStrings in the roads catalog that share this hit's route code. */
export function expandTramoGroup(
  hit: Feature,
  roadsCatalog: readonly Feature[] = [],
): Feature[] {
  const layerId = (hit as FeatureWithLayer).layer?.id;
  const ruta = roadRouteCode(hit.properties as Record<string, unknown> | null);
  if (layerId !== ROAD_HIT_LAYER || ruta === null) {
    return [hit];
  }
  const group = roadsCatalog.filter((feature) => {
    const props = (feature.properties ?? {}) as Record<string, unknown>;
    return roadRouteCode(props) === ruta && feature.geometry?.type === 'LineString';
  });
  if (group.length === 0) {
    return [hit];
  }
  return group.map((feature) => ({
    ...feature,
    layer: { id: ROAD_HIT_LAYER },
  }));
}

function geometryFingerprint(feature: Feature): string {
  const geometry = feature.geometry;
  if (geometry?.type === 'LineString' && geometry.coordinates.length >= 2) {
    const start = geometry.coordinates[0];
    const end = geometry.coordinates[geometry.coordinates.length - 1];
    if (start && end) {
      return `${start[0]},${start[1]}->${end[0]},${end[1]}:${geometry.coordinates.length}`;
    }
  }
  return '';
}

export function selectionKey(feature: Feature): string {
  const withLayer = feature as FeatureWithLayer;
  const layer = withLayer.layer?.id ?? '';
  const props = (feature.properties ?? {}) as Record<string, unknown>;
  const namedId = feature.id ?? props.id ?? props.osm_id;
  if (namedId !== undefined && namedId !== null && String(namedId).length > 0) {
    return `${layer}::${String(namedId)}`;
  }
  return `${layer}::${geometryFingerprint(feature)}`;
}

/** Ctrl/⌘-click: append unseen features, toggle off ones already selected. */
export function mergeAdditiveFeatures(previous: Feature[], incoming: Feature[]): Feature[] {
  if (incoming.length === 0) {
    return previous;
  }
  const next = [...previous];
  for (const feature of incoming) {
    const key = selectionKey(feature);
    const index = next.findIndex((item) => selectionKey(item) === key);
    if (index >= 0) {
      next.splice(index, 1);
    } else {
      next.push(feature);
    }
  }
  return next;
}
