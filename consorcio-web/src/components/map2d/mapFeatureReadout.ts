/**
 * Hovered feature name, docked outside the map.
 *
 * A MapLibre popup anchored on the feature covers the line or point it names.
 * The 2D cursor strip and the 3D status bar subscribe here instead.
 */

import { useEffect, useState } from 'react';

export type MapReadoutSurface = '2d' | '3d';

const labels: Record<MapReadoutSurface, string | null> = {
  '2d': null,
  '3d': null,
};

const listeners = new Set<(surface: MapReadoutSurface, label: string | null) => void>();

export function publishMapFeatureReadout(surface: MapReadoutSurface, label: string | null): void {
  if (labels[surface] === label) {
    return;
  }
  labels[surface] = label;
  for (const listener of listeners) {
    listener(surface, label);
  }
}

export function subscribeMapFeatureReadout(
  surface: MapReadoutSurface,
  listener: (label: string | null) => void
): () => void {
  const wrapped = (nextSurface: MapReadoutSurface, label: string | null) => {
    if (nextSurface === surface) {
      listener(label);
    }
  };
  listeners.add(wrapped);
  listener(labels[surface]);
  return () => {
    listeners.delete(wrapped);
  };
}

export function useMapFeatureReadout(surface: MapReadoutSurface): string | null {
  const [label, setLabel] = useState<string | null>(labels[surface]);
  useEffect(() => subscribeMapFeatureReadout(surface, setLabel), [surface]);
  return label;
}
