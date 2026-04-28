/**
 * useMeasurement — hook tests.
 *
 * The hook owns a DEDICATED `@mapbox/mapbox-gl-draw` instance (separate
 * from `LineDrawControl`'s) and translates user actions into:
 *  - mode transitions (idle / measuring-distance / measuring-area)
 *  - computed measurement values (meters / m²) + label anchor positions
 *  - an array of persisted `MeasurementEntry` rows
 *
 * jsdom/happy-dom can't create a WebGL context, so we cannot instantiate
 * the real `MapboxDraw`. We mock it with a fake that captures `new` args,
 * exposes `changeMode` / `deleteAll` as spies, and lets the test trigger
 * `draw.create` events via the mock `map.on` registry.
 */

import { act, renderHook } from '@testing-library/react';
import type { Feature, LineString, Polygon } from 'geojson';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// ─── @mapbox/mapbox-gl-draw mock ────────────────────────────────────────
// We expose shared spies so each test can reset / assert against them.

const drawChangeMode = vi.fn();
const drawDeleteAll = vi.fn();
const drawInstances: Array<{
  changeMode: typeof drawChangeMode;
  deleteAll: typeof drawDeleteAll;
}> = [];

vi.mock('@mapbox/mapbox-gl-draw', () => {
  class MapboxDrawMock {
    changeMode = drawChangeMode;
    deleteAll = drawDeleteAll;
    constructor() {
      drawInstances.push(this);
    }
  }
  return { default: MapboxDrawMock };
});

// ─── @turf/* mocks ──────────────────────────────────────────────────────
// Deterministic stubs so we can assert the hook's wiring without
// simulating real spherical geometry.

vi.mock('@turf/length', () => ({
  default: vi.fn(() => 123.4), // meters
}));

vi.mock('@turf/area', () => ({
  default: vi.fn(() => 4567.8), // square meters
}));

vi.mock('@turf/midpoint', () => ({
  default: vi.fn(() => ({
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [-62.5, -32.5] },
    properties: {},
  })),
}));

vi.mock('@turf/center-of-mass', () => ({
  default: vi.fn(() => ({
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [-62.6, -32.6] },
    properties: {},
  })),
}));

// Import the hook AFTER all mocks.
import { useMeasurement } from '@/components/map2d/measurement/useMeasurement';

// ─── Helpers ────────────────────────────────────────────────────────────

function createMapMock() {
  const handlers = new Map<string, Array<(payload: unknown) => void>>();
  const canvas = { style: { cursor: '' } };

  const map = {
    on: vi.fn((event: string, handler: (payload: unknown) => void) => {
      const existing = handlers.get(event) ?? [];
      handlers.set(event, [...existing, handler]);
    }),
    off: vi.fn((event: string, handler: (payload: unknown) => void) => {
      handlers.set(
        event,
        (handlers.get(event) ?? []).filter((c) => c !== handler),
      );
    }),
    addControl: vi.fn(),
    removeControl: vi.fn(),
    hasControl: vi.fn(() => true),
    getStyle: vi.fn(() => ({ layers: [], sources: {} })),
    getSource: vi.fn(() => null),
    removeSource: vi.fn(),
    removeLayer: vi.fn(),
    getCanvas: vi.fn(() => canvas),
  };

  return { map, handlers, canvas };
}

function buildLineFeature(): Feature<LineString> {
  return {
    type: 'Feature',
    id: 'line-1',
    geometry: {
      type: 'LineString',
      coordinates: [
        [-62.5, -32.5],
        [-62.4, -32.4],
        [-62.3, -32.3],
      ],
    },
    properties: {},
  };
}

function buildPolygonFeature(): Feature<Polygon> {
  return {
    type: 'Feature',
    id: 'poly-1',
    geometry: {
      type: 'Polygon',
      coordinates: [
        [
          [-62.5, -32.5],
          [-62.4, -32.5],
          [-62.4, -32.4],
          [-62.5, -32.4],
          [-62.5, -32.5],
        ],
      ],
    },
    properties: {},
  };
}

// ─── Tests ──────────────────────────────────────────────────────────────

