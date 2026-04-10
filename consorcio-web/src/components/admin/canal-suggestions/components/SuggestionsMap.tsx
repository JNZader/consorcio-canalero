import { useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { MAP_CENTER, MAP_DEFAULT_ZOOM } from '../../../../constants';
import type { CanalSuggestion, SuggestionTipo } from '../../../../lib/api';
import { buildMapCollections, collectBoundsCoordinates } from '../canalSuggestionsUtils';

interface SuggestionsMapProps {
  readonly suggestions: CanalSuggestion[];
  readonly visibleTypes: Set<SuggestionTipo>;
}

export function SuggestionsMap({ suggestions, visibleTypes }: SuggestionsMapProps) {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<maplibregl.Map | null>(null);
  const popupRef = useRef<maplibregl.Popup | null>(null);
  const [mapReady, setMapReady] = useState(false);

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
      zoom: MAP_DEFAULT_ZOOM ?? 11,
    });

    map.on('load', () => {
      mapInstanceRef.current = map;
      setMapReady(true);
    });

    return () => {
      map.remove();
      mapInstanceRef.current = null;
      setMapReady(false);
    };
  }, []);

  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || !mapReady) return;

    const SOURCE_ID = 'suggestions-data';
    const POINTS_LAYER = 'suggestions-circles';
    const LINES_LAYER = 'suggestions-lines';
    const { filtered, pointFeatures, lineFeatures, pointsGeoJSON, linesGeoJSON } = buildMapCollections(
      suggestions,
      visibleTypes,
    );

    const pointSource = map.getSource(`${SOURCE_ID}-points`) as maplibregl.GeoJSONSource | undefined;
    const lineSource = map.getSource(`${SOURCE_ID}-lines`) as maplibregl.GeoJSONSource | undefined;

    if (pointSource) {
      pointSource.setData(pointsGeoJSON);
    } else {
      map.addSource(`${SOURCE_ID}-points`, { type: 'geojson', data: pointsGeoJSON });
      map.addLayer({
        id: POINTS_LAYER,
        type: 'circle',
        source: `${SOURCE_ID}-points`,
        paint: {
          'circle-color': ['get', 'color'],
          'circle-radius': ['get', 'radius'],
          'circle-opacity': 0.5,
          'circle-stroke-color': ['get', 'color'],
          'circle-stroke-width': 2,
          'circle-stroke-opacity': 1,
        },
      });

      map.on('click', POINTS_LAYER, (event) => {
        const feature = event.features?.[0];
        if (!feature) return;
        const { label, score, description } = feature.properties as Record<string, string | number>;
        const coords = (feature.geometry as GeoJSON.Point).coordinates as [number, number];
        popupRef.current?.remove();
        popupRef.current = new maplibregl.Popup()
          .setLngLat(coords)
          .setHTML(`<strong>${label}</strong><br/>Score: ${Number(score).toFixed(1)}${description !== '-' ? `<br/>${description}` : ''}`)
          .addTo(map);
      });

      map.on('mouseenter', POINTS_LAYER, () => {
        map.getCanvas().style.cursor = 'pointer';
      });
      map.on('mouseleave', POINTS_LAYER, () => {
        map.getCanvas().style.cursor = '';
      });
    }

    if (lineSource) {
      lineSource.setData(linesGeoJSON);
    } else {
      map.addSource(`${SOURCE_ID}-lines`, { type: 'geojson', data: linesGeoJSON });
      map.addLayer({
        id: LINES_LAYER,
        type: 'line',
        source: `${SOURCE_ID}-lines`,
        paint: {
          'line-color': ['get', 'color'],
          'line-width': ['get', 'weight'],
          'line-opacity': 0.8,
        },
      });

      map.on('click', LINES_LAYER, (event) => {
        const feature = event.features?.[0];
        if (!feature) return;
        const { label, score, description } = feature.properties as Record<string, string | number>;
        popupRef.current?.remove();
        popupRef.current = new maplibregl.Popup()
          .setLngLat(event.lngLat)
          .setHTML(`<strong>${label}</strong><br/>Score: ${Number(score).toFixed(1)}${description !== '-' ? `<br/>${description}` : ''}`)
          .addTo(map);
      });

      map.on('mouseenter', LINES_LAYER, () => {
        map.getCanvas().style.cursor = 'pointer';
      });
      map.on('mouseleave', LINES_LAYER, () => {
        map.getCanvas().style.cursor = '';
      });
    }

    if (filtered.length > 0) {
      const coords = collectBoundsCoordinates(pointFeatures, lineFeatures);
      if (coords.length > 0) {
        const lngs = coords.map(([lng]) => lng);
        const lats = coords.map(([, lat]) => lat);
        try {
          map.fitBounds(
            [
              [Math.min(...lngs), Math.min(...lats)],
              [Math.max(...lngs), Math.max(...lats)],
            ],
            { padding: 30, maxZoom: 14 },
          );
        } catch {
          // ignore invalid bounds
        }
      }
    }
  }, [suggestions, visibleTypes, mapReady]);

  return <div ref={mapContainerRef} style={{ width: '100%', height: '100%' }} />;
}
