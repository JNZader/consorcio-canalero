/**
 * Unit tests for MeasurementLabels collision handling.
 *
 * Covers:
 * - All labels render when zoom >= MIN_ZOOM_TO_SHOW_ALL
 * - Labels are filtered by collision when zoom < threshold
 * - Priority: areas first, then larger distances
 * - Re-render on map move/zoom events
 */

import { describe, expect, it, vi } from 'vitest';
import { act, render, screen } from '@testing-library/react';

import {
  MeasurementLabels,
  type MeasurementLabelsProps,
} from '@/components/map2d/measurement/MeasurementLabels';
import type { MeasurementEntry } from '@/components/map2d/measurement/useMeasurement';

function createMockMap(zoom = 12) {
  const listeners: Record<string, (() => void)[]> = {};

  return {
    project: vi.fn((lngLat: [number, number]) => {
      // Deterministic projection based on lng/lat so tests are stable
      return { x: (lngLat[0] + 180) * 100, y: (lngLat[1] + 90) * 100 };
    }),
    getZoom: vi.fn(() => zoom),
    on: vi.fn((event: string, handler: () => void) => {
      if (!listeners[event]) listeners[event] = [];
      listeners[event].push(handler);
    }),
    off: vi.fn((event: string, handler: () => void) => {
      if (listeners[event]) {
        listeners[event] = listeners[event].filter((h) => h !== handler);
      }
    }),
    _trigger(event: string) {
      (listeners[event] ?? []).forEach((h) => h());
    },
  };
}

function makeMeasurements(): MeasurementEntry[] {
  return [
    {
      id: 'dist-small',
      kind: 'distance',
      value: 100,
      labelPosition: [-62.68, -32.63],
    },
    {
      id: 'dist-large',
      kind: 'distance',
      value: 5000,
      labelPosition: [-62.681, -32.631], // very close to dist-small (< 40 px)
    },
    {
      id: 'area-medium',
      kind: 'area',
      value: 2000,
      labelPosition: [-62.682, -32.632], // also very close
    },
    {
      id: 'dist-far',
      kind: 'distance',
      value: 3000,
      labelPosition: [-62.0, -32.0], // far away
    },
  ];
}

describe('MeasurementLabels', () => {
  it('renders all labels when zoom is above threshold', () => {
    const map = createMockMap(15); // zoom >= 14
    const measurements = makeMeasurements();

    render(<MeasurementLabels map={map as unknown as NonNullable<MeasurementLabelsProps['map']>} measurements={measurements} />);

    expect(screen.getByTestId('measurement-label-dist-small')).toBeInTheDocument();
    expect(screen.getByTestId('measurement-label-dist-large')).toBeInTheDocument();
    expect(screen.getByTestId('measurement-label-area-medium')).toBeInTheDocument();
    expect(screen.getByTestId('measurement-label-dist-far')).toBeInTheDocument();
  });

  it('filters colliding labels when zoom is below threshold', () => {
    const map = createMockMap(12); // zoom < 14
    const measurements = makeMeasurements();

    render(<MeasurementLabels map={map as unknown as NonNullable<MeasurementLabelsProps['map']>} measurements={measurements} />);

    // area-medium has highest priority (area), so it should stay
    expect(screen.getByTestId('measurement-label-area-medium')).toBeInTheDocument();

    // dist-large is next (larger distance), but collides with area-medium (< 40 px)
    // so it should be hidden
    expect(screen.queryByTestId('measurement-label-dist-large')).not.toBeInTheDocument();

    // dist-small collides with area-medium too
    expect(screen.queryByTestId('measurement-label-dist-small')).not.toBeInTheDocument();

    // dist-far is far away, so it should be visible
    expect(screen.getByTestId('measurement-label-dist-far')).toBeInTheDocument();
  });

  it('shows larger distance before smaller one when both are far apart', () => {
    const measurements: MeasurementEntry[] = [
      {
        id: 'dist-small-far',
        kind: 'distance',
        value: 100,
        labelPosition: [-60.0, -30.0],
      },
      {
        id: 'dist-large-far',
        kind: 'distance',
        value: 5000,
        labelPosition: [-59.0, -29.0],
      },
    ];
    const map = createMockMap(12);

    render(<MeasurementLabels map={map as unknown as NonNullable<MeasurementLabelsProps['map']>} measurements={measurements} />);

    // Both are far apart (> 40 px in our mock projection)
    expect(screen.getByTestId('measurement-label-dist-large-far')).toBeInTheDocument();
    expect(screen.getByTestId('measurement-label-dist-small-far')).toBeInTheDocument();
  });

  it('re-renders when map zoom changes via zoom event', () => {
    const map = createMockMap(15);
    const measurements = makeMeasurements();

    render(<MeasurementLabels map={map as unknown as NonNullable<MeasurementLabelsProps['map']>} measurements={measurements} />);

    // All visible at zoom 15
    expect(screen.getByTestId('measurement-label-dist-small')).toBeInTheDocument();

    // Simulate zoom out
    map.getZoom.mockReturnValue(12);
    act(() => {
      map._trigger('zoom');
    });

    // After zoom out, dist-small should collide and disappear
    expect(screen.queryByTestId('measurement-label-dist-small')).not.toBeInTheDocument();
  });

  it('re-renders when map moves via move event', () => {
    const map = createMockMap(15);
    const measurements = makeMeasurements();

    render(<MeasurementLabels map={map as unknown as NonNullable<MeasurementLabelsProps['map']>} measurements={measurements} />);

    const el = screen.getByTestId('measurement-label-dist-small');
    expect(el).toBeInTheDocument();
    const originalLeft = (el as HTMLElement).style.left;

    // Change projection scale to simulate zoom/pan
    map.project.mockImplementation((lngLat: [number, number]) => {
      return { x: (lngLat[0] + 180) * 1000, y: (lngLat[1] + 90) * 1000 };
    });
    act(() => {
      map._trigger('move');
    });

    const updatedEl = screen.getByTestId('measurement-label-dist-small');
    expect(updatedEl).toBeInTheDocument();
    expect((updatedEl as HTMLElement).style.left).not.toBe(originalLeft);
  });

  it('returns null when map is null', () => {
    const { container } = render(<MeasurementLabels map={null} measurements={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('registers both move and zoom listeners', () => {
    const map = createMockMap(15);
    render(<MeasurementLabels map={map as unknown as NonNullable<MeasurementLabelsProps['map']>} measurements={[]} />);

    expect(map.on).toHaveBeenCalledWith('move', expect.any(Function));
    expect(map.on).toHaveBeenCalledWith('zoom', expect.any(Function));
  });

  it('unregisters listeners on unmount', () => {
    const map = createMockMap(15);
    const { unmount } = render(
      <MeasurementLabels map={map as unknown as NonNullable<MeasurementLabelsProps['map']>} measurements={[]} />
    );

    unmount();

    expect(map.off).toHaveBeenCalledWith('move', expect.any(Function));
    expect(map.off).toHaveBeenCalledWith('zoom', expect.any(Function));
  });
});
