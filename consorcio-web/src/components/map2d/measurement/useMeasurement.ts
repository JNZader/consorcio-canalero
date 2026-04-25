/**
 * useMeasurement — hook that owns the measurement MapboxDraw instance.
 *
 * Lifecycle (mirrors `LineDrawControl.tsx`'s cleanup pattern but without
 * the controlled-component value/onChange plumbing — measurements are
 * hook-local state, not form state):
 *
 *   1. On mount (once `map` is non-null):
 *      - Create a DEDICATED `MapboxDraw` via `createMeasurementDraw()`.
 *        We never share with `LineDrawControl`, so `clear()` is
 *        physically incapable of wiping canales.
 *      - Clean any stale `mapbox-gl-draw-*` sources/layers
 *        (`removeMapboxDrawArtifacts`) — defends against WebGL context
 *        loss+restore, same as canales' draw control.
 *      - `map.addControl(draw)` and subscribe to `draw.create`.
 *
 *   2. User flow:
 *      - `startDistance()` / `startArea()` → `draw.changeMode(...)` and
 *        transition `state.mode` so the toolbar can highlight the
 *        active button.
 *      - When the user finishes a shape, `draw.create` fires. We compute
 *        the measurement value (meters for lines, m² for polygons) via
 *        Turf, compute the label anchor (line midpoint or polygon
 *        center-of-mass), and push a new `MeasurementEntry`.
 *        `state.mode` stays active so consecutive measurements feel
 *        continuous; `cancel()` / `clear()` exit measuring mode explicitly.
 *
 *   3. `clear()` calls `draw.deleteAll()` + resets state.
 *      `cancel()` flips back to `simple_select` WITHOUT saving.
 *
 *   4. On unmount: remove listener, `map.removeControl`, and run
 *      `removeMapboxDrawArtifacts` a second time to be defensive
 *      about orphan layers.
 *
 * The hook is deliberately unaware of LABEL RENDERING — that's Batch C.
 * For now, `labelPosition` is computed and stored; Batch C will overlay
 * a Marker/Popup at each position using `formatDistance` / `formatArea`.
 *
 * INVARIANT: the `clear()` method NEVER touches LineDrawControl features,
 * because the measurement MapboxDraw instance is dedicated to this hook.
 * Cross-instance contamination is physically impossible — documented
 * here because the proposal calls it out explicitly.
 */

import type { Feature, LineString, Point, Polygon } from 'geojson';
import type maplibregl from 'maplibre-gl';
import type MapboxDraw from '@mapbox/mapbox-gl-draw';
import { useCallback, useEffect, useRef, useState } from 'react';

import area from '@turf/area';
import centerOfMass from '@turf/center-of-mass';
import length from '@turf/length';
import midpoint from '@turf/midpoint';

import { removeMapboxDrawArtifacts } from '../../map/mapboxDrawShared';
import { createMeasurementDraw } from './measurementDrawModes';

// ─── Types ──────────────────────────────────────────────────────────────

export type MeasurementMode = 'idle' | 'measuring-distance' | 'measuring-area';

export interface MeasurementEntry {
  /** Stable id — taken straight from the MapboxDraw feature id. */
  id: string;
  /** Distance (length in meters) or area (square meters). */
  kind: 'distance' | 'area';
  /** Meters for distance, square meters for area. */
  value: number;
  /**
   * Anchor for the label Marker/Popup, as [lng, lat].
   * - Distance: midpoint between the first and the last vertex.
   * - Area: polygon center-of-mass.
   */
  labelPosition: [number, number];
}

export interface MeasurementState {
  mode: MeasurementMode;
  measurements: MeasurementEntry[];
}

type MeasurementStateUpdater = MeasurementState | ((prev: MeasurementState) => MeasurementState);

export interface UseMeasurementReturn {
  state: MeasurementState;
  startDistance: () => void;
  startArea: () => void;
  clear: () => void;
  cancel: () => void;
}

// ─── Helpers ────────────────────────────────────────────────────────────

function coerceId(raw: unknown, fallback: string): string {
  if (typeof raw === 'string') return raw;
  if (typeof raw === 'number') return String(raw);
  return fallback;
}

function computeLineLabelAnchor(line: Feature<LineString>): [number, number] {
  const coords = line.geometry.coordinates;
  if (coords.length === 0) return [0, 0];
  const first = coords[0];
  const last = coords[coords.length - 1];
  const firstPt: Feature<Point> = {
    type: 'Feature',
    geometry: { type: 'Point', coordinates: first },
    properties: {},
  };
  const lastPt: Feature<Point> = {
    type: 'Feature',
    geometry: { type: 'Point', coordinates: last },
    properties: {},
  };
  const mid = midpoint(firstPt, lastPt);
  const [lng, lat] = mid.geometry.coordinates;
  return [lng, lat];
}

function computePolygonLabelAnchor(poly: Feature<Polygon>): [number, number] {
  const centroid = centerOfMass(poly);
  const [lng, lat] = centroid.geometry.coordinates;
  return [lng, lat];
}

