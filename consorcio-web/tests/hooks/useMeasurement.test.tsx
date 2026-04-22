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
  };

  return { map, handlers };
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

  it('adds a draw control to the map on mount (dedicated instance)', () => {
    const { map } = createMapMock();
    // biome-ignore lint/suspicious/noExplicitAny: test-only coercion of mock map
    renderHook(() => useMeasurement(map as any));

    expect(drawInstances).toHaveLength(1);
    expect(map.addControl).toHaveBeenCalledTimes(1);
  });

  it('startDistance() switches draw into draw_line_string and mode into measuring-distance', () => {
    const { map } = createMapMock();
    // biome-ignore lint/suspicious/noExplicitAny: test-only coercion of mock map
    const { result } = renderHook(() => useMeasurement(map as any));

    act(() => result.current.startDistance());

    expect(drawChangeMode).toHaveBeenCalledWith('draw_line_string');
    expect(result.current.state.mode).toBe('measuring-distance');
  });

  it('startArea() switches draw into draw_polygon and mode into measuring-area', () => {
    const { map } = createMapMock();
    // biome-ignore lint/suspicious/noExplicitAny: test-only coercion of mock map
    const { result } = renderHook(() => useMeasurement(map as any));

    act(() => result.current.startArea());

    expect(drawChangeMode).toHaveBeenCalledWith('draw_polygon');
    expect(result.current.state.mode).toBe('measuring-area');
  });

  it('records a distance entry with midpoint anchor on draw.create with a LineString feature', () => {
    const { map, handlers } = createMapMock();
    // biome-ignore lint/suspicious/noExplicitAny: test-only coercion of mock map
    const { result } = renderHook(() => useMeasurement(map as any));

    act(() => result.current.startDistance());

    const createHandler = handlers.get('draw.create')?.[0];
    expect(createHandler).toBeTruthy();

    act(() => createHandler?.({ features: [buildLineFeature()] }));

    expect(result.current.state.measurements).toHaveLength(1);
    const [entry] = result.current.state.measurements;
    expect(entry.kind).toBe('distance');
    expect(entry.value).toBe(123.4);
    expect(entry.labelPosition).toEqual([-62.5, -32.5]); // from @turf/midpoint mock
    expect(result.current.state.mode).toBe('idle');
  });

  it('records an area entry with center-of-mass anchor on draw.create with a Polygon feature', () => {
    const { map, handlers } = createMapMock();
    // biome-ignore lint/suspicious/noExplicitAny: test-only coercion of mock map
    const { result } = renderHook(() => useMeasurement(map as any));

    act(() => result.current.startArea());

    const createHandler = handlers.get('draw.create')?.[0];
    expect(createHandler).toBeTruthy();

    act(() => createHandler?.({ features: [buildPolygonFeature()] }));

    expect(result.current.state.measurements).toHaveLength(1);
    const [entry] = result.current.state.measurements;
    expect(entry.kind).toBe('area');
    expect(entry.value).toBe(4567.8);
    expect(entry.labelPosition).toEqual([-62.6, -32.6]); // from @turf/center-of-mass mock
    expect(result.current.state.mode).toBe('idle');
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

  it('clear() calls draw.deleteAll and empties the measurements list', () => {
    const { map, handlers } = createMapMock();
    // biome-ignore lint/suspicious/noExplicitAny: test-only coercion of mock map
    const { result } = renderHook(() => useMeasurement(map as any));

    act(() => result.current.startDistance());
    const createHandler = handlers.get('draw.create')?.[0];
    act(() => createHandler?.({ features: [buildLineFeature()] }));
    expect(result.current.state.measurements).toHaveLength(1);

    drawDeleteAll.mockClear();
    act(() => result.current.clear());

    expect(drawDeleteAll).toHaveBeenCalledTimes(1);
    expect(result.current.state.measurements).toEqual([]);
  });

  it('cancel() exits draw mode into simple_select WITHOUT appending a measurement', () => {
    const { map } = createMapMock();
    // biome-ignore lint/suspicious/noExplicitAny: test-only coercion of mock map
    const { result } = renderHook(() => useMeasurement(map as any));

    act(() => result.current.startDistance());
    expect(result.current.state.mode).toBe('measuring-distance');

    drawChangeMode.mockClear();
    act(() => result.current.cancel());

    expect(drawChangeMode).toHaveBeenCalledWith('simple_select');
    expect(result.current.state.mode).toBe('idle');
    expect(result.current.state.measurements).toEqual([]);
  });

  it('removes the draw control on unmount and cleans up event listeners', () => {
    const { map, handlers } = createMapMock();
    // biome-ignore lint/suspicious/noExplicitAny: test-only coercion of mock map
    const { unmount } = renderHook(() => useMeasurement(map as any));

    expect(handlers.get('draw.create')?.length ?? 0).toBeGreaterThan(0);

    unmount();

    expect(map.removeControl).toHaveBeenCalledTimes(1);
    // draw.create listener should be detached
    expect(handlers.get('draw.create')?.length ?? 0).toBe(0);
  });
});
