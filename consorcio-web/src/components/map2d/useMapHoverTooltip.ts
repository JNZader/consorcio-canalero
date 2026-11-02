import type { Feature } from 'geojson';
import type { Map as MapLibreMap, MapMouseEvent } from 'maplibre-gl';
import { type RefObject, useEffect, useState } from 'react';
import { featureDisplayName } from './InfoPanel';
import { SOURCE_IDS } from './map2dConfig';
import { publishMapFeatureReadout } from './mapFeatureReadout';
import type { MapInteractionMode } from './measurement/useMeasurement';
import { prefersFineHover, subscribePrefersFineHover } from './prefersFineHover';
import { PUNTOS_INTERES_HIT_LAYER_ID, PUNTOS_INTERES_LAYER_ID } from './puntosInteresLayers';

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
 * Desktop hover name (UX PDF R6). The name is published to the cursor dock
 * instead of a popup on the feature, which used to cover the line it named.
 * Mobile has no hover — click opens the sheet.
 */
export function useMapHoverTooltip({
  mapRef,
  mapReady,
  mode = 'idle',
}: {
  readonly mapRef: RefObject<MapLibreMap | null>;
  readonly mapReady: boolean;
  readonly mode?: MapInteractionMode;
}): void {
  const [fineHover, setFineHover] = useState(prefersFineHover);
  useEffect(() => subscribePrefersFineHover(setFineHover), []);
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || mode !== 'idle' || !fineHover) return;

    let last = 0;

    const onMove = (event: MapMouseEvent) => {
      const now = Date.now();
      if (now - last < THROTTLE_MS) return;
      last = now;
      const layers = HOVER_LAYER_IDS.filter((id) => map.getLayer(id));
      if (layers.length === 0) return;
      const hits = map.queryRenderedFeatures(event.point, { layers });
      const feature = hits[0];
      if (!feature) {
        publishMapFeatureReadout('2d', null);
        map.getCanvas().style.cursor = '';
        return;
      }
      map.getCanvas().style.cursor = 'pointer';
      publishMapFeatureReadout('2d', featureDisplayName(feature as Feature));
    };

    const onLeave = () => {
      publishMapFeatureReadout('2d', null);
      map.getCanvas().style.cursor = '';
    };

    map.on('mousemove', onMove);
    map.on('mouseout', onLeave);
    return () => {
      map.off('mousemove', onMove);
      map.off('mouseout', onLeave);
      publishMapFeatureReadout('2d', null);
      map.getCanvas().style.cursor = '';
    };
  }, [fineHover, mapReady, mapRef, mode]);
}
