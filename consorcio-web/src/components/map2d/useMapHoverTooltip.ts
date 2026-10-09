import type { Feature } from 'geojson';
import maplibregl from 'maplibre-gl';
import { type RefObject, useEffect } from 'react';

import { featureDisplayName } from './InfoPanel';
import { SOURCE_IDS } from './map2dConfig';
import {
  PUNTOS_INTERES_HIT_LAYER_ID,
  PUNTOS_INTERES_LAYER_ID,
} from './puntosInteresLayers';
import type { MapInteractionMode } from './measurement/useMeasurement';

const HOVER_LAYER_IDS = [
  `${SOURCE_IDS.CANALES_RELEVADOS}-line`,
  `${SOURCE_IDS.CANALES_PROPUESTOS}-line`,
  `${SOURCE_IDS.ROADS}-hit`,
  `${SOURCE_IDS.WATERWAYS}-rio-tercero-line`,
  `${SOURCE_IDS.WATERWAYS}-arroyo-algodon-line`,
  `${SOURCE_IDS.WATERWAYS}-canal-desviador-line`,
  `${SOURCE_IDS.WATERWAYS}-canal-litin-line`,
  `${SOURCE_IDS.WATERWAYS}-arroyo-mojarras-line`,
  `${SOURCE_IDS.ESCUELAS}-symbol`,
  PUNTOS_INTERES_HIT_LAYER_ID,
  PUNTOS_INTERES_LAYER_ID,
];

const THROTTLE_MS = 80;

/**
 * Desktop hover tooltip (UX PDF R6). Mobile has no hover — click opens the sheet.
 */
export function useMapHoverTooltip({
  mapRef,
  mapReady,
  mode = 'idle',
}: {
  readonly mapRef: RefObject<maplibregl.Map | null>;
  readonly mapReady: boolean;
  readonly mode?: MapInteractionMode;
}): void {
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || mode !== 'idle') return;
    if (window.matchMedia('(hover: none)').matches) return;

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
      const layers = HOVER_LAYER_IDS.filter((id) => map.getLayer(id));
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
        .setText(featureDisplayName(feature as GeoJSON.Feature))
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
      map.getCanvas().style.cursor = '';
    };
  }, [mapReady, mapRef, mode]);
}