describe('useMeasurement', () => {
  beforeEach(() => {
    drawChangeMode.mockClear();
    drawDeleteAll.mockClear();
    drawInstances.length = 0;
  });

  it('starts in the idle state with no measurements', () => {
    const { map } = createMapMock();
    // biome-ignore lint/suspicious/noExplicitAny: test-only coercion of mock map
    const { result } = renderHook(() => useMeasurement(map as any));

    expect(result.current.state.mode).toBe('idle');
    expect(result.current.state.measurements).toEqual([]);
  });

  it('does not create a draw instance when map is null', () => {
    renderHook(() => useMeasurement(null));
    expect(drawInstances).toHaveLength(0);
  });

  it('does NOT create a draw instance on mount — only on startDistance/startArea (lazy)', () => {
    const { map } = createMapMock();
    // biome-ignore lint/suspicious/noExplicitAny: test-only coercion of mock map
    const { result } = renderHook(() => useMeasurement(map as any));

    // Hook mounted but no MapboxDraw yet: this avoids colliding with
    // LineDrawControl's MapboxDraw on the SAME map (both use the hardcoded
    // `mapbox-gl-draw-cold/hot` source ids).
    expect(drawInstances).toHaveLength(0);
    expect(map.addControl).not.toHaveBeenCalled();

    act(() => result.current.startDistance());

    expect(drawInstances).toHaveLength(1);
    expect(map.addControl).toHaveBeenCalledTimes(1);
  });

  it('startDistance() switches draw into draw_line_string and mode into measuring-distance', () => {
    const { map, canvas } = createMapMock();
    // biome-ignore lint/suspicious/noExplicitAny: test-only coercion of mock map
    const { result } = renderHook(() => useMeasurement(map as any));

    act(() => result.current.startDistance());

    expect(drawChangeMode).toHaveBeenCalledWith('draw_line_string');
    expect(result.current.state.mode).toBe('measuring-distance');
    expect(canvas.style.cursor).toBe('crosshair');
  });

  it('startArea() switches draw into draw_polygon and mode into measuring-area', () => {
    const { map, canvas } = createMapMock();
    // biome-ignore lint/suspicious/noExplicitAny: test-only coercion of mock map
    const { result } = renderHook(() => useMeasurement(map as any));

    act(() => result.current.startArea());

    expect(drawChangeMode).toHaveBeenCalledWith('draw_polygon');
    expect(result.current.state.mode).toBe('measuring-area');
    expect(canvas.style.cursor).toBe('crosshair');
  });

  it('records a distance entry and returns to idle (no auto-restart of next shape)', () => {
    const { map, handlers } = createMapMock();
    // biome-ignore lint/suspicious/noExplicitAny: test-only coercion of mock map
    const { result } = renderHook(() => useMeasurement(map as any));

    act(() => result.current.startDistance());

    const createHandler = handlers.get('draw.create')?.[0];
    expect(createHandler).toBeTruthy();

    drawChangeMode.mockClear();
    act(() => createHandler?.({ features: [buildLineFeature()] }));

    expect(result.current.state.measurements).toHaveLength(1);
    const [entry] = result.current.state.measurements;
    expect(entry.kind).toBe('distance');
    expect(entry.value).toBe(123.4);
    // labelPosition path for 3+ vertices uses real turf/distance walk-along
    // (NOT @turf/midpoint), so we assert the shape and rough range, not the
    // exact (-62.5, -32.5) — that mock only fires for 2-vertex lines.
    expect(entry.labelPosition).toHaveLength(2);
    expect(entry.labelPosition[0]).toBeGreaterThan(-63);
    expect(entry.labelPosition[0]).toBeLessThan(-62);
    expect(entry.labelPosition[1]).toBeGreaterThan(-33);
    expect(entry.labelPosition[1]).toBeLessThan(-32);
    // Critical: after the shape is finished we go back to idle so the
    // double-click that ended the line does NOT start a phantom new line.
    expect(result.current.state.mode).toBe('idle');
    // And we do NOT reentrantly call changeMode from inside draw.create —
    // that reentrancy was the source of the "too much recursion" prod crash.
    expect(drawChangeMode).not.toHaveBeenCalled();
  });

  it('records an area entry and returns to idle (no auto-restart of next shape)', () => {
    const { map, handlers } = createMapMock();
    // biome-ignore lint/suspicious/noExplicitAny: test-only coercion of mock map
    const { result } = renderHook(() => useMeasurement(map as any));

    act(() => result.current.startArea());

    const createHandler = handlers.get('draw.create')?.[0];
    expect(createHandler).toBeTruthy();

    drawChangeMode.mockClear();
    act(() => createHandler?.({ features: [buildPolygonFeature()] }));

    expect(result.current.state.measurements).toHaveLength(1);
    const [entry] = result.current.state.measurements;
    expect(entry.kind).toBe('area');
    expect(entry.value).toBe(4567.8);
    expect(entry.labelPosition).toEqual([-62.6, -32.6]); // from @turf/center-of-mass mock
    // Same rule as distance — after a polygon completes, return to idle.
    expect(result.current.state.mode).toBe('idle');
    expect(drawChangeMode).not.toHaveBeenCalled();
  });

  it('assigns stable ids from the draw feature id (no randomness in the pipeline)', () => {
    const { map, handlers } = createMapMock();
    // biome-ignore lint/suspicious/noExplicitAny: test-only coercion of mock map
    const { result } = renderHook(() => useMeasurement(map as any));

    act(() => result.current.startDistance());
    const createHandler = handlers.get('draw.create')?.[0];
    act(() => createHandler?.({ features: [buildLineFeature()] }));

    expect(result.current.state.measurements[0].id).toBe('line-1');
  });

  it('clear() empties the measurements list and ensures the slot is released', () => {
    const { map, handlers, canvas } = createMapMock();
    // biome-ignore lint/suspicious/noExplicitAny: test-only coercion of mock map
    const { result } = renderHook(() => useMeasurement(map as any));

    act(() => result.current.startDistance());
    const createHandler = handlers.get('draw.create')?.[0];
    act(() => createHandler?.({ features: [buildLineFeature()] }));
    expect(result.current.state.measurements).toHaveLength(1);

    // Completing the shape already returned us to idle, which auto-unmounts
    // the draw via the reactive effect — `removeControl` was called there.
    expect(map.removeControl).toHaveBeenCalledTimes(1);
    // listeners were detached as part of the auto-unmount
    expect(handlers.get('draw.create')?.length ?? 0).toBe(0);

    act(() => result.current.clear());

    // `clear()` only resets state; the draw was already gone, so no extra
    // removeControl call.
    expect(map.removeControl).toHaveBeenCalledTimes(1);
    expect(result.current.state.measurements).toEqual([]);
    expect(result.current.state.mode).toBe('idle');
    expect(canvas.style.cursor).toBe('');
  });

  it('clear() while still drawing tears the draw down explicitly', () => {
    const { map, canvas } = createMapMock();
    // biome-ignore lint/suspicious/noExplicitAny: test-only coercion of mock map
    const { result } = renderHook(() => useMeasurement(map as any));

    // Start a measurement but DO NOT complete it — draw is mounted, no entry yet.
    act(() => result.current.startDistance());
    expect(result.current.state.measurements).toEqual([]);
    expect(map.addControl).toHaveBeenCalledTimes(1);

    map.removeControl.mockClear();
    act(() => result.current.clear());

    // `clear()` MUST tear down the in-flight draw + release the slot.
    expect(map.removeControl).toHaveBeenCalledTimes(1);
    expect(result.current.state.mode).toBe('idle');
    expect(canvas.style.cursor).toBe('');
  });

  it('cancel() tears the draw down WITHOUT appending a measurement', () => {
    const { map, canvas } = createMapMock();
    // biome-ignore lint/suspicious/noExplicitAny: test-only coercion of mock map
    const { result } = renderHook(() => useMeasurement(map as any));

    act(() => result.current.startDistance());
    expect(result.current.state.mode).toBe('measuring-distance');

    map.removeControl.mockClear();
    act(() => result.current.cancel());

    // No leftover MapboxDraw — same path as `clear()` minus the state reset.
    expect(map.removeControl).toHaveBeenCalledTimes(1);
    expect(result.current.state.mode).toBe('idle');
    expect(result.current.state.measurements).toEqual([]);
    expect(canvas.style.cursor).toBe('');
  });

  it('removes the draw control on unmount and cleans up event listeners', () => {
    const { map, handlers } = createMapMock();
    // biome-ignore lint/suspicious/noExplicitAny: test-only coercion of mock map
    const { result, unmount } = renderHook(() => useMeasurement(map as any));

    // Lazy mount: trigger startDistance so the draw + listeners actually exist
    act(() => result.current.startDistance());
    expect(handlers.get('draw.create')?.length ?? 0).toBeGreaterThan(0);

    unmount();

    expect(map.removeControl).toHaveBeenCalledTimes(1);
    // draw.create listener should be detached
    expect(handlers.get('draw.create')?.length ?? 0).toBe(0);
  });
});
