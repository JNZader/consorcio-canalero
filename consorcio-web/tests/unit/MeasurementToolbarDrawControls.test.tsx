/**
 * MeasurementToolbarDrawControls.test.tsx — T3c fix 4.
 *
 * MapboxDraw drops to `simple_select` after `draw.create`, so drawing a SECOND
 * polygon used to require toggling the whole ficha-draw mode off and on, and
 * deleting one was an undiscoverable Backspace. Two sub-controls now render
 * WHILE draw mode is active.
 */

import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { MeasurementToolbar } from '../../src/components/map2d/measurement/MeasurementToolbar';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

function baseProps(overrides: Record<string, unknown> = {}) {
  return {
    mode: 'idle' as const,
    hasMeasurements: false,
    onStartDistance: () => {},
    onStartArea: () => {},
    onClear: () => {},
    onToggleFichaDraw: () => {},
    ...overrides,
  };
}

describe('<MeasurementToolbar /> — draw sub-controls (T3c fix 4)', () => {
  it('hides both sub-controls while draw mode is off', () => {
    renderWithMantine(
      <MeasurementToolbar
        {...baseProps({
          fichaDrawActive: false,
          onRedrawPolygon: () => {},
          onDeletePolygon: () => {},
        })}
      />
    );

    expect(screen.queryByTestId('ficha-draw-new-polygon')).toBeNull();
    expect(screen.queryByTestId('ficha-draw-delete-polygon')).toBeNull();
  });

  it('renders both sub-controls while drawing', () => {
    renderWithMantine(
      <MeasurementToolbar
        {...baseProps({
          mode: 'ficha-dibujo',
          fichaDrawActive: true,
          onRedrawPolygon: () => {},
          onDeletePolygon: () => {},
        })}
      />
    );

    expect(screen.getByTestId('ficha-draw-new-polygon')).toBeInTheDocument();
    expect(screen.getByTestId('ficha-draw-delete-polygon')).toBeInTheDocument();
  });

  it('re-enters polygon drawing and deletes on click', () => {
    const onRedrawPolygon = vi.fn();
    const onDeletePolygon = vi.fn();
    renderWithMantine(
      <MeasurementToolbar
        {...baseProps({
          mode: 'ficha-dibujo',
          fichaDrawActive: true,
          onRedrawPolygon,
          onDeletePolygon,
        })}
      />
    );

    fireEvent.click(screen.getByTestId('ficha-draw-new-polygon'));
    expect(onRedrawPolygon).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByTestId('ficha-draw-delete-polygon'));
    expect(onDeletePolygon).toHaveBeenCalledTimes(1);
  });

  it('stays unchanged for callers that omit the handlers (3D viewer)', () => {
    renderWithMantine(
      <MeasurementToolbar {...baseProps({ mode: 'ficha-dibujo', fichaDrawActive: true })} />
    );

    expect(screen.queryByTestId('ficha-draw-new-polygon')).toBeNull();
    expect(screen.queryByTestId('ficha-draw-delete-polygon')).toBeNull();
  });
});