// ─── Hook ───────────────────────────────────────────────────────────────

export function useMeasurement(map: maplibregl.Map | null): UseMeasurementReturn {
  const [state, setState] = useState<MeasurementState>({
    mode: 'idle',
    measurements: [],
  });
  const modeRef = useRef<MeasurementMode>('idle');
  const drawRef = useRef<MapboxDraw | null>(null);

  const setMeasurementState = useCallback((updater: MeasurementStateUpdater) => {
    setState((prev) => {
      const next = typeof updater === 'function' ? updater(prev) : updater;
      modeRef.current = next.mode;
      return next;
    });
  }, []);

  const setMeasurementCursor = useCallback(
    (active: boolean) => {
      if (!map) return;
      map.getCanvas().style.cursor = active ? 'crosshair' : '';
    },
    [map]
  );

  useEffect(() => {
    if (!map) return;

    const draw = createMeasurementDraw();
    drawRef.current = draw;

    // Same defensive cleanup as LineDrawControl — WebGL context lost+restored
    // can leave orphan `gl-draw-*` layers behind.
    removeMapboxDrawArtifacts(map);

    // MapboxDraw targets the same GL control API as maplibre-gl.
    map.addControl(draw as unknown as maplibregl.IControl);

    const handleCreate = (event: unknown) => {
      const features = (event as { features?: Feature[] })?.features ?? [];
      const entries: MeasurementEntry[] = [];

      for (const feature of features) {
        const geom = feature.geometry;
        const featureId = coerceId(
          (feature as { id?: unknown }).id,
          `measurement-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
        );

        if (geom.type === 'LineString') {
          const line = feature as Feature<LineString>;
          const meters = length(line, { units: 'meters' });
          const labelPosition = computeLineLabelAnchor(line);
          const entry: MeasurementEntry = {
            id: featureId,
            kind: 'distance',
            value: meters,
            labelPosition,
          };
          entries.push(entry);
        } else if (geom.type === 'Polygon') {
          const poly = feature as Feature<Polygon>;
          const m2 = area(poly);
          const labelPosition = computePolygonLabelAnchor(poly);
          const entry: MeasurementEntry = {
            id: featureId,
            kind: 'area',
            value: m2,
            labelPosition,
          };
          entries.push(entry);
        }
      }

      if (entries.length === 0) return;

      const currentMode = modeRef.current;
      const nextMode =
        currentMode === 'measuring-distance' || currentMode === 'measuring-area'
          ? currentMode
          : 'idle';

      setMeasurementState((prev) => ({
        mode: nextMode,
        measurements: [...prev.measurements, ...entries],
      }));

      if (nextMode === 'measuring-distance') {
        draw.changeMode('draw_line_string');
      } else if (nextMode === 'measuring-area') {
        draw.changeMode('draw_polygon');
      }
    };

    const handleContextLost = () => {
      removeMapboxDrawArtifacts(map);
    };

    map.on('draw.create', handleCreate);
    map.on('webglcontextlost', handleContextLost);

    return () => {
      map.off('draw.create', handleCreate);
      map.off('webglcontextlost', handleContextLost);
      try {
        // Remove draw layers/sources before calling MapboxDraw's onRemove.
        // After WebGL context loss MapboxDraw can lose track of its suffixed
        // custom style layer IDs and try to remove the shared sources first,
        // which MapLibre rejects while measurement layers still reference
        // them.
        removeMapboxDrawArtifacts(map);
        const control = draw as unknown as maplibregl.IControl;
        if (map.hasControl(control)) {
          map.removeControl(control);
        }
      } catch {
        // ignore — removal can race with map teardown
      }
      setMeasurementCursor(false);
      removeMapboxDrawArtifacts(map);
      drawRef.current = null;
    };
  }, [map, setMeasurementCursor, setMeasurementState]);

  const startDistance = () => {
    const draw = drawRef.current;
    if (draw) draw.changeMode('draw_line_string');
    setMeasurementCursor(true);
    setMeasurementState((prev) => ({ ...prev, mode: 'measuring-distance' }));
  };

  const startArea = () => {
    const draw = drawRef.current;
    if (draw) draw.changeMode('draw_polygon');
    setMeasurementCursor(true);
    setMeasurementState((prev) => ({ ...prev, mode: 'measuring-area' }));
  };

  const clear = () => {
    const draw = drawRef.current;
    if (draw) draw.deleteAll();
    setMeasurementCursor(false);
    // NOTE: this ONLY clears the measurement draw instance. LineDrawControl
    // uses its own independent MapboxDraw — canales are untouched.
    setMeasurementState({ mode: 'idle', measurements: [] });
  };

  const cancel = () => {
    const draw = drawRef.current;
    if (draw) draw.changeMode('simple_select');
    setMeasurementCursor(false);
    setMeasurementState((prev) => ({ ...prev, mode: 'idle' }));
  };

  return { state, startDistance, startArea, clear, cancel };
}
