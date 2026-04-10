import { useEffect, useRef } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import type { FeatureCollection } from 'geojson';
import type { Sugerencia } from '../../../../lib/api';
import { MAP_CENTER } from '../../../../constants';

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
      for (const canal of canales) {
        const sourceId = `canal-${canal.id}`;
        const layerId = `canal-${canal.id}-line`;
        if (!map.getSource(sourceId)) {
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

      if (geometry) {
        map.addSource('sugerencia-geom', { type: 'geojson', data: geometry as FeatureCollection });
        map.addLayer({
          id: 'sugerencia-geom-line',
          type: 'line',
          source: 'sugerencia-geom',
          paint: { 'line-color': '#7B1FA2', 'line-width': 4, 'line-opacity': 0.95, 'line-dasharray': [8, 6] },
        });

        const coords: [number, number][] = [];
        for (const f of (geometry as FeatureCollection).features) {
          if (f.geometry.type === 'LineString') {
            for (const c of f.geometry.coordinates) coords.push([c[0] as number, c[1] as number]);
          }
        }
        if (coords.length > 0) {
          const lngs = coords.map(([lng]) => lng);
          const lats = coords.map(([, lat]) => lat);
          try {
            map.fitBounds(
              [[Math.min(...lngs), Math.min(...lats)], [Math.max(...lngs), Math.max(...lats)]],
              { padding: 40, maxZoom: 14 }
            );
          } catch {}
        }
      }
    });

    mapInstanceRef.current = map;
    return () => {
      map.remove();
      mapInstanceRef.current = null;
    };
  }, [canales, geometry]);

  return <div ref={mapContainerRef} style={{ width: '100%', height: '100%' }} />;
}
