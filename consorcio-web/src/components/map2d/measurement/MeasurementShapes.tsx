/**
 * MeasurementShapes — MapLibre source+layers that persist the user's
 * measured shapes after the temporary MapboxDraw instance is unmounted.
 *
 * Why this exists
 * ---------------
 * `useMeasurement` mounts a dedicated MapboxDraw on `startDistance/startArea`
 * and unmounts it as soon as the shape is finished (so the slot mutex can
 * release and `LineDrawControl` can re-mount). MapboxDraw owns the rendering
 * of its features inside its own internal sources — when we remove the
 * control those layers vanish, taking the line/polygon visualization with
 * them. The label survives because it lives in React state; the SHAPE
 * doesn't.
 *
 * This component reads `state.measurements` (which stores the geometry per
 * entry) and keeps a single GeoJSON source `measurement-shapes` updated
 * with all measured features. Two thin layers paint them — solid blue line
 * for distances and translucent fill + outline for areas. Result: the user
 * sees the shape persist after the double-click that finishes drawing.
 */

import type { Feature, FeatureCollection, LineString, Polygon } from 'geojson';
import type maplibregl from 'maplibre-gl';
import { useEffect } from 'react';

import type { MeasurementEntry } from './useMeasurement';

const SOURCE_ID = 'measurement-shapes';
const LINE_LAYER_ID = 'measurement-shapes-line';
const POLYGON_FILL_LAYER_ID = 'measurement-shapes-polygon-fill';
const POLYGON_LINE_LAYER_ID = 'measurement-shapes-polygon-line';

const EMPTY_COLLECTION: FeatureCollection = { type: 'FeatureCollection', features: [] };

function buildFeatureCollection(measurements: readonly MeasurementEntry[]): FeatureCollection {
  if (measurements.length === 0) return EMPTY_COLLECTION;
  const features: Feature<LineString | Polygon>[] = measurements.map((m) => ({
    type: 'Feature',
    id: m.id,
    geometry: m.geometry,
    properties: { kind: m.kind, value: m.value },
  }));
  return { type: 'FeatureCollection', features };
}

function ensureSourceAndLayers(map: maplibregl.Map): void {
  if (!map.getSource(SOURCE_ID)) {
    map.addSource(SOURCE_ID, { type: 'geojson', data: EMPTY_COLLECTION });
  }
  if (!map.getLayer(POLYGON_FILL_LAYER_ID)) {
    map.addLayer({
      id: POLYGON_FILL_LAYER_ID,
      type: 'fill',
      source: SOURCE_ID,
      filter: ['==', ['geometry-type'], 'Polygon'],
      paint: {
        'fill-color': '#2563eb',
        'fill-opacity': 0.18,
      },
    });
  }
  if (!map.getLayer(POLYGON_LINE_LAYER_ID)) {
    map.addLayer({
      id: POLYGON_LINE_LAYER_ID,
      type: 'line',
      source: SOURCE_ID,
      filter: ['==', ['geometry-type'], 'Polygon'],
      paint: {
        'line-color': '#1d4ed8',
        'line-width': 2,
        'line-opacity': 0.9,
      },
    });
  }
  if (!map.getLayer(LINE_LAYER_ID)) {
    map.addLayer({
      id: LINE_LAYER_ID,
      type: 'line',
      source: SOURCE_ID,
      filter: ['==', ['geometry-type'], 'LineString'],
      paint: {
        'line-color': '#1d4ed8',
        'line-width': 3,
        'line-opacity': 0.95,
      },
    });
  }
}

export interface MeasurementShapesProps {
  readonly map: maplibregl.Map | null;
  readonly measurements: readonly MeasurementEntry[];
}

export function MeasurementShapes({ map, measurements }: MeasurementShapesProps): null {
  useEffect(() => {
    if (!map) return;

    const updateData = () => {
      ensureSourceAndLayers(map);
      const src = map.getSource(SOURCE_ID) as maplibregl.GeoJSONSource | undefined;
      if (src) src.setData(buildFeatureCollection(measurements));
    };

    if (map.isStyleLoaded()) {
      updateData();
    } else {
      map.once('load', updateData);
    }

    // Source + layers are re-installed on style reload (e.g. base layer
    // swap from OSM ↔ Satélite throws a `style.load` event after wiping
    // every custom source/layer). Re-attach so the shapes don't disappear
    // when the user toggles the basemap.
    const handleStyleLoad = () => {
      updateData();
    };
    map.on('style.load', handleStyleLoad);

    return () => {
      map.off('style.load', handleStyleLoad);
      // We intentionally do NOT remove the source/layers on unmount —
      // they're cheap, idempotent, and persisting them across hook
      // remounts (e.g. WebGL context restore) avoids a flash of nothing.
    };
  }, [map, measurements]);

  return null;
}
