/**
 * MeasurementLabels — HTML overlay that renders a floating label per
 * measurement entry at its `labelPosition`. Labels re-project on every
 * map `move` event using `map.project(lngLat)`.
 *
 * Why HTML (not a MapLibre symbol layer): the 2D base style has NO
 * `glyphs` URL, so any layer with `text-field` crashes the GL renderer
 * (same constraint that bit us during escuelas-rurales). HTML `<div>` +
 * `map.project` is the stable fallback.
 *
 * Contract pinned by these tests:
 * - Renders `null` when `map` is null (no overlay DOM at all).
 * - Renders 0 labels when `measurements === []`.
 * - Renders N labels for N measurements, each formatted via
 *   `formatDistance`/`formatArea`.
 * - Computes initial pixel positions from `map.project(labelPosition)`.
 * - Subscribes to `map.on('move', ...)` on mount, unsubscribes on unmount.
 * - Re-computes positions when `measurements` changes.
 */

import { act, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { MeasurementLabels } from '@/components/map2d/measurement/MeasurementLabels';
import type { MeasurementEntry } from '@/components/map2d/measurement/useMeasurement';

type Handler = (payload?: unknown) => void;

interface MapMock {
  map: {
    on: ReturnType<typeof vi.fn>;
    off: ReturnType<typeof vi.fn>;
    project: ReturnType<typeof vi.fn>;
  };
  handlers: Map<string, Handler[]>;
  emit: (event: string) => void;
}

function createMapMock(): MapMock {
  const handlers = new Map<string, Handler[]>();

  const on = vi.fn((event: string, handler: Handler) => {
    const existing = handlers.get(event) ?? [];
    handlers.set(event, [...existing, handler]);
  });

  const off = vi.fn((event: string, handler: Handler) => {
    handlers.set(
      event,
      (handlers.get(event) ?? []).filter((h) => h !== handler),
    );
  });

  // Deterministic projection: lng * 10, lat * -10, shifted to avoid negatives.
  const project = vi.fn((lngLat: [number, number] | { lng: number; lat: number }) => {
    const lng = Array.isArray(lngLat) ? lngLat[0] : lngLat.lng;
    const lat = Array.isArray(lngLat) ? lngLat[1] : lngLat.lat;
    return { x: lng * 10 + 1000, y: lat * -10 + 1000 };
  });

  const map = { on, off, project };

  return {
    map,
    handlers,
    emit(event: string) {
      for (const h of handlers.get(event) ?? []) h();
    },
  };
}

function buildDistance(id: string, meters: number, pos: [number, number]): MeasurementEntry {
  return { id, kind: 'distance', value: meters, labelPosition: pos };
}

function buildArea(id: string, m2: number, pos: [number, number]): MeasurementEntry {
  return { id, kind: 'area', value: m2, labelPosition: pos };
}

describe('<MeasurementLabels />', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when map is null', () => {
    const { container } = render(
      <MeasurementLabels map={null} measurements={[]} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders 0 labels when measurements is empty', () => {
    const { map } = createMapMock();
    const { container } = render(
      <MeasurementLabels
        map={map as unknown as maplibregl.Map}
        measurements={[]}
      />,
    );
    // Outer overlay is present but has no children.
    const overlay = container.firstElementChild;
    expect(overlay).not.toBeNull();
    expect(overlay?.children.length).toBe(0);
  });

  it('renders one label per measurement with the correct formatted text', () => {
    const { map } = createMapMock();
    const measurements: MeasurementEntry[] = [
      buildDistance('m1', 1500, [-62.5, -32.5]), // "1.5 km"
      buildArea('m2', 50_000, [-62.6, -32.6]), // "5.0 ha"
      buildDistance('m3', 250, [-62.7, -32.7]), // "250 m"
    ];

    render(
      <MeasurementLabels
        map={map as unknown as maplibregl.Map}
        measurements={measurements}
      />,
    );

    expect(screen.getByText('1.5 km')).toBeInTheDocument();
    expect(screen.getByText('5.0 ha')).toBeInTheDocument();
    expect(screen.getByText('250 m')).toBeInTheDocument();
  });

  it('uses map.project(labelPosition) to compute pixel coords for each label', () => {
    const mock = createMapMock();
    const measurements: MeasurementEntry[] = [
      buildDistance('m1', 1500, [-62.5, -32.5]),
      buildArea('m2', 50_000, [-62.6, -32.6]),
    ];

    render(
      <MeasurementLabels
        map={mock.map as unknown as maplibregl.Map}
        measurements={measurements}
      />,
    );

    expect(mock.map.project).toHaveBeenCalledWith([-62.5, -32.5]);
    expect(mock.map.project).toHaveBeenCalledWith([-62.6, -32.6]);
  });

  it('subscribes to map.on("move", ...) on mount', () => {
    const mock = createMapMock();
    render(
      <MeasurementLabels
        map={mock.map as unknown as maplibregl.Map}
        measurements={[buildDistance('m1', 1500, [-62.5, -32.5])]}
      />,
    );

    expect(mock.map.on).toHaveBeenCalledWith('move', expect.any(Function));
  });

  it('unsubscribes from "move" on unmount', () => {
    const mock = createMapMock();
    const { unmount } = render(
      <MeasurementLabels
        map={mock.map as unknown as maplibregl.Map}
        measurements={[buildDistance('m1', 1500, [-62.5, -32.5])]}
      />,
    );

    const registered = mock.map.on.mock.calls.find((c) => c[0] === 'move');
    expect(registered).toBeDefined();
    const registeredHandler = registered?.[1];

    unmount();

    expect(mock.map.off).toHaveBeenCalledWith('move', registeredHandler);
  });

  it('re-computes positions when a new measurement is appended', () => {
    const mock = createMapMock();
    const initial: MeasurementEntry[] = [
      buildDistance('m1', 1500, [-62.5, -32.5]),
    ];

    const { rerender } = render(
      <MeasurementLabels
        map={mock.map as unknown as maplibregl.Map}
        measurements={initial}
      />,
    );

    const callsBefore = mock.map.project.mock.calls.length;

    const next: MeasurementEntry[] = [
      ...initial,
      buildArea('m2', 50_000, [-62.9, -32.9]),
    ];

    rerender(
      <MeasurementLabels
        map={mock.map as unknown as maplibregl.Map}
        measurements={next}
      />,
    );

    expect(mock.map.project.mock.calls.length).toBeGreaterThan(callsBefore);
    // The new label position must have been projected.
    expect(mock.map.project).toHaveBeenCalledWith([-62.9, -32.9]);
    // And the new label is visible in the DOM.
    expect(screen.getByText('5.0 ha')).toBeInTheDocument();
  });

  it('re-computes positions when the map fires a "move" event', () => {
    const mock = createMapMock();
    const measurements: MeasurementEntry[] = [
      buildDistance('m1', 1500, [-62.5, -32.5]),
    ];

    render(
      <MeasurementLabels
        map={mock.map as unknown as maplibregl.Map}
        measurements={measurements}
      />,
    );

    const callsBefore = mock.map.project.mock.calls.length;

    // Simulate a map pan — the registered handler should re-run projections.
    act(() => {
      mock.emit('move');
    });

    expect(mock.map.project.mock.calls.length).toBeGreaterThan(callsBefore);
  });
});
