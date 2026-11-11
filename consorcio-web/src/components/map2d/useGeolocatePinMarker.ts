/**
 * useGeolocatePinMarker — drop a temporary marker at the GPS fix captured by
 * the «Ubicarme» button (ET3-GEO). The writer lives in `MapaMapLibreView`'s
 * geolocate callback (`setGeolocatePin`); this hook is the reader that makes
 * the pin observable on the map. Same marker contract as `useQuickPlaceMarker`
 * / `useReportHighlight`: marker + closable popup, removed on cleanup.
 *
 * Closing the popup is "leaving Ubicarme mode": the store pin goes back to
 * null so the state never outlives the marker it describes.
 */

import * as maplibregl from 'maplibre-gl';
import { type RefObject, useEffect, useRef } from 'react';
import { mapColorTokens } from '../../lib/mapColorTokens';
import { useReportAnchorStore } from '../../stores/reportAnchorStore';

interface UseGeolocatePinMarkerParams {
  readonly mapRef: RefObject<maplibregl.Map | null>;
  /** Becomes `true` once the map style finished loading. */
  readonly mapReady: boolean;
}

export function useGeolocatePinMarker({ mapRef, mapReady }: UseGeolocatePinMarkerParams): void {
  const pin = useReportAnchorStore((state) => state.geolocatePin);
  const markerRef = useRef<maplibregl.Marker | null>(null);

  useEffect(() => {
    const map = mapRef.current;
    markerRef.current?.remove();
    markerRef.current = null;
    if (!map || !mapReady || !pin) return;

    // Convencion: NUNCA interpolar dato de usuario en setHTML de MapLibre;
    // usar setDOMContent + textContent (los nodos construidos con
    // createElement/textContent no son parseados como HTML).
    const popupContent = document.createElement('div');
    popupContent.style.fontSize = '13px';
    const title = document.createElement('strong');
    title.textContent = 'Tu ubicación';
    const coords = document.createElement('span');
    coords.textContent = `${pin.lat.toFixed(5)}, ${pin.lng.toFixed(5)}`;
    popupContent.append(title, document.createElement('br'), coords);

    const popup = new maplibregl.Popup({
      closeButton: true,
      closeOnClick: false,
      anchor: 'bottom',
      offset: 28,
    }).setDOMContent(popupContent);

    const marker = new maplibregl.Marker({ color: mapColorTokens.h2563eb })
      .setLngLat([pin.lng, pin.lat])
      .setPopup(popup)
      .addTo(map);
    marker.togglePopup();
    markerRef.current = marker;

    // `active` guards the pin swap (A→B): MapLibre fires `close` from
    // `Popup.remove()` — which `Marker.remove()` triggers during cleanup — so
    // without the guard the stale popup would clobber the fresh pin B.
    let active = true;
    popup.once('close', () => {
      if (active) useReportAnchorStore.getState().setGeolocatePin(null);
    });

    return () => {
      active = false;
      marker.remove();
      markerRef.current = null;
    };
  }, [mapRef, mapReady, pin]);

  // The store outlives the route: without this, a pin captured before
  // navigating away would resurrect its marker on the next map mount.
  useEffect(
    () => () => {
      useReportAnchorStore.getState().setGeolocatePin(null);
    },
    []
  );
}
