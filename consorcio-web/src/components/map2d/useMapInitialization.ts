import type * as maplibregl from 'maplibre-gl';
import { type RefObject, useEffect, useRef } from 'react';
import { MAP_MAX_BOUNDS, MAP_MIN_ZOOM } from '../../constants';
import { TILE_LAYERS } from '../../constants/mapStyles';
import { logger } from '../../lib/logger';
import { createMapLibreMap, destroyMapLibreMap } from '../../lib/maplibreLifecycle';
import { listenMapEvent, unlistenMapEvent } from '../../lib/maplibreListen';
import { erroresUi, textoError } from '../../lib/userFacingError';
import { type ClassifiedMapError, classifyMapError } from './mapErrorClassify';
import { MAP_LOCALE_ES } from './mapLibreLocale';
import { MAP_GLYPHS_URL } from './roadLabelLayer';

export { isCoarsePointerDevice } from '../../lib/maplibreLifecycle';
export { MAP_LOCALE_ES } from './mapLibreLocale';

interface UseMapInitializationParams {
  maplibre: Pick<
    typeof maplibregl,
    'Map' | 'NavigationControl' | 'FullscreenControl' | 'ScaleControl'
  >;
  containerRef: RefObject<HTMLDivElement | null>;
  centerLat: number;
  centerLng: number;
  zoom: number;
  mapRef: RefObject<maplibregl.Map | null>;
  setMapReady: (ready: boolean) => void;
  /**
   * Observer for every MapLibre `error`, already classified (tile vs real).
   *
   * DELIBERATELY NOT IN THE INIT EFFECT'S DEPENDENCY ARRAY. That effect's
   * cleanup calls `destroyMapLibreMap`, so adding a callback that changes identity
   * between renders would tear down and rebuild the whole map — losing the
   * viewport, every source and the WebGL context — on each render. The callback
   * is therefore read through a ref that a separate effect keeps current.
   */
  onMapError?: (error: ClassifiedMapError) => void;
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
  // Prefer setProperty for -webkit-* so jsdom/happy-dom and Safari agree on
  // the computed inline style (camelCase webkitUserSelect is not mirrored in
  // happy-dom ≥20.14).
  container.style.userSelect = 'none';
  container.style.setProperty('-webkit-user-select', 'none');
  container.style.setProperty('-webkit-user-drag', 'none');

