import { useEffect, useRef } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import type { FeatureCollection } from 'geojson';
import type { Sugerencia } from '../../../../lib/api';
import { MAP_CENTER } from '../../../../constants';

function addCanalLayers(
  map: maplibregl.Map,
  canales: Array<{
    id: string;
    data: FeatureCollection;
    style: { color?: string; weight?: number; opacity?: number };
  }>
) {
  for (const canal of canales) {
    const sourceId = `canal-${canal.id}`;
    const layerId = `canal-${canal.id}-line`;
    if (map.getSource(sourceId)) continue;
    map.addSource(sourceId, { type: 'geojson', data: canal.data });
    map.addLayer({
      id: layerId,
      type: 'line',
      source: sourceId,
      paint: {
        'line-color': canal.style.color ?? '#0B3D91',
        'line-width': canal.style.weight ?? 2,
        'line-opacity': canal.style.opacity ?? 0.8,
      },
    });
  }
}

function getGeometryBounds(geometry: FeatureCollection): [[number, number], [number, number]] | null {
  const coords: [number, number][] = [];
  for (const feature of geometry.features) {
    if (feature.geometry.type !== 'LineString') continue;
    for (const coord of feature.geometry.coordinates) {
      coords.push([coord[0] as number, coord[1] as number]);
    }
  }
  if (coords.length === 0) return null;
  const lngs = coords.map(([lng]) => lng);
  const lats = coords.map(([, lat]) => lat);
  return [
    [Math.min(...lngs), Math.min(...lats)],
    [Math.max(...lngs), Math.max(...lats)],
  ];
}

function addSuggestionGeometry(map: maplibregl.Map, geometry: FeatureCollection | null) {
  if (!geometry) return;

  map.addSource('sugerencia-geom', { type: 'geojson', data: geometry });
  map.addLayer({
    id: 'sugerencia-geom-line',
    type: 'line',
    source: 'sugerencia-geom',
    paint: { 'line-color': '#7B1FA2', 'line-width': 4, 'line-opacity': 0.95, 'line-dasharray': [8, 6] },
  });

  const bounds = getGeometryBounds(geometry);
  if (!bounds) return;
  try {
    map.fitBounds(bounds, { padding: 40, maxZoom: 14 });
  } catch {}
}

export function SugerenciaGeometryMap({
  geometry,
  canales,
}: Readonly<{
  geometry: Sugerencia['geometry'];
  canales: Array<{ id: string; data: FeatureCollection; style: { color?: string; weight?: number; opacity?: number } }>;
}>) {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<maplibregl.Map | null>(null);

  useEffect(() => {
    if (!mapContainerRef.current || mapInstanceRef.current) return;

    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: {
        version: 8,
        sources: {
          osm: {
            type: 'raster',
            tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
            tileSize: 256,
            attribution: '&copy; OpenStreetMap',
          },
        },
        layers: [{ id: 'osm', type: 'raster', source: 'osm' }],
      },
      center: [MAP_CENTER[1], MAP_CENTER[0]],
      zoom: 12,
    });

    map.on('load', () => {
      addCanalLayers(map, canales);
      addSuggestionGeometry(map, geometry as FeatureCollection | null);
    });

    mapInstanceRef.current = map;
    return () => {
      map.remove();
      mapInstanceRef.current = null;
    };
  }, [canales, geometry]);

  return <div ref={mapContainerRef} style={{ width: '100%', height: '100%' }} />;
}
