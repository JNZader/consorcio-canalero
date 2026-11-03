import type { Feature, FeatureCollection, GeoJsonProperties, LineString, Point } from 'geojson';
import type * as maplibregl from 'maplibre-gl';
import { useEffect, useRef } from 'react';
import { mapColorTokens } from '../../lib/mapColorTokens';
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
  return (value?.features ?? [])
    .filter((feature): feature is typeof feature & { geometry: NonNullable<typeof feature.geometry> } => Boolean(feature?.geometry))
    .map((feature, index) => ({
      type: 'Feature',
      id: `feature-${index}`,
      geometry: feature.geometry,
      properties: {},
    }));
}

export function toSourceFeatures(
  value: DrawnLineFeatureCollection | null
): Array<Feature<Point | LineString, GeoJsonProperties>> {
  const sourceFeatures: Array<Feature<Point | LineString, GeoJsonProperties>> = [];

  for (const [featureIndex, feature] of (value?.features ?? []).entries()) {
    if (!feature?.geometry) continue;
    if (feature.geometry.type === 'Point') {
      sourceFeatures.push({
        type: 'Feature',
        id: `vertex-${featureIndex}-0`,
        geometry: {
          type: 'Point',
          coordinates: feature.geometry.coordinates,
        },
        properties: {
          feature_role: 'vertex',
          featureIndex,
          vertexIndex: 0,
        },
      });
      continue;
    }

    sourceFeatures.push({
      type: 'Feature',
      id: `feature-${featureIndex}`,
      geometry: {
        type: 'LineString',
        coordinates: feature.geometry.coordinates,
      },
      properties: {
        feature_role: 'line',
        featureIndex,
      },
    });

    for (const [vertexIndex, coord] of feature.geometry.coordinates.entries()) {
      sourceFeatures.push({
        type: 'Feature',
        id: `vertex-${featureIndex}-${vertexIndex}`,
        geometry: {
          type: 'Point',
          coordinates: coord,
        },
        properties: {
          feature_role: 'vertex',
          featureIndex,
          vertexIndex,
        },
      });
    }
  }

  return sourceFeatures;
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

export function undoLastSuggestionVertex(
  value: DrawnLineFeatureCollection | null
): DrawnLineFeatureCollection | null {
  const current = toMapFeatures(value);
  if (current.length === 0) return null;

  const last = current[current.length - 1];
  if (last.geometry.type === 'Point') {
    return buildNextValue(current.slice(0, -1));
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

  return buildNextValue(nextFeatures);
}

export function removeSuggestionVertexAt(
  value: DrawnLineFeatureCollection | null,
  featureIndex?: number,
  vertexIndex?: number
): DrawnLineFeatureCollection | null {
  const current = toMapFeatures(value);
  if (current.length === 0) return null;

  if (
    typeof featureIndex !== 'number' ||
    typeof vertexIndex !== 'number' ||
    featureIndex < 0 ||
    featureIndex >= current.length
  ) {
    return undoLastSuggestionVertex(value);
  }

  const target = current[featureIndex];
  const nextFeatures = [...current];

  if (target.geometry.type === 'Point') {
    nextFeatures.splice(featureIndex, 1);
    return buildNextValue(nextFeatures);
  }

  const remainingCoordinates = target.geometry.coordinates.filter((_, idx) => idx !== vertexIndex);
  if (remainingCoordinates.length >= 2) {
    nextFeatures[featureIndex] = {
      type: 'Feature',
      geometry: {
        type: 'LineString',
        coordinates: remainingCoordinates,
      },
      properties: {},
    };
  } else if (remainingCoordinates.length === 1) {
    nextFeatures[featureIndex] = {
      type: 'Feature',
      geometry: {
        type: 'Point',
        coordinates: remainingCoordinates[0],
      },
      properties: {},
    };
  } else {
    nextFeatures.splice(featureIndex, 1);
  }

  return buildNextValue(nextFeatures);
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
      const data = toFeatureCollection(toSourceFeatures(valueRef.current));
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
        paint: { 'line-color': mapColorTokens.h0f766e, 'line-width': 4, 'line-opacity': 0.95 },
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
          'circle-color': mapColorTokens.hdc2626,
          'circle-stroke-width': 2,
          'circle-stroke-color': mapColorTokens.hffffff,
        },
      });
    }

    const commit = (features: Array<Feature<Point | LineString, GeoJsonProperties>>) => {
      const nextValue = buildNextValue(features);
      valueRef.current = nextValue;
      onChangeRef.current(nextValue);
    };

    const handleClick = (event: maplibregl.MapMouseEvent) => {
      if (event.defaultPrevented || event.originalEvent?.defaultPrevented) {
        return;
      }

      if (
        typeof map.queryRenderedFeatures === 'function' &&
        map.getLayer(`${DRAW_SOURCE_ID}-point`)
      ) {
        const hits = map.queryRenderedFeatures(event.point, {
          layers: [`${DRAW_SOURCE_ID}-point`],
        });
        if (hits.length > 0) {
          return;
        }
      }

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

    const handleContextMenu = (
      event: maplibregl.MapMouseEvent & { originalEvent?: MouseEvent }
    ) => {
      event.preventDefault();
      event.originalEvent?.preventDefault?.();
      onChangeRef.current(undoLastSuggestionVertex(valueRef.current));
    };

    const handlePointClick = (event: maplibregl.MapLayerMouseEvent) => {
      event.preventDefault();
      event.originalEvent?.preventDefault?.();
      event.originalEvent?.stopPropagation?.();
      const hitProps = event.features?.[0]?.properties as
        | { featureIndex?: number; vertexIndex?: number }
        | undefined;
      onChangeRef.current(
        removeSuggestionVertexAt(
          valueRef.current,
          typeof hitProps?.featureIndex === 'number' ? hitProps.featureIndex : undefined,
          typeof hitProps?.vertexIndex === 'number' ? hitProps.vertexIndex : undefined
        )
      );
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
    source.setData(toFeatureCollection(toSourceFeatures(value)));
  }, [map, value]);

  return null;
}
