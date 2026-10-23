import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { useCallback, useEffect, useRef } from 'react';
import { MAP_BOUNDS, MAP_CENTER, MAP_DEFAULT_ZOOM } from '../../../constants';
import { apiFetch, GEE_TIMEOUT } from '../../../lib/api';
import { logger } from '../../../lib/logger';
import { mapColorTokens } from '../../../lib/mapColorTokens';
import { bootMapLibreWorker } from '../../../lib/maplibreLoader';
import { useConfigStore } from '../../../stores/configStore';

/**
 * The admin image explorer is an ANALYSIS tool, not the guarded public map:
 * an operator inspecting a regional flood needs to pan upstream (Río Tercero)
 * and zoom out for context. So it gets looser limits than the public
 * MAP_MAX_BOUNDS/MAP_MIN_ZOOM — ±3° (~300 km) around the consorcio and
 * province-level zoom — plus a "fit zona" control to come back in one click.
 */
const EXPLORER_MAX_BOUNDS: [[number, number], [number, number]] = [
  [MAP_BOUNDS.west - 3, MAP_BOUNDS.south - 3],
  [MAP_BOUNDS.east + 3, MAP_BOUNDS.north + 3],
];
const EXPLORER_MIN_ZOOM = 6;

const ZONA_FIT_BOUNDS: [[number, number], [number, number]] = [
  [MAP_BOUNDS.west, MAP_BOUNDS.south],
  [MAP_BOUNDS.east, MAP_BOUNDS.north],
];

function applyGeeRaster(map: maplibregl.Map, url: string, beforeId: string | null) {
  if (map.getLayer('gee-water-mask')) map.removeLayer('gee-water-mask');
  if (map.getSource('gee-water')) map.removeSource('gee-water');
  if (map.getLayer('gee-image-layer')) map.removeLayer('gee-image-layer');
  if (map.getSource('gee-image')) map.removeSource('gee-image');
  map.addSource('gee-image', {
    type: 'raster',
    tiles: [url],
    tileSize: 256,
    attribution: 'Imagery &copy; Google Earth Engine',
  });
  map.addLayer(
    {
      id: 'gee-image-layer',
      type: 'raster',
      source: 'gee-image',
      paint: { 'raster-opacity': 0.9 },
    },
    beforeId ?? undefined
  );
}

