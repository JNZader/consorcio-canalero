/**
 * Drop a closeable marker when the user flies to a quick place (UX-22).
 * Not a denuncia pin — that path is `report=1` via useReportHighlight.
 */

import maplibregl from 'maplibre-gl';
import { type RefObject, useEffect, useRef } from 'react';

export interface QuickPlacePin {
  readonly label: string;
  readonly lng: number;
  readonly lat: number;
}

interface UseQuickPlaceMarkerParams {
  readonly mapRef: RefObject<maplibregl.Map | null>;
  readonly mapReady: boolean;
  readonly place: QuickPlacePin | null;
}

export function useQuickPlaceMarker({ mapRef, mapReady, place }: UseQuickPlaceMarkerParams): void {
  const markerRef = useRef<maplibregl.Marker | null>(null);

  useEffect(() => {
    const map = mapRef.current;
    markerRef.current?.remove();
    markerRef.current = null;
    if (!map || !mapReady || !place) return;

    const popupContent = document.createElement('div');
    popupContent.style.fontSize = '13px';
    const title = document.createElement('strong');
    title.textContent = place.label;
    popupContent.append(title);

    const popup = new maplibregl.Popup({
      closeButton: true,
      closeOnClick: false,
      offset: 24,
    }).setDOMContent(popupContent);

    const marker = new maplibregl.Marker({ color: '#2563eb' })
      .setLngLat([place.lng, place.lat])
      .setPopup(popup)
      .addTo(map);
    marker.togglePopup();
    markerRef.current = marker;

    return () => {
      marker.remove();
      markerRef.current = null;
    };
  }, [mapRef, mapReady, place]);
}
