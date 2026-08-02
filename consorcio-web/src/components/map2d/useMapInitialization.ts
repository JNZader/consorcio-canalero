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
    container.removeEventListener('dragstart', preventNativeDrag, {
      capture: true,
    });
    container.style.userSelect = '';
    container.style.webkitUserSelect = '';
    container.style.removeProperty('-webkit-user-drag');
  };
}

/**
 * True when the primary pointer is coarse (finger/stylus), i.e. a touch device.
 *
 * Cooperative gestures exist to stop the DESKTOP wheel from hijacking page
 * scroll. On touch they do the opposite of what we want: MapLibre requires TWO
 * fingers to pan, so a one-finger drag scrolls the page and the map becomes
 * unpannable with the gesture every user tries first. We therefore enable the
 * handler only for fine pointers.
 *
 * Read ONCE at map construction (the option is not reactive in MapLibre);
 * falls back to `false` (= cooperative gestures ON) when `matchMedia` is
 * unavailable, which keeps the safer desktop behaviour as the default.
 */
export function isCoarsePointerDevice(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false;
  try {
    return window.matchMedia('(pointer: coarse)').matches;
  } catch {
    return false;
  }
}

/**
 * Spanish copy for MapLibre's cooperative-gestures hint overlay. Keys are the
 * canonical MapLibre locale ids (see `CooperativeGesturesHandler.*HelpText` in
 * the installed `maplibre-gl` typings) — the library ships English-only text.
 */
export const MAP_LOCALE_ES = {
  'CooperativeGesturesHandler.WindowsHelpText': 'Usá Ctrl + desplazamiento para hacer zoom',
  'CooperativeGesturesHandler.MacHelpText': 'Usá ⌘ + desplazamiento para hacer zoom',
  'CooperativeGesturesHandler.MobileHelpText': 'Usá dos dedos para mover el mapa',
} as const;

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
            paint: {
              'background-color': 'rgba(0,0,0,0)',
              'background-opacity': 0,
            },
          },
        ],
      },
      center: [centerLng, centerLat],
      zoom,
      minZoom: MAP_MIN_ZOOM,
      maxBounds: MAP_MAX_BOUNDS,
      preserveDrawingBuffer: true,
      // Desktop wheel must NOT hijack the page scroll: cooperative gestures
      // require Ctrl+wheel to zoom and show a hint otherwise (see change
      // `rediseno-ux-mapa`). On TOUCH the same handler forces two-finger pan,
      // which makes the map unresponsive to the one-finger drag every user
      // tries first — so it is enabled for FINE pointers only.
      cooperativeGestures: !isCoarsePointerDevice(),
      locale: { ...MAP_LOCALE_ES },
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
