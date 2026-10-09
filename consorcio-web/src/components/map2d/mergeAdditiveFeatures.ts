import type { Feature } from 'geojson';

type FeatureWithLayer = Feature & { readonly layer?: { readonly id?: string } };

export function selectionKey(feature: Feature): string {
  const withLayer = feature as FeatureWithLayer;
  const layer = withLayer.layer?.id ?? '';
  const props = (feature.properties ?? {}) as Record<string, unknown>;
  const id = feature.id ?? props.id ?? props.osm_id ?? '';
  return `${layer}::${String(id)}`;
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
