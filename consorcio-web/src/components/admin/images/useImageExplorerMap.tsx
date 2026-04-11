import maplibregl from 'maplibre-gl';
import { useCallback, useEffect, useRef } from 'react';

import { MAP_CENTER, MAP_DEFAULT_ZOOM, MAP_MAX_BOUNDS, MAP_MIN_ZOOM } from '../../../constants';
import { useConfigStore } from '../../../stores/configStore';
import { API_URL } from '../../../lib/api';
import { logger } from '../../../lib/logger';

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
            tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
            tileSize: 256,
            attribution: 'Tiles &copy; Esri',
          },
          labels: {
            type: 'raster',
            tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}'],
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
      minZoom: MAP_MIN_ZOOM,
      maxBounds: MAP_MAX_BOUNDS,
    });
    mapInstanceRef.current = map;
    return () => {
      map.remove();
      mapInstanceRef.current = null;
    };
  }, [centerLat, centerLng, zoom]);

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
        { id: 'gee-image-layer', type: 'raster', source: 'gee-image', paint: { 'raster-opacity': 0.9 } },
        zonaLayerIdRef.current ?? undefined,
      );
      tileLayerIdRef.current = 'gee-image-layer';
    };
    if (map.isStyleLoaded()) apply();
    else map.once('load', apply);
  }, []);

  return { mapRef, updateTileLayer };
}
