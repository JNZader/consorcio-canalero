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
import { Marker, type Map as MapLibreMap, type GeoJSONSource } from 'maplibre-gl';
import { useEffect } from 'react';
import { mapColorTokens } from '../../../lib/mapColorTokens';
import { moveLineVertex } from './measurementEdit';
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

interface StylePaintHost {
  // biome-ignore lint/suspicious/noConfusingVoidType: matches maplibre-gl isStyleLoaded signature
  isStyleLoaded: () => boolean | void;
  loaded?: () => boolean;
  once: (event: string, handler: () => void) => void;
}

/** UX-23: `load` already fired; with tiles in flight `isStyleLoaded()` is false. */
export function scheduleMeasurementShapePaint(map: StylePaintHost, paint: () => void): void {
  if (map.isStyleLoaded() || map.loaded?.()) {
    paint();
    return;
  }
  map.once('idle', paint);
}

function ensureSourceAndLayers(map: MapLibreMap): void {
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
        'fill-color': mapColorTokens.h2563eb,
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
        'line-color': mapColorTokens.h1d4ed8,
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
        'line-color': mapColorTokens.h1d4ed8,
        'line-width': 3,
        'line-opacity': 0.95,
      },
    });
  }
}

export interface MeasurementShapesProps {
  readonly map: MapLibreMap | null;
  readonly measurements: readonly MeasurementEntry[];
  readonly onMoveVertex?: (id: string, geometry: LineString) => void;
}

function createVertexMarkerElement(index: number, total: number): HTMLElement {
  const el = document.createElement('div');
  el.className = 'measurement-vertex-handle';
  el.setAttribute('role', 'button');
  el.setAttribute('tabindex', '0');
  el.setAttribute('aria-label', `Vértice ${index + 1} de ${total}`);
  el.style.width = '10px';
  el.style.height = '10px';
  el.style.borderRadius = '50%';
  el.style.backgroundColor = mapColorTokens.h7c3aed;
  el.style.border = `2px solid ${mapColorTokens.hffffff}`;
  el.style.boxShadow = '0 1px 3px rgba(0, 0, 0, 0.45)';
  el.style.cursor = 'grab';
  el.style.boxSizing = 'border-box';
  el.style.transition = 'transform 0.12s ease, box-shadow 0.12s ease';

  el.addEventListener('mouseenter', () => {
    el.style.transform = 'scale(1.35)';
    el.style.boxShadow = '0 0 0 3px rgba(124, 58, 237, 0.25), 0 2px 4px rgba(0, 0, 0, 0.4)';
  });
  el.addEventListener('mouseleave', () => {
    el.style.transform = 'scale(1)';
    el.style.boxShadow = '0 1px 3px rgba(0, 0, 0, 0.45)';
  });

  return el;
}

export function MeasurementShapes({ map, measurements, onMoveVertex }: MeasurementShapesProps): null {
  useEffect(() => {
    if (!map) return;

    const updateData = () => {
      ensureSourceAndLayers(map);
      const src = map.getSource(SOURCE_ID) as GeoJSONSource | undefined;
      if (src) src.setData(buildFeatureCollection(measurements));
    };

    scheduleMeasurementShapePaint(map, updateData);

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

  useEffect(() => {
    if (!map || !onMoveVertex) return;
    const markers: Marker[] = [];
    for (const entry of measurements) {
      if (entry.geometry.type !== 'LineString') continue;
      const total = entry.geometry.coordinates.length;
      entry.geometry.coordinates.forEach((coord, index) => {
        if (coord.length < 2) return;
        const el = createVertexMarkerElement(index, total);
        const marker = new Marker({ element: el, draggable: true })
          .setLngLat([coord[0]!, coord[1]!])
          .addTo(map);

        marker.on('dragstart', () => {
          el.style.cursor = 'grabbing';
          el.style.transform = 'scale(1.4)';
        });
        marker.on('dragend', () => {
          el.style.cursor = 'grab';
          el.style.transform = 'scale(1)';
          const lngLat = marker.getLngLat();
          onMoveVertex(
            entry.id,
            moveLineVertex(entry.geometry as LineString, index, [lngLat.lng, lngLat.lat]),
          );
        });
        markers.push(marker);
      });
    }
    return () => {
      for (const marker of markers) marker.remove();
    };
  }, [map, measurements, onMoveVertex]);

  return null;
}
