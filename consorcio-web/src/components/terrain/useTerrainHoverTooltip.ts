import type { Feature } from 'geojson';
import type { Map as MapLibreMap, MapMouseEvent } from 'maplibre-gl';
import { type RefObject, useEffect, useState } from 'react';
import { featureDisplayName } from '../map2d/InfoPanel';
import { publishMapFeatureReadout } from '../map2d/mapFeatureReadout';
import { prefersFineHover, subscribePrefersFineHover } from '../map2d/prefersFineHover';
import { buildClickableLayers3D, filterExistingLayers } from './terrainViewer3DUtils';

const THROTTLE_MS = 80;

/**
 * UX PDF T5 — same desktop hover name as 2D, docked in the status bar so the
 * card does not cover the feature. Mobile has no hover.
 */
export function useTerrainHoverTooltip({
  mapRef,
  ready,
}: {
  readonly mapRef: RefObject<MapLibreMap | null>;
  readonly ready: boolean;
}): void {
  const [fineHover, setFineHover] = useState(prefersFineHover);
  useEffect(() => subscribePrefersFineHover(setFineHover), []);
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || !fineHover) return;

    let last = 0;

    const onMove = (event: MapMouseEvent) => {
      const now = Date.now();
      if (now - last < THROTTLE_MS) return;
      last = now;
      const layers = filterExistingLayers(map, buildClickableLayers3D());
      if (layers.length === 0) return;
      const hits = map.queryRenderedFeatures(event.point, { layers });
      const feature = hits[0];
      if (!feature) {
        publishMapFeatureReadout('3d', null);
        map.getCanvas().style.cursor = '';
        return;
      }
      map.getCanvas().style.cursor = 'pointer';
      publishMapFeatureReadout('3d', featureDisplayName(feature as Feature));
    };

    const onLeave = () => {
      publishMapFeatureReadout('3d', null);
      map.getCanvas().style.cursor = '';
    };

    map.on('mousemove', onMove);
    map.on('mouseout', onLeave);
    return () => {
      map.off('mousemove', onMove);
      map.off('mouseout', onLeave);
      publishMapFeatureReadout('3d', null);
    };
  }, [fineHover, mapRef, ready]);
}