export function useImageExplorerMap() {
  const config = useConfigStore((state) => state.config);
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<maplibregl.Map | null>(null);
  const tileLayerIdRef = useRef<string | null>(null);
  const zonaLayerIdRef = useRef<string | null>(null);
  /** Última URL pedida; la aplica quien llegue a correr, sea ahora o en `idle`. */
  const pendingTileUrlRef = useRef<string | null>(null);
  /** Evita apilar listeners de `idle` cuando llegan varias URLs seguidas. */
  const idleWaitRef = useRef(false);
  const centerLat = config?.map.center?.lat ?? MAP_CENTER[0];
  const centerLng = config?.map.center?.lng ?? MAP_CENTER[1];
  const zoom = config?.map.zoom ?? MAP_DEFAULT_ZOOM;

  useEffect(() => {
    let cancelled = false;
    let map: maplibregl.Map | null = null;
    let resizeObserver: ResizeObserver | null = null;
    // Lets cleanup drop a still-pending `once('load', fetchZona)` listener.
    let offZonaLoadListener: (() => void) | null = null;
    const zonaController = new AbortController();
    void (async () => {
      await bootMapLibreWorker();
      if (cancelled || !mapRef.current || mapInstanceRef.current) return;
      map = new maplibregl.Map({
        container: mapRef.current,
        style: {
          version: 8,
          sources: {
            satellite: {
              type: 'raster',
              tiles: [
                'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
              ],
              tileSize: 256,
              attribution: 'Tiles &copy; Esri',
            },
            labels: {
              type: 'raster',
              tiles: [
                'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',
              ],
              tileSize: 256,
            },
          },
          layers: [
            { id: 'satellite', type: 'raster', source: 'satellite' },
            { id: 'labels', type: 'raster', source: 'labels' },
          ],
        },
        center: [centerLng, centerLat],
        zoom,
        minZoom: EXPLORER_MIN_ZOOM,
        maxBounds: EXPLORER_MAX_BOUNDS,
      });
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
      map.addControl(new maplibregl.FullscreenControl(), 'top-right');
      map.fitBounds(ZONA_FIT_BOUNDS, { padding: 24, animate: false });
      mapInstanceRef.current = map;
      const container = mapRef.current;
      resizeObserver =
        container && typeof ResizeObserver !== 'undefined'
          ? new ResizeObserver(() => {
              map?.resize();
            })
          : null;
      if (container) resizeObserver?.observe(container);

      // Zona boundary — audit 2026-10 finding C4 (regression from 84c0a9c4):
      // this fetch/add used to live in a SEPARATE effect with deps `[]`. That
      // effect ran in the same passive-effects flush as this one, but
      // `mapInstanceRef.current` is only assigned AFTER `await
      // bootMapLibreWorker()` — i.e. in a later microtask. The zona effect
      // therefore read `null`, early-returned, and nothing ever re-ran it
      // (deps `[]`, no state/timeout retrigger, cleanup nulls the ref), so the
      // red consorcio boundary NEVER rendered and `zonaLayerIdRef` stayed
      // null — dropping the `beforeId` slot `applyGeeRaster`/`updateWaterMask`
      // use to slot rasters UNDER the boundary line. Fetching here, after map
      // creation (mirroring the `pendingTileUrlRef` wiring below), guarantees
      // the map exists and re-runs naturally when a config change re-creates
      // the map. It must run BEFORE the pending-raster block so a raster
      // arriving in the same synchronous pass already finds the zona layer as
      // its `beforeId`.
      const addZonaLayer = (geojson: unknown) => {
        const live = mapInstanceRef.current;
        if (cancelled || live === null || live !== map) return;
        const sourceId = 'zona-boundary';
        const layerId = 'zona-boundary-line';
        if (live.getLayer(layerId)) live.removeLayer(layerId);
        if (live.getSource(sourceId)) live.removeSource(sourceId);
        live.addSource(sourceId, {
          type: 'geojson',
          data: geojson as GeoJSON.FeatureCollection,
        });
        live.addLayer({
          id: layerId,
          type: 'line',
          source: sourceId,
          paint: { 'line-color': mapColorTokens.hFF0000, 'line-width': 3, 'line-opacity': 1 },
        });
        zonaLayerIdRef.current = layerId;
      };
      const fetchZona = () => {
        apiFetch<unknown>('/geo/gee/layers/zona', {
          signal: zonaController.signal,
          timeout: GEE_TIMEOUT,
        })
          .then(addZonaLayer)
          .catch((err) => {
            if (!zonaController.signal.aborted) logger.warn('Error cargando capa zona:', err);
          });
      };
      // Same gate the old effect used: MapLibre needs the style live before
      // sources/layers can be added. `once` (not `on`) — this must fire a
      // single time per map instance; cleanup aborts the fetch if it never
      // got to run.
      if (map.isStyleLoaded()) fetchZona();
      else {
        map.once('load', fetchZona);
        offZonaLoadListener = () => map?.off('load', fetchZona);
      }

      const pending = pendingTileUrlRef.current;
      if (pending) {
        if (map.isStyleLoaded()) {
          applyGeeRaster(map, pending, zonaLayerIdRef.current);
          tileLayerIdRef.current = 'gee-image-layer';
        } else if (!idleWaitRef.current) {
          idleWaitRef.current = true;
          map.once('idle', () => {
            idleWaitRef.current = false;
            const url = pendingTileUrlRef.current;
            const live = mapInstanceRef.current;
            if (!url || !live) return;
            applyGeeRaster(live, url, zonaLayerIdRef.current);
            tileLayerIdRef.current = 'gee-image-layer';
          });
        }
      }
    })();
    return () => {
      cancelled = true;
      zonaController.abort();
      offZonaLoadListener?.();
      resizeObserver?.disconnect();
      // `map.remove()` destroys all layers/sources (zona included); the ref
      // MUST be nulled separately so `applyGeeRaster` never receives a
      // `beforeId` that no longer exists on the next map instance — MapLibre
      // throws on `addLayer` with a non-existent `beforeId`.
      map?.remove();
      mapInstanceRef.current = null;
      zonaLayerIdRef.current = null;
    };
  }, [centerLat, centerLng, zoom]);

  const fitZona = useCallback(() => {
    mapInstanceRef.current?.fitBounds(ZONA_FIT_BOUNDS, { padding: 24 });
  }, []);

  const updateTileLayer = useCallback((tileUrl: string) => {
    // Queue even if MapLibre is still booting the worker — otherwise a 200 from
    // GEE is discarded and the explorer stays on the empty Esri basemap.
    pendingTileUrlRef.current = tileUrl;
    const map = mapInstanceRef.current;
    if (!map) return;

    const apply = () => {
      const url = pendingTileUrlRef.current;
      if (!url) return;
      applyGeeRaster(map, url, zonaLayerIdRef.current);
      tileLayerIdRef.current = 'gee-image-layer';
    };

    if (map.isStyleLoaded()) {
      apply();
      return;
    }

    // `idle` y NO `load`. El evento `load` de MapLibre dispara UNA sola vez en
    // toda la vida del mapa —lo guarda un flag `_loaded` en el propio Map— asi
    // que para el segundo cambio de imagen ya disparo y el callback no corre
    // nunca: la actualizacion se perdia EN SILENCIO.
    //
    // Y se caia en esta rama seguido, porque `isStyleLoaded()` no mira solo el
    // estilo: agrega el estado de los tiles. Con tiles de Earth Engine que
    // tardan 20-35 segundos (medido en produccion), cualquier cambio de
    // visualizacion durante esa ventana se descartaba. Sintoma: "cambio la
    // visualizacion y no hace nada".
    //
    // `idle` vuelve a dispararse cada vez que el mapa termina de acomodarse.
    if (idleWaitRef.current) return; // ya hay uno en cola; usara la URL nueva
    idleWaitRef.current = true;
    map.once('idle', () => {
      idleWaitRef.current = false;
      apply();
    });
  }, []);

  const updateWaterMask = useCallback((tileUrl: string | null) => {
    const map = mapInstanceRef.current;
    if (!map) return;
    if (map.getLayer('gee-water-mask')) map.removeLayer('gee-water-mask');
    if (map.getSource('gee-water')) map.removeSource('gee-water');
    if (!tileUrl) return;
    map.addSource('gee-water', {
      type: 'raster',
      tiles: [tileUrl],
      tileSize: 256,
      attribution: 'Imagery &copy; Google Earth Engine',
    });
    map.addLayer(
      {
        id: 'gee-water-mask',
        type: 'raster',
        source: 'gee-water',
        paint: { 'raster-opacity': 0.65 },
      },
      zonaLayerIdRef.current ?? undefined
    );
  }, []);

  return { mapRef, updateTileLayer, updateWaterMask, fitZona };
}
