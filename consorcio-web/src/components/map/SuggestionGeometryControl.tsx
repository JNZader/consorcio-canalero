import type { Feature, FeatureCollection, GeoJsonProperties, LineString, Point } from 'geojson';
import type maplibregl from 'maplibre-gl';
import { useEffect, useRef } from 'react';
import type { DrawnLineFeatureCollection } from './LineDrawControl';

interface SuggestionGeometryControlProps {
  readonly map: maplibregl.Map;
  readonly value: DrawnLineFeatureCollection | null;
  readonly onChange: (geometry: DrawnLineFeatureCollection | null) => void;
}

const DRAW_SOURCE_ID = 'suggestion-geometry-source';

function toFeatureCollection(
  features: Array<Feature<Point | LineString, GeoJsonProperties>>
): FeatureCollection<Point | LineString, GeoJsonProperties> {
  return { type: 'FeatureCollection', features };
}

function toMapFeatures(
  value: DrawnLineFeatureCollection | null
): Array<Feature<Point | LineString, GeoJsonProperties>> {
  return (value?.features ?? []).map((feature, index) => ({
    type: 'Feature',
    id: `feature-${index}`,
    geometry: feature.geometry,
    properties: {},
  }));
}

function buildNextValue(
  features: Array<Feature<Point | LineString, GeoJsonProperties>>
): DrawnLineFeatureCollection | null {
  if (features.length === 0) return null;

  return {
    type: 'FeatureCollection',
    features: features.map((feature) =>
      feature.geometry.type === 'Point'
        ? {
            type: 'Feature' as const,
            geometry: {
              type: 'Point' as const,
              coordinates: feature.geometry.coordinates,
            },
            properties: {},
          }
        : {
            type: 'Feature' as const,
            geometry: {
              type: 'LineString' as const,
              coordinates: feature.geometry.coordinates,
            },
            properties: {},
          }
    ),
  };
}

export default function SuggestionGeometryControl({
  map,
  value,
  onChange,
}: SuggestionGeometryControlProps) {
  const valueRef = useRef(value);
  const onChangeRef = useRef(onChange);

  valueRef.current = value;
  onChangeRef.current = onChange;

  useEffect(() => {
    const ensureSource = () => {
      const source = map.getSource(DRAW_SOURCE_ID) as maplibregl.GeoJSONSource | undefined;
      const data = toFeatureCollection(toMapFeatures(valueRef.current));
      if (source) {
        source.setData(data);
        return;
      }
      map.addSource(DRAW_SOURCE_ID, { type: 'geojson', data });
    };

    ensureSource();

    if (!map.getLayer(`${DRAW_SOURCE_ID}-line`)) {
      map.addLayer({
        id: `${DRAW_SOURCE_ID}-line`,
        type: 'line',
        source: DRAW_SOURCE_ID,
        filter: ['==', '$type', 'LineString'],
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: { 'line-color': '#0f766e', 'line-width': 4, 'line-opacity': 0.95 },
      });
    }

    if (!map.getLayer(`${DRAW_SOURCE_ID}-point`)) {
      map.addLayer({
        id: `${DRAW_SOURCE_ID}-point`,
        type: 'circle',
        source: DRAW_SOURCE_ID,
        filter: ['==', '$type', 'Point'],
        paint: {
          'circle-radius': 8,
          'circle-color': '#dc2626',
          'circle-stroke-width': 2,
          'circle-stroke-color': '#ffffff',
        },
      });
    }

    const commit = (features: Array<Feature<Point | LineString, GeoJsonProperties>>) => {
      onChangeRef.current(buildNextValue(features));
    };

    const handleClick = (event: maplibregl.MapMouseEvent) => {
      const nextCoordinate: [number, number] = [event.lngLat.lng, event.lngLat.lat];
      const current = toMapFeatures(valueRef.current);
      const last = current[current.length - 1];

      if (!last) {
        commit([
          {
            type: 'Feature',
            geometry: { type: 'Point', coordinates: nextCoordinate },
            properties: {},
          },
        ]);
        return;
      }

      if (last.geometry.type === 'Point') {
        const nextFeatures = current.slice(0, -1);
        nextFeatures.push({
          type: 'Feature',
          geometry: {
            type: 'LineString',
            coordinates: [last.geometry.coordinates as [number, number], nextCoordinate],
          },
          properties: {},
        });
        commit(nextFeatures);
        return;
      }

      const nextFeatures = current.slice(0, -1);
      nextFeatures.push({
        type: 'Feature',
        geometry: {
          type: 'LineString',
          coordinates: [...last.geometry.coordinates, nextCoordinate],
        },
        properties: {},
      });
      commit(nextFeatures);
    };

    const handleContextMenu = (event: maplibregl.MapMouseEvent & { originalEvent: MouseEvent }) => {
      event.preventDefault();
      event.originalEvent.preventDefault();

      const current = toMapFeatures(valueRef.current);
      if (current.length === 0) return;

      const last = current[current.length - 1];
      if (last.geometry.type === 'Point') {
        commit(current.slice(0, -1));
        return;
      }

      const remainingCoordinates = last.geometry.coordinates.slice(0, -1);
      const nextFeatures = current.slice(0, -1);

      if (remainingCoordinates.length >= 2) {
        nextFeatures.push({
          type: 'Feature',
          geometry: {
            type: 'LineString',
            coordinates: remainingCoordinates,
          },
          properties: {},
        });
      } else if (remainingCoordinates.length === 1) {
        nextFeatures.push({
          type: 'Feature',
          geometry: {
            type: 'Point',
            coordinates: remainingCoordinates[0],
          },
          properties: {},
        });
      }

      commit(nextFeatures);
    };

    const handlePointClick = (event: maplibregl.MapLayerMouseEvent) => {
      event.preventDefault();
      const features = toMapFeatures(valueRef.current);
      if (features.length === 0) return;
      commit(features.slice(0, -1));
    };

    map.getCanvas().style.cursor = 'crosshair';
    map.on('click', handleClick);
    map.on('contextmenu', handleContextMenu);
    map.on('click', `${DRAW_SOURCE_ID}-point`, handlePointClick);

    return () => {
      try {
        map.off('click', handleClick);
        map.off('contextmenu', handleContextMenu);
        map.off('click', `${DRAW_SOURCE_ID}-point`, handlePointClick);
        map.getCanvas().style.cursor = '';

        if (!map.getStyle()) return;

        if (map.getLayer(`${DRAW_SOURCE_ID}-point`)) map.removeLayer(`${DRAW_SOURCE_ID}-point`);
        if (map.getLayer(`${DRAW_SOURCE_ID}-line`)) map.removeLayer(`${DRAW_SOURCE_ID}-line`);
        if (map.getSource(DRAW_SOURCE_ID)) map.removeSource(DRAW_SOURCE_ID);
      } catch {
        // Ignore teardown races when the parent map is already being destroyed
      }
    };
  }, [map]);

  useEffect(() => {
    const source = map.getSource(DRAW_SOURCE_ID) as maplibregl.GeoJSONSource | undefined;
    if (!source) return;
    source.setData(toFeatureCollection(toMapFeatures(value)));
  }, [map, value]);

  return null;
}
