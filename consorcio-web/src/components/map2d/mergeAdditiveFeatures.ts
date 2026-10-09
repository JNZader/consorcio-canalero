import type { Feature } from 'geojson';

import { SOURCE_IDS } from './map2dConfig';

type FeatureWithLayer = Feature & { readonly layer?: { readonly id?: string } };

/** Canal first, then roads. Waterways are never a "tramo" selection. */
export const TRAMO_LAYER_PRIORITY = [
  `${SOURCE_IDS.CANALES_RELEVADOS}-line`,
  `${SOURCE_IDS.CANALES_PROPUESTOS}-line`,
  `${SOURCE_IDS.ROADS}-hit`,
] as const;

export function pickPrimaryTramo(features: readonly Feature[]): Feature | null {
  for (const layerId of TRAMO_LAYER_PRIORITY) {
    const hit = features.find((feature) => (feature as FeatureWithLayer).layer?.id === layerId);
    if (hit) {
      return hit;
    }
  }
  return null;
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
