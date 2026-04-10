import { useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { MAP_CENTER, MAP_DEFAULT_ZOOM } from '../../../../constants';
import type { CanalSuggestion, CorridorRoutingResponse, SuggestionTipo } from '../../../../lib/api';
import { buildMapCollections, collectBoundsCoordinates } from '../canalSuggestionsUtils';
import {
  buildCorridorAnchorCollection,
  buildCorridorMapCollections,
  collectCorridorBounds,
} from '../corridorRoutingUtils';

interface SuggestionsMapProps {
  readonly suggestions: CanalSuggestion[];
  readonly visibleTypes: Set<SuggestionTipo>;
  readonly corridorResult: CorridorRoutingResponse | null;
  readonly corridorForm: {
    fromLon: number | '';
    fromLat: number | '';
    toLon: number | '';
    toLat: number | '';
  };
  readonly corridorPickTarget: 'from' | 'to' | null;
  readonly onPickCoordinate: (coords: { lon: number; lat: number }) => void;
}

export function SuggestionsMap({
  suggestions,
  visibleTypes,
  corridorResult,
  corridorForm,
  corridorPickTarget,
  onPickCoordinate,
}: SuggestionsMapProps) {
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
    if (!map || !mapReady || !corridorPickTarget) return;

    const handleMapClick = (event: maplibregl.MapMouseEvent) => {
      onPickCoordinate({ lon: event.lngLat.lng, lat: event.lngLat.lat });
    };

    map.on('click', handleMapClick);
    return () => {
      map.off('click', handleMapClick);
    };
  }, [corridorPickTarget, mapReady, onPickCoordinate]);

  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || !mapReady) return;
    map.getCanvas().style.cursor = corridorPickTarget ? 'crosshair' : '';
  }, [corridorPickTarget, mapReady]);

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

  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || !mapReady) return;

    const { centerline, corridor, alternatives } = buildCorridorMapCollections(corridorResult);
    const centerlineSourceId = 'corridor-centerline';
    const corridorSourceId = 'corridor-polygon';
    const alternativesSourceId = 'corridor-alternatives';

    const centerlineSource = map.getSource(centerlineSourceId) as maplibregl.GeoJSONSource | undefined;
    const corridorSource = map.getSource(corridorSourceId) as maplibregl.GeoJSONSource | undefined;
    const alternativesSource = map.getSource(alternativesSourceId) as maplibregl.GeoJSONSource | undefined;

    if (centerlineSource) {
      centerlineSource.setData(centerline ?? { type: 'FeatureCollection', features: [] });
    } else {
      map.addSource(centerlineSourceId, {
        type: 'geojson',
        data: centerline ?? { type: 'FeatureCollection', features: [] },
      });
      map.addLayer({
        id: centerlineSourceId,
        type: 'line',
        source: centerlineSourceId,
        paint: {
          'line-color': '#f76707',
          'line-width': 5,
          'line-opacity': 0.95,
        },
      });
    }

    if (corridorSource) {
      corridorSource.setData(corridor ?? { type: 'FeatureCollection', features: [] });
    } else {
      map.addSource(corridorSourceId, {
        type: 'geojson',
        data: corridor ?? { type: 'FeatureCollection', features: [] },
      });
      map.addLayer({
        id: corridorSourceId,
        type: 'fill',
        source: corridorSourceId,
        paint: {
          'fill-color': '#fab005',
          'fill-opacity': 0.14,
        },
      });
      map.addLayer({
        id: `${corridorSourceId}-line`,
        type: 'line',
        source: corridorSourceId,
        paint: {
          'line-color': '#f08c00',
          'line-width': 2,
          'line-opacity': 0.7,
        },
      });
    }

    if (alternativesSource) {
      alternativesSource.setData(alternatives ?? { type: 'FeatureCollection', features: [] });
    } else {
      map.addSource(alternativesSourceId, {
        type: 'geojson',
        data: alternatives ?? { type: 'FeatureCollection', features: [] },
      });
      map.addLayer({
        id: alternativesSourceId,
        type: 'line',
        source: alternativesSourceId,
        paint: {
          'line-color': '#495057',
          'line-width': 3,
          'line-opacity': 0.55,
          'line-dasharray': [2, 2],
        },
      });
    }

    const coords = collectCorridorBounds(corridorResult);
    if (coords.length > 0) {
      const lngs = coords.map(([lng]) => lng);
      const lats = coords.map(([, lat]) => lat);
      try {
        map.fitBounds(
          [
            [Math.min(...lngs), Math.min(...lats)],
            [Math.max(...lngs), Math.max(...lats)],
          ],
          { padding: 40, maxZoom: 14 },
        );
      } catch {
        // ignore invalid bounds
      }
    }
  }, [corridorResult, mapReady]);

  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || !mapReady) return;

    const sourceId = 'corridor-anchors';
    const layerId = 'corridor-anchors';
    const anchorCollection = buildCorridorAnchorCollection(corridorForm);
    const source = map.getSource(sourceId) as maplibregl.GeoJSONSource | undefined;

    if (source) {
      source.setData(anchorCollection ?? { type: 'FeatureCollection', features: [] });
    } else {
      map.addSource(sourceId, {
        type: 'geojson',
        data: anchorCollection ?? { type: 'FeatureCollection', features: [] },
      });
      map.addLayer({
        id: layerId,
        type: 'circle',
        source: sourceId,
        paint: {
          'circle-color': ['get', 'color'],
          'circle-radius': 7,
          'circle-stroke-width': 2,
          'circle-stroke-color': '#ffffff',
        },
      });
    }
  }, [corridorForm, mapReady]);

  return <div ref={mapContainerRef} style={{ width: '100%', height: '100%' }} />;
}
