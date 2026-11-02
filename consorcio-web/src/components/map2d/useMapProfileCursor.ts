import type { Map as MapLibreMap, MapMouseEvent } from 'maplibre-gl';
import { useEffect, useRef } from 'react';
import type { ProfileCursorSample } from './profileCursorSync';

const HIT_PX = 18;

/**
 * Moving the pointer along the profile line on the map sets the chart cursor.
 * The chart's own pointer still wins: this only publishes a distance.
 */
export function useMapProfileCursor({
  map,
  mapReady,
  samples,
  enabled,
  onDistance,
}: {
  readonly map: MapLibreMap | null;
  readonly mapReady: boolean;
  readonly samples: readonly ProfileCursorSample[];
  readonly enabled: boolean;
  readonly onDistance: (distanceM: number | null) => void;
}): void {
  const onDistanceRef = useRef(onDistance);
  onDistanceRef.current = onDistance;
  const samplesRef = useRef(samples);
  samplesRef.current = samples;

  useEffect(() => {
    if (!map || !mapReady || !enabled) {
      return;
    }
    const onMove = (event: MapMouseEvent) => {
      let bestPx = Infinity;
      let bestDistance: number | null = null;
      for (const sample of samplesRef.current) {
        if (sample.lon == null || sample.lat == null) {
          continue;
        }
        const projected = map.project([sample.lon, sample.lat]);
        const px = Math.hypot(projected.x - event.point.x, projected.y - event.point.y);
        if (px < bestPx) {
          bestPx = px;
          bestDistance = sample.distance_m;
        }
      }
      onDistanceRef.current(bestPx <= HIT_PX ? bestDistance : null);
    };
    const onLeave = () => onDistanceRef.current(null);
    map.on('mousemove', onMove);
    map.on('mouseout', onLeave);
    return () => {
      map.off('mousemove', onMove);
      map.off('mouseout', onLeave);
      onDistanceRef.current(null);
    };
  }, [enabled, map, mapReady]);
}
