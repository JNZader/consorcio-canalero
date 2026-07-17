import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { useCallback, useEffect, useRef } from 'react';

import { MAP_BOUNDS, MAP_CENTER, MAP_DEFAULT_ZOOM } from '../../../constants';
import { API_URL } from '../../../lib/api';
import { logger } from '../../../lib/logger';
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

export function useImageExplorerMap() {
  const config = useConfigStore((state) => state.config);
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<maplibregl.Map | null>(null);
  const tileLayerIdRef = useRef<string | null>(null);
  const zonaLayerIdRef = useRef<string | null>(null);
  const centerLat = config?.map.center?.lat ?? MAP_CENTER[0];
  const centerLng = config?.map.center?.lng ?? MAP_CENTER[1];
  const zoom = config?.map.zoom ?? MAP_DEFAULT_ZOOM;

  useEffect(() => {
    if (!mapRef.current || mapInstanceRef.current) return;
    const map = new maplibregl.Map({
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
    // Start with the WHOLE consorcio visible — the fixed center+zoom default
    // cropped the zona vertically on short map heights.
    map.fitBounds(ZONA_FIT_BOUNDS, { padding: 24, animate: false });
    mapInstanceRef.current = map;
    return () => {
      map.remove();
      mapInstanceRef.current = null;
    };
  }, [centerLat, centerLng, zoom]);

  const fitZona = useCallback(() => {
    mapInstanceRef.current?.fitBounds(ZONA_FIT_BOUNDS, { padding: 24 });
  }, []);

  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;
    const addZona = (geojson: unknown) => {
      const sourceId = 'zona-boundary';
      const layerId = 'zona-boundary-line';
      if (zonaLayerIdRef.current) {
        if (map.getLayer(zonaLayerIdRef.current)) map.removeLayer(zonaLayerIdRef.current);
        if (map.getSource(sourceId)) map.removeSource(sourceId);
      }
      map.addSource(sourceId, { type: 'geojson', data: geojson as GeoJSON.FeatureCollection });
      map.addLayer({
        id: layerId,
        type: 'line',
        source: sourceId,
        paint: { 'line-color': '#FF0000', 'line-width': 3, 'line-opacity': 1 },
      });
      zonaLayerIdRef.current = layerId;
    };
    const doFetch = () => {
      fetch(`${API_URL}/api/v2/geo/gee/layers/zona`)
        .then((res) => {
          if (res.ok) return res.json();
          throw new Error('No se pudo cargar la capa zona');
        })
        .then(addZona)
        .catch((err) => logger.warn('Error cargando capa zona:', err));
    };
    if (map.isStyleLoaded()) doFetch();
    else map.once('load', doFetch);
    return () => {
      const current = mapInstanceRef.current;
      if (current && zonaLayerIdRef.current) {
        if (current.getLayer(zonaLayerIdRef.current)) current.removeLayer(zonaLayerIdRef.current);
        if (current.getSource('zona-boundary')) current.removeSource('zona-boundary');
        zonaLayerIdRef.current = null;
      }
    };
  }, []);

  const updateTileLayer = useCallback((tileUrl: string) => {
    const map = mapInstanceRef.current;
    if (!map) return;
    const apply = () => {
      if (map.getLayer('gee-image-layer')) map.removeLayer('gee-image-layer');
      if (map.getSource('gee-image')) map.removeSource('gee-image');
      map.addSource('gee-image', {
        type: 'raster',
        tiles: [tileUrl],
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
        zonaLayerIdRef.current ?? undefined
      );
      tileLayerIdRef.current = 'gee-image-layer';
    };
    if (map.isStyleLoaded()) apply();
    else map.once('load', apply);
  }, []);

  return { mapRef, updateTileLayer, fitZona };
}
