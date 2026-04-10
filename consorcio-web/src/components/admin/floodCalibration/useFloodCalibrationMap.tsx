import maplibregl from 'maplibre-gl';
import type { FeatureCollection } from 'geojson';
import { useCallback, useEffect, useRef, useState } from 'react';

import { API_URL } from '../../../lib/api';
import { logger } from '../../../lib/logger';
import { MAP_CENTER, MAP_DEFAULT_ZOOM } from '../../../constants';
import { useConfigStore } from '../../../stores/configStore';
import { useFloodCalibrationStore } from '../../../stores/floodCalibrationStore';
import { getZonePaint } from './floodCalibrationUtils';

const API_BASE = `${API_URL}/api/v2/geo/gee/images`;
const BASINS_URL = `${API_URL}/api/v2/geo/basins`;

export function useFloodCalibrationMap() {
  const config = useConfigStore((state) => state.config);
  const labeledZones = useFloodCalibrationStore((s) => s.labeledZones);
  const toggleZoneLabel = useFloodCalibrationStore.getState().toggleZoneLabel;

  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<maplibregl.Map | null>(null);
  const tileLayerIdRef = useRef<string | null>(null);
  const zonasDataRef = useRef<FeatureCollection | null>(null);
  const [mapReady, setMapReady] = useState(false);
  const [loadingImage, setLoadingImage] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const renderZonas = useCallback((map: maplibregl.Map, geojson: FeatureCollection) => {
    const currentLabels = useFloodCalibrationStore.getState().labeledZones;
    const colored: FeatureCollection = {
      type: 'FeatureCollection',
      features: geojson.features.map((f) => {
        const zonaId = String(f.properties?.id || f.id);
        const paint = getZonePaint(zonaId, currentLabels);
        return {
          ...f,
          properties: {
            ...f.properties,
            _fillColor: paint.fillColor,
            _color: paint.color,
            _fillOpacity: paint.fillOpacity,
          },
        };
      }),
    };

    if (map.getSource('zonas')) {
      (map.getSource('zonas') as maplibregl.GeoJSONSource).setData(colored);
      return;
    }

    map.addSource('zonas', { type: 'geojson', data: colored });
    map.addLayer({
      id: 'zonas-fill',
      type: 'fill',
      source: 'zonas',
      paint: { 'fill-color': ['get', '_fillColor'], 'fill-opacity': ['get', '_fillOpacity'] },
    });
    map.addLayer({
      id: 'zonas-line',
      type: 'line',
      source: 'zonas',
      paint: { 'line-color': ['get', '_color'], 'line-width': 2 },
    });
    map.on('click', 'zonas-fill', (e) => {
      const feature = e.features?.[0];
      if (!feature) return;
      toggleZoneLabel(String(feature.properties?.id || feature.id));
    });
    map.on('mouseenter', 'zonas-fill', () => { map.getCanvas().style.cursor = 'pointer'; });
    map.on('mouseleave', 'zonas-fill', () => { map.getCanvas().style.cursor = ''; });
  }, [toggleZoneLabel]);

  const updateTileLayer = useCallback((tileUrl: string) => {
    const map = mapInstanceRef.current;
    if (!map) return;
    const apply = () => {
      if (tileLayerIdRef.current) {
        if (map.getLayer('gee-cal-layer')) map.removeLayer('gee-cal-layer');
        if (map.getSource('gee-cal')) map.removeSource('gee-cal');
      }
      map.addSource('gee-cal', {
        type: 'raster',
        tiles: [tileUrl],
        tileSize: 256,
        attribution: 'Imagery &copy; Google Earth Engine',
      });
      map.addLayer(
        { id: 'gee-cal-layer', type: 'raster', source: 'gee-cal', paint: { 'raster-opacity': 0.85 } },
        map.getLayer('zonas-fill') ? 'zonas-fill' : undefined,
      );
      tileLayerIdRef.current = 'gee-cal-layer';
    };
    if (map.isStyleLoaded()) apply();
    else map.once('load', apply);
  }, []);

  const fetchImageForDate = useCallback(async (dateStr: string) => {
    setLoadingImage(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        target_date: dateStr,
        days_buffer: '1',
        visualization: 'rgb',
        max_cloud: '40',
      });
      const response = await fetch(`${API_BASE}/sentinel2?${params}`);
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Error al obtener imagen');
      }
      const data = await response.json();
      updateTileLayer(data.tile_url);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido');
    } finally {
      setLoadingImage(false);
    }
  }, [updateTileLayer]);

  useEffect(() => {
    if (!mapRef.current || mapInstanceRef.current) return;
    const lat = config?.map.center?.lat ?? MAP_CENTER[0];
    const lng = config?.map.center?.lng ?? MAP_CENTER[1];
    const zoom = config?.map.zoom ?? MAP_DEFAULT_ZOOM;
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
      center: [lng, lat],
      zoom,
    });
    mapInstanceRef.current = map;
    return () => {
      map.remove();
      mapInstanceRef.current = null;
    };
  }, [config?.map.center, config?.map.zoom]);

  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;
    if (map.isStyleLoaded()) setMapReady(true);
    else map.once('load', () => setMapReady(true));
  });

  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || !mapReady) return;
    fetch(BASINS_URL)
      .then((res) => {
        if (res.ok) return res.json();
        throw new Error('No se pudieron cargar las zonas operativas');
      })
      .then((geojson: FeatureCollection) => {
        zonasDataRef.current = geojson;
        renderZonas(map, geojson);
      })
      .catch((err) => logger.warn('Error cargando zonas operativas:', err));
    return () => {
      const currentMap = mapInstanceRef.current;
      if (!currentMap) return;
      ['zonas-fill', 'zonas-line'].forEach((id) => {
        if (currentMap.getLayer(id)) currentMap.removeLayer(id);
      });
      if (currentMap.getSource('zonas')) currentMap.removeSource('zonas');
    };
  }, [mapReady, renderZonas]);

  useEffect(() => {
    const map = mapInstanceRef.current;
    const geojson = zonasDataRef.current;
    if (!map || !geojson || !mapReady) return;
    renderZonas(map, geojson);
  }, [labeledZones, mapReady, renderZonas]);

  return { mapRef, loadingImage, error, fetchImageForDate };
}
