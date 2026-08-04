/**
 * useFichaDrawWiring.test.ts
 *
 * The container half of T4. `MapaMapLibre` is not mountable in jsdom (router +
 * react-query + WebGL + a dozen data hooks), so the two decisions it used to
 * inline live in this hook instead — and are asserted here:
 *
 *  1. Escape keeps working for the WHOLE draw session, not only while tracing.
 *     After `draw.create` the real mode is `idle`, yet the control is still
 *     mounted with a polygon on screen; passing the raw mode made Escape a
 *     silent no-op exactly there.
 *  2. "Otro" goes through STATE (`redrawPolygon`) and lets the kick-off effect
 *     drive MapboxDraw. Calling the imperative handle directly would have left
 *     React thinking the map was click-selectable while MapboxDraw traced.
 */

import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { DrawControlHandle } from '../../src/components/map/DrawControl';
import { useFichaDrawWiring } from '../../src/components/map2d/useFichaDrawWiring';
import type { MapInteractionMode } from '../../src/components/map2d/measurement/useMeasurement';

function makeHandle() {
  return {
    current: {
      startDrawing: vi.fn(),
      clearDrawing: vi.fn(),
    } satisfies DrawControlHandle,
  };
}

interface Props {
  interactionMode: MapInteractionMode;
  drawSession: boolean;
}

describe('useFichaDrawWiring — escape mode', () => {
  let redrawPolygon: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    redrawPolygon = vi.fn();
  });

  it('synthesises ficha-dibujo for the whole session, even once tracing ended', () => {
    const drawControlRef = makeHandle();
    const { result } = renderHook(
      ({ interactionMode, drawSession }: Props) =>
        useFichaDrawWiring({ interactionMode, drawSession, redrawPolygon, drawControlRef }),
      // The exact post-`draw.create` state: session open, mode back to idle.
      { initialProps: { interactionMode: 'idle' as MapInteractionMode, drawSession: true } },
    );

    expect(result.current.escapeMode).toBe('ficha-dibujo');
    expect(result.current.isTracing).toBe(false);
    expect(result.current.isDrawSession).toBe(true);
  });

  it('passes the real mode through when there is no draw session', () => {
    const drawControlRef = makeHandle();
    const { result, rerender } = renderHook(
      ({ interactionMode, drawSession }: Props) =>
        useFichaDrawWiring({ interactionMode, drawSession, redrawPolygon, drawControlRef }),
      { initialProps: { interactionMode: 'idle' as MapInteractionMode, drawSession: false } },
    );

    expect(result.current.escapeMode).toBe('idle');

    // A measurement must NOT be masked as a draw session.
    rerender({ interactionMode: 'measuring-distance' as MapInteractionMode, drawSession: false });
    expect(result.current.escapeMode).toBe('measuring-distance');

    rerender({ interactionMode: 'ficha-canal' as MapInteractionMode, drawSession: false });
    expect(result.current.escapeMode).toBe('ficha-canal');
  });
});

describe('useFichaDrawWiring — draw control kick-off', () => {
  it('starts MapboxDraw when tracing begins, and only then', () => {
    const drawControlRef = makeHandle();
    const redrawPolygon = vi.fn();
    const { rerender } = renderHook(
      ({ interactionMode, drawSession }: Props) =>
        useFichaDrawWiring({ interactionMode, drawSession, redrawPolygon, drawControlRef }),
      { initialProps: { interactionMode: 'idle' as MapInteractionMode, drawSession: false } },
    );

    expect(drawControlRef.current.startDrawing).not.toHaveBeenCalled();

    rerender({ interactionMode: 'ficha-dibujo' as MapInteractionMode, drawSession: true });
    expect(drawControlRef.current.startDrawing).toHaveBeenCalledTimes(1);

    // `draw.create`: tracing ends, session stays. No new startDrawing.
    rerender({ interactionMode: 'idle' as MapInteractionMode, drawSession: true });
    expect(drawControlRef.current.startDrawing).toHaveBeenCalledTimes(1);
  });

  it('"Otro" only touches STATE — the imperative handle is driven by the effect', () => {
    const drawControlRef = makeHandle();
    const redrawPolygon = vi.fn();
    const { result, rerender } = renderHook(
      ({ interactionMode, drawSession }: Props) =>
        useFichaDrawWiring({ interactionMode, drawSession, redrawPolygon, drawControlRef }),
      { initialProps: { interactionMode: 'idle' as MapInteractionMode, drawSession: true } },
    );

    result.current.handleRedrawPolygon();

    expect(redrawPolygon).toHaveBeenCalledTimes(1);
    // Crucially NOT called yet: the state flip has not happened in this fake.
    expect(drawControlRef.current.startDrawing).not.toHaveBeenCalled();

    // The coordinator re-arms tracing → THEN the effect drives MapboxDraw.
    rerender({ interactionMode: 'ficha-dibujo' as MapInteractionMode, drawSession: true });
    expect(drawControlRef.current.startDrawing).toHaveBeenCalledTimes(1);
  });

  it('"Borrar" wipes through the imperative handle and tolerates an unmounted control', () => {
    const drawControlRef = makeHandle();
    const redrawPolygon = vi.fn();
    const { result } = renderHook(() =>
      useFichaDrawWiring({
        interactionMode: 'idle',
        drawSession: true,
        redrawPolygon,
        drawControlRef,
      }),
    );

    result.current.handleDeletePolygon();
    expect(drawControlRef.current.clearDrawing).toHaveBeenCalledTimes(1);

    // Session closed → control unmounted → the handler must not throw.
    const detached = drawControlRef as { current: DrawControlHandle | null };
    detached.current = null;
    expect(() => result.current.handleDeletePolygon()).not.toThrow();
  });
});

// R3-101: mid-trace "Otro" must restart via the handle — the state path is a
// no-op there (tracing is already true) and the button used to go dead.
describe('handleRedrawPolygon mid-trace', () => {
	it('calls startDrawing directly while tracing instead of the inert state path', () => {
		const redrawPolygon = vi.fn();
		const startDrawing = vi.fn();
		const drawControlRef = {
			current: { startDrawing, clearDrawing: vi.fn() },
		};
		const { result } = renderHook(() =>
			useFichaDrawWiring({
				interactionMode: 'ficha-dibujo',
				drawSession: true,
				redrawPolygon,
				drawControlRef,
			})
		);
		startDrawing.mockClear(); // the kick-off effect already fired once on mount
		result.current.handleRedrawPolygon();
		expect(startDrawing).toHaveBeenCalledTimes(1);
		expect(redrawPolygon).not.toHaveBeenCalled();
	});
});
