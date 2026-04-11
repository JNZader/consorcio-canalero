import type maplibregl from 'maplibre-gl';
import { useEffect } from 'react';

interface UseMapInitializationParams {
  maplibre: typeof maplibregl;
  containerRef: React.RefObject<HTMLDivElement | null>;
  centerLat: number;
  centerLng: number;
  zoom: number;
  mapRef: React.RefObject<maplibregl.Map | null>;
  setMapReady: (ready: boolean) => void;
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

    const map = new maplibre.Map({
      container: containerRef.current,
      style: {
        version: 8,
        sources: {
          'osm-base': {
            type: 'raster',
            tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
            tileSize: 256,
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
            maxzoom: 19,
          },
          'satellite-base': {
            type: 'raster',
            tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
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
    });

    map.addControl(new maplibre.NavigationControl(), 'top-right');
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
        'tile' in event ||
        /AJAXError/i.test(msg) ||
        /earthengine\.googleapis\.com/i.test(msg);
      if (!isTileError) {
        console.error('MapaMapLibre error:', event.error);
      }
    });

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
      setMapReady(false);
    };
  }, [centerLat, centerLng, containerRef, mapRef, maplibre, setMapReady, zoom]);
}
