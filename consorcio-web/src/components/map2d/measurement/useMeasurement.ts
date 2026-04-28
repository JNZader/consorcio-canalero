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
import distance from '@turf/distance';
import length from '@turf/length';
import midpoint from '@turf/midpoint';

import { useMapboxDrawSlot } from '../../../stores/mapboxDrawSlot';
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
  /**
   * Persisted geometry of the shape the user drew. Stored on the entry so
   * `<MeasurementShapes>` can render the line/polygon as a plain MapLibre
   * layer that survives the unmount of the temporary MapboxDraw instance
   * (which otherwise wipes its features when we release the slot mutex).
   */
  geometry: LineString | Polygon;
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

export function computeLineLabelAnchor(line: Feature<LineString>): [number, number] {
  const coords = line.geometry.coordinates;
  if (coords.length === 0) return [0, 0];
  if (coords.length === 1) {
    const [lng, lat] = coords[0];
    return [lng, lat];
  }

  if (coords.length === 2) {
    const firstPt: Feature<Point> = {
      type: 'Feature',
      geometry: { type: 'Point', coordinates: coords[0] },
      properties: {},
    };
    const lastPt: Feature<Point> = {
      type: 'Feature',
      geometry: { type: 'Point', coordinates: coords[1] },
      properties: {},
    };
    const mid = midpoint(firstPt, lastPt);
    const [lng, lat] = mid.geometry.coordinates;
    return [lng, lat];
  }

  const totalLength = length(line, { units: 'meters' });
  const target = totalLength / 2;
  let accumulated = 0;

  for (let i = 0; i < coords.length - 1; i++) {
    const from = coords[i];
    const to = coords[i + 1];
    const segmentLength = distance(from, to, { units: 'meters' });

    if (accumulated + segmentLength >= target) {
      const ratio = segmentLength === 0 ? 0 : (target - accumulated) / segmentLength;
      const lng = from[0] + (to[0] - from[0]) * ratio;
      const lat = from[1] + (to[1] - from[1]) * ratio;
      return [lng, lat];
    }

    accumulated += segmentLength;
  }

  // Fallback for floating-point drift: return last coordinate
  const last = coords[coords.length - 1];
  return [last[0], last[1]];
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

  // Refs holding the listeners so `mountDraw` can register them once and
  // `unmountDraw` can off them by reference.
  const handleCreateRef = useRef<((event: unknown) => void) | null>(null);
  const handleContextLostRef = useRef<(() => void) | null>(null);

  // ── Lazy mount/unmount of the MapboxDraw control ─────────────────────
  //
  // We INTENTIONALLY do NOT mount MapboxDraw on the hook's mount. The bug
  // we fix (`Source "mapbox-gl-draw-cold" already exists`) happens because
  // both `LineDrawControl` and this hook used to call `addControl(new
  // MapboxDraw)` on the SAME map, and MapboxDraw hard-codes its source IDs.
  //
  // Now we mount MapboxDraw only when the user enters a measuring mode,
  // and acquire the global `mapboxDrawSlot` so `LineDrawControl` knows to
  // unmount itself first. On `clear()` / `cancel()` we tear it down and
  // release the slot, letting `LineDrawControl` re-mount.
  const mountDraw = useCallback((): MapboxDraw | null => {
    if (!map) return null;
    if (drawRef.current) return drawRef.current;

    useMapboxDrawSlot.getState().acquire('measurement');

    const draw = createMeasurementDraw();
    drawRef.current = draw;

    // Defensive: clean any leftover gl-draw-* layers/sources from a prior
    // owner before we add ours. Idempotent.
    removeMapboxDrawArtifacts(map);

    map.addControl(draw as unknown as maplibregl.IControl);

    const handleCreate = handleCreateRef.current;
    const handleContextLost = handleContextLostRef.current;
    if (handleCreate) map.on('draw.create', handleCreate);
    if (handleContextLost) map.on('webglcontextlost', handleContextLost);

    return draw;
  }, [map]);

  const unmountDraw = useCallback(() => {
    if (!map) return;
    const draw = drawRef.current;

    const handleCreate = handleCreateRef.current;
    const handleContextLost = handleContextLostRef.current;
    if (handleCreate) map.off('draw.create', handleCreate);
    if (handleContextLost) map.off('webglcontextlost', handleContextLost);

    if (draw) {
      try {
        removeMapboxDrawArtifacts(map);
        const control = draw as unknown as maplibregl.IControl;
        if (map.hasControl(control)) {
          map.removeControl(control);
        }
      } catch {
        // ignore — removal can race with map teardown
      }
      removeMapboxDrawArtifacts(map);
    }

    drawRef.current = null;
    setMeasurementCursor(false);
    useMapboxDrawSlot.getState().release('measurement');
  }, [map, setMeasurementCursor]);

  // The handlers don't depend on any reactive state — they read mode via
  // `modeRef` and only ever push entries via the stable `setMeasurementState`.
  // We register them once in stable refs so `mountDraw` / `unmountDraw` can
  // attach/detach them without re-running this effect.
  useEffect(() => {
    handleCreateRef.current = (event: unknown) => {
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
          entries.push({
            id: featureId,
            kind: 'distance',
            value: meters,
            labelPosition,
            geometry: line.geometry,
          });
        } else if (geom.type === 'Polygon') {
          const poly = feature as Feature<Polygon>;
          const m2 = area(poly);
          const labelPosition = computePolygonLabelAnchor(poly);
          entries.push({
            id: featureId,
            kind: 'area',
            value: m2,
            labelPosition,
            geometry: poly.geometry,
          });
        }
      }

      if (entries.length === 0) return;

      // After each successful measurement, return to 'idle'. The user has to
      // click "Medir distancia / área" again to start another shape. Two
      // wins from this:
      //   1. UX: the double-click that ends a shape stops on the last vertex
      //      instead of starting a phantom new line from that same point.
      //   2. Stability: we no longer call `draw.changeMode(...)` from inside
      //      MapboxDraw's `draw.create` handler. That reentrancy fired
      //      MapboxDraw's `onStop` recursively and produced
      //      "InternalError: too much recursion" in production.
      // The unmount of the MapboxDraw control is handled by the
      // `state.mode === 'idle'` reactive effect below — doing it here would
      // re-enter the very event loop we are currently inside.
      setMeasurementState((prev) => ({
        mode: 'idle',
        measurements: [...prev.measurements, ...entries],
      }));
    };

    handleContextLostRef.current = () => {
      if (map) removeMapboxDrawArtifacts(map);
    };
  }, [map, setMeasurementState]);

  // Reactive teardown: whenever the mode flips back to 'idle' (because a
  // measurement just completed inside `handleCreate`, or because the user
  // pressed `clear/cancel`), drop the MapboxDraw control + release the
  // mutex slot so LineDrawControl can re-mount.
  //
  // We do this in an effect (not directly in `handleCreate`) so the unmount
  // runs OUTSIDE of MapboxDraw's `draw.create` event loop — calling
  // `removeControl` from inside an event fired by MapboxDraw was the source
  // of the "too much recursion" crash.
  useEffect(() => {
    if (state.mode === 'idle' && drawRef.current) {
      unmountDraw();
    }
  }, [state.mode, unmountDraw]);

  // Tear down on full unmount: release the slot so LineDrawControl can
  // re-mount.
  useEffect(() => {
    return () => {
      unmountDraw();
    };
  }, [unmountDraw]);

  const startDistance = () => {
    const draw = mountDraw();
    if (draw) draw.changeMode('draw_line_string');
    setMeasurementCursor(true);
    setMeasurementState((prev) => ({ ...prev, mode: 'measuring-distance' }));
  };

  const startArea = () => {
    const draw = mountDraw();
    if (draw) draw.changeMode('draw_polygon');
    setMeasurementCursor(true);
    setMeasurementState((prev) => ({ ...prev, mode: 'measuring-area' }));
  };

  const clear = () => {
    // Tearing down the draw releases the slot and removes its layers/sources
    // — LineDrawControl will re-mount and restore its features from props.
    unmountDraw();
    setMeasurementState({ mode: 'idle', measurements: [] });
  };

  const cancel = () => {
    // Same reasoning as `clear`: drop the draw + release the slot. The user
    // cancelled before saving, so there's nothing to preserve.
    unmountDraw();
    setMeasurementState((prev) => ({ ...prev, mode: 'idle' }));
  };

  return { state, startDistance, startArea, clear, cancel };
}
