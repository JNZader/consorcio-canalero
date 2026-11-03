import type { Map as MapLibreMap, MapMouseEvent } from 'maplibre-gl';
import { useEffect, useMemo, useRef } from 'react';
import type { ProfileCursorSample } from './profileCursorSync';

const HIT_PX = 18;
// Approx ~1000m buffer in degrees (~0.01 deg) for quick spatial rejection
const BBOX_BUFFER_DEG = 0.01;

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

  const bbox = useMemo(() => {
    if (!samples.length) return null;
    let minLon = Infinity;
    let maxLon = -Infinity;
    let minLat = Infinity;
    let maxLat = -Infinity;
    for (const s of samples) {
      if (s.lon != null && s.lat != null) {
        if (s.lon < minLon) minLon = s.lon;
        if (s.lon > maxLon) maxLon = s.lon;
        if (s.lat < minLat) minLat = s.lat;
        if (s.lat > maxLat) maxLat = s.lat;
      }
    }
    if (!Number.isFinite(minLon)) return null;
    return {
      minLon: minLon - BBOX_BUFFER_DEG,
      maxLon: maxLon + BBOX_BUFFER_DEG,
      minLat: minLat - BBOX_BUFFER_DEG,
      maxLat: maxLat + BBOX_BUFFER_DEG,
    };
  }, [samples]);

  const bboxRef = useRef(bbox);
  bboxRef.current = bbox;

  useEffect(() => {
    if (!map || !mapReady || !enabled) {
      return;
    }

    let rafId: number | null = null;
    let lastDistance: number | null = null;

    const computeDistance = (point: { x: number; y: number }, lngLat: { lng: number; lat: number }) => {
      const b = bboxRef.current;
      if (
        b &&
        (lngLat.lng < b.minLon ||
          lngLat.lng > b.maxLon ||
          lngLat.lat < b.minLat ||
          lngLat.lat > b.maxLat)
      ) {
        if (lastDistance !== null) {
          lastDistance = null;
          onDistanceRef.current(null);
        }
        return;
      }

      let bestPx = Infinity;
      let bestDistance: number | null = null;
      for (const sample of samplesRef.current) {
        if (sample.lon == null || sample.lat == null) {
          continue;
        }
        const projected = map.project([sample.lon, sample.lat]);
        const px = Math.hypot(projected.x - point.x, projected.y - point.y);
        if (px < bestPx) {
          bestPx = px;
          bestDistance = sample.distance_m;
        }
      }

      const nextDistance = bestPx <= HIT_PX ? bestDistance : null;
      if (nextDistance !== lastDistance) {
        lastDistance = nextDistance;
        onDistanceRef.current(nextDistance);
      }
    };

    const onMove = (event: MapMouseEvent) => {
      const point = { x: event.point.x, y: event.point.y };
      const lngLat = { lng: event.lngLat.lng, lat: event.lngLat.lat };
      if (rafId !== null) {
        cancelAnimationFrame(rafId);
      }
      rafId = requestAnimationFrame(() => {
        rafId = null;
        computeDistance(point, lngLat);
      });
    };

    const onLeave = () => {
      if (rafId !== null) {
        cancelAnimationFrame(rafId);
        rafId = null;
      }
      if (lastDistance !== null) {
        lastDistance = null;
        onDistanceRef.current(null);
      }
    };

    map.on('mousemove', onMove);
    map.on('mouseout', onLeave);
    return () => {
      if (rafId !== null) {
        cancelAnimationFrame(rafId);
        rafId = null;
      }
      map.off('mousemove', onMove);
      map.off('mouseout', onLeave);
      if (lastDistance !== null) {
        lastDistance = null;
        onDistanceRef.current(null);
      }
    };
  }, [enabled, map, mapReady]);
}