  return () => {
    container.removeEventListener('dragstart', preventNativeDrag, {
      capture: true,
    });
    container.style.userSelect = '';
    container.style.removeProperty('-webkit-user-select');
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
  onMapError,
}: UseMapInitializationParams) {
  // See the `onMapError` doc comment: a REF, never a dependency of the init
  // effect below — that effect's cleanup calls `destroyMapLibreMap`.
  const onMapErrorRef = useRef(onMapError);
  useEffect(() => {
    onMapErrorRef.current = onMapError;
  }, [onMapError]);

  // Snapshot the opening camera ONCE. `MapaMapLibre` also publishes live
  // center/zoom into `mapCameraStore` on `moveend`. If those values stay in
  // this effect's deps, any later render (query, hash `#v`, layer toggle)
  // tears the map down (`destroyMapLibreMap` → WebGL context lost) and rebuilds it.
  // Pan/zoom belong on the MapLibre instance, not in React init.
  const originRef = useRef({ centerLat, centerLng, zoom });

  useEffect(() => {
    if (!containerRef.current) return;

    const removeNativeDragGuards = installMapNativeDragGuards(containerRef.current);
    const abort = new AbortController();
    let cancelled = false;
    let map: maplibregl.Map | undefined;
    const onContextLost = (event: { preventDefault?: () => void }) => {
      event.preventDefault?.();
      setMapReady(false);
    };
    const onContextRestored = () => {
      setMapReady(true);
    };

    void (async () => {
      try {
        if (cancelled || !containerRef.current) return;
        // Gestos de superficie principal: en puntero fino, Ctrl+rueda para no
        // robar el scroll. En táctil un dedo panea (`primary-surface`).
        const created = await createMapLibreMap({
          maplibre,
          gestures: 'primary-surface',
          signal: abort.signal,
          options: {
            container: containerRef.current,
            style: {
              version: 8,
              glyphs: MAP_GLYPHS_URL,
              sources: {
                'osm-base': {
                  type: 'raster',
                  tiles: [TILE_LAYERS.osm.url],
                  tileSize: 256,
                  attribution: TILE_LAYERS.osm.attribution,
                  maxzoom: 19,
                },
                'satellite-base': {
                  type: 'raster',
                  tiles: [TILE_LAYERS.satellite.url],
                  tileSize: 256,
                  attribution: TILE_LAYERS.satellite.attribution,
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
            center: [originRef.current.centerLng, originRef.current.centerLat],
            zoom: originRef.current.zoom,
            minZoom: MAP_MIN_ZOOM,
            maxBounds: MAP_MAX_BOUNDS,
            // KEPT UNCONDITIONALLY ON PURPOSE (T3c, fix 5b). PNG/PDF export reads the
            // canvas back with `getCanvas().toDataURL()`, which returns a blank image
            // unless the backbuffer is preserved. WebGL context attributes are frozen
            // at context creation: MapLibre cannot flip this after `new Map()`, so
            // "enable it only on export intent" would mean tearing the map down and
            // rebuilding it mid-session (losing viewport, sources and draw state) the
            // first time a user opens the Export menu. The cost is a modest GPU
            // memory/compositing overhead on one canvas; the alternative is a broken
            // export or a map that reloads under the user. Do not "optimize" this away
            // without moving export to an offscreen render.
            // MapLibre 5: WebGL options live under `canvasContextAttributes` (top-level
            // `preserveDrawingBuffer` was removed in 5.0.0).
            canvasContextAttributes: { preserveDrawingBuffer: true },
            // UX PDF R9: arrows and +/- when the canvas is focused (MapLibre default,
            // set explicitly so a later "optimization" cannot disable it).
            keyboard: true,
            /* Collapsed behind the info button so the credit line does not
               cover the scale or the cursor readout. */
            attributionControl: { compact: true },
            hash: 'v',
            locale: { ...MAP_LOCALE_ES },
          },
        });
        if (!created) return;
        map = created;
      } catch (error) {
        if (cancelled || abort.signal.aborted) return;
        const detail = error instanceof Error ? error.message : 'Error desconocido';
        onMapErrorRef.current?.({
          kind: 'other',
          sourceId: null,
          sourceType: null,
          status: null,
          url: null,
          message: textoError(erroresUi.cargarMapa, detail),
        });
        logger.error('MapaMapLibre failed to construct', error);
        return;
      }
      if (!map || cancelled || abort.signal.aborted || !containerRef.current) {
        destroyMapLibreMap(map);
        return;
      }

      map.addControl(new maplibre.NavigationControl({ visualizePitch: true }), 'top-right');
      map.addControl(new maplibre.FullscreenControl(), 'top-right');
      map.addControl(new maplibre.ScaleControl({ unit: 'metric' }), 'bottom-left');

      map.on('load', () => {
        setMapReady(true);
      });
      listenMapEvent(map, 'webglcontextlost', onContextLost);
      listenMapEvent(map, 'webglcontextrestored', onContextRestored);

      map.on('error', (event) => {
        const classified = classifyMapError(event);
        onMapErrorRef.current?.(classified);
        if (classified.kind !== 'tile') {
          logger.error('MapaMapLibre error', event.error);
        }
      });

      mapRef.current = map;
    })();

    return () => {
      cancelled = true;
      abort.abort();
      if (map) {
        if (typeof map.off === 'function') {
          unlistenMapEvent(map, 'webglcontextlost', onContextLost);
          unlistenMapEvent(map, 'webglcontextrestored', onContextRestored);
        }
        destroyMapLibreMap(map);
      }
      removeNativeDragGuards();
      mapRef.current = null;
      setMapReady(false);
    };
  }, [containerRef, mapRef, maplibre, setMapReady]);
}
