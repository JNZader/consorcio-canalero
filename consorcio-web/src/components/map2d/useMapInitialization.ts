import type maplibregl from 'maplibre-gl';
import { type RefObject, useEffect } from 'react';
import { MAP_MAX_BOUNDS, MAP_MIN_ZOOM } from '../../constants';
import { logger } from '../../lib/logger';

interface UseMapInitializationParams {
  maplibre: typeof maplibregl;
  containerRef: RefObject<HTMLDivElement | null>;
  centerLat: number;
  centerLng: number;
  zoom: number;
  mapRef: RefObject<maplibregl.Map | null>;
  setMapReady: (ready: boolean) => void;
}

/**
 * Prevent the browser's native drag-and-drop gesture from hijacking MapLibre
 * pan gestures. This is intentionally done with a capture-phase event guard,
 * not only CSS, because satellite/raster map DOM can change after initial
 * render and browser-native dragstart still wins intermittently in Chromium.
 */
export function installMapNativeDragGuards(container: HTMLElement): () => void {
  const preventNativeDrag = (event: DragEvent) => {
    event.preventDefault();
  };

  container.addEventListener('dragstart', preventNativeDrag, { capture: true });
  container.style.userSelect = 'none';
  container.style.webkitUserSelect = 'none';
  container.style.setProperty('-webkit-user-drag', 'none');

  return () => {
    container.removeEventListener('dragstart', preventNativeDrag, { capture: true });
    container.style.userSelect = '';
    container.style.webkitUserSelect = '';
    container.style.removeProperty('-webkit-user-drag');
  };
}

export function useMapInitialization({
  maplibre,
  containerRef,
  centerLat,
  centerLng,
  zoom,
  mapRef,
  setMapReady,
}: UseMapInitializationParams) {
  useEffect(() => {
    if (!containerRef.current) return;

    const removeNativeDragGuards = installMapNativeDragGuards(containerRef.current);

    const map = new maplibre.Map({
      container: containerRef.current,
      style: {
        version: 8,
        sources: {
          'osm-base': {
            type: 'raster',
            tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
            tileSize: 256,
            attribution:
              '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
            maxzoom: 19,
          },
          'satellite-base': {
            type: 'raster',
            tiles: [
              'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            ],
            tileSize: 256,
            attribution: '&copy; Esri',
          },
        },
        layers: [
          {
            id: 'osm-tiles',
            type: 'raster',
            source: 'osm-base',
            layout: { visibility: 'visible' },
            paint: { 'raster-opacity': 1 },
          },
          {
            id: 'satellite-tiles',
            type: 'raster',
            source: 'satellite-base',
            layout: { visibility: 'none' },
            paint: { 'raster-opacity': 1 },
          },
          {
            id: 'vector-layers-start',
            type: 'background',
            paint: { 'background-color': 'rgba(0,0,0,0)', 'background-opacity': 0 },
          },
        ],
      },
      center: [centerLng, centerLat],
      zoom,
      minZoom: MAP_MIN_ZOOM,
      maxBounds: MAP_MAX_BOUNDS,
      preserveDrawingBuffer: true,
    });

    map.addControl(new maplibre.NavigationControl(), 'top-right');
    map.addControl(new maplibre.FullscreenControl(), 'top-right');
    map.addControl(new maplibre.ScaleControl({ unit: 'metric' }), 'bottom-left');

    map.on('load', () => {
      setMapReady(true);
    });

    map.on('error', (event) => {
      const msg =
        typeof event.error === 'string'
          ? event.error
          : event.error instanceof Error
            ? event.error.message
            : '';
      const isTileError =
        'tile' in event || /AJAXError/i.test(msg) || /earthengine\.googleapis\.com/i.test(msg);
      if (!isTileError) {
        logger.error('MapaMapLibre error', event.error);
      }
    });

    mapRef.current = map;

    return () => {
      removeNativeDragGuards();
      map.remove();
      mapRef.current = null;
      setMapReady(false);
    };
  }, [centerLat, centerLng, containerRef, mapRef, maplibre, setMapReady, zoom]);
}
