import type { Feature } from 'geojson';
import maplibregl from 'maplibre-gl';
import { type RefObject, useEffect, useState } from 'react';

import { prefersFineHover, subscribePrefersFineHover } from '../map2d/prefersFineHover';

import { featureDisplayName } from '../map2d/InfoPanel';
import { buildClickableLayers3D, filterExistingLayers } from './terrainViewer3DUtils';

const THROTTLE_MS = 80;

/**
 * UX PDF T5 — same desktop hover tooltip as 2D R6. Mobile has no hover.
 */
export function useTerrainHoverTooltip({
  mapRef,
  ready,
}: {
  readonly mapRef: RefObject<maplibregl.Map | null>;
  readonly ready: boolean;
}): void {
  const [fineHover, setFineHover] = useState(prefersFineHover);
  useEffect(() => subscribePrefersFineHover(setFineHover), []);
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || !fineHover) return;
    if (typeof maplibregl.Popup !== 'function') return;

    const popup = new maplibregl.Popup({
      closeButton: false,
      closeOnClick: false,
      offset: 12,
    });
    let last = 0;

    const onMove = (event: maplibregl.MapMouseEvent) => {
      const now = Date.now();
      if (now - last < THROTTLE_MS) return;
      last = now;
      const layers = filterExistingLayers(map, buildClickableLayers3D());
      if (layers.length === 0) return;
      const hits = map.queryRenderedFeatures(event.point, { layers });
      const feature = hits[0];
      if (!feature) {
        popup.remove();
        map.getCanvas().style.cursor = '';
        return;
      }
      map.getCanvas().style.cursor = 'pointer';
      popup
        .setLngLat(event.lngLat)
        .setText(featureDisplayName(feature as unknown as Feature))
        .addTo(map);
    };

    const onLeave = () => {
      popup.remove();
      map.getCanvas().style.cursor = '';
    };

    map.on('mousemove', onMove);
    map.on('mouseout', onLeave);
    return () => {
      map.off('mousemove', onMove);
      map.off('mouseout', onLeave);
      popup.remove();
    };
  }, [fineHover, mapRef, ready]);
}
