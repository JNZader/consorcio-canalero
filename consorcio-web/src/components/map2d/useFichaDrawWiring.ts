import { type RefObject, useCallback, useEffect } from 'react';

import type { DrawControlHandle } from '../map/DrawControl';
import type { MapInteractionMode } from './measurement/useMeasurement';

export interface UseFichaDrawWiringParams {
  /** `'ficha-dibujo'` exactly while MapboxDraw is TRACING (see `useFichaInteraction`). */
  readonly interactionMode: MapInteractionMode;
  /** `state.drawing` — the draw SESSION, which outlives tracing. */
  readonly drawSession: boolean;
  /** Re-arms tracing without discarding the polygon already on screen ("Otro"). */
  readonly redrawPolygon: () => void;
  /** Imperative handle of the mounted `DrawControl` (null while unmounted). */
  readonly drawControlRef: RefObject<DrawControlHandle | null>;
}

export interface UseFichaDrawWiringResult {
  /** True while MapboxDraw owns clicks. Drives the kick-off effect. */
  readonly isTracing: boolean;
  /** True while the control must stay mounted and the toolbar lit. */
  readonly isDrawSession: boolean;
  /**
   * The mode handed to `useMapEscapeExit`.
   *
   * SYNTHESISED: after `draw.create` the real `interactionMode` is back to
   * `idle` (clicks belong to the map again), but the draw SESSION is still open
   * — the control is mounted and a polygon is on screen. Passing the raw mode
   * would have made Escape a no-op exactly there, silently dropping the only
   * keyboard exit from a session the user CAN see.
   */
  readonly escapeMode: MapInteractionMode;
  /**
   * "Otro" — restarts the trace. Post-`draw.create` it goes through STATE and
   * the kick-off effect does the imperative part; MID-trace it calls the
   * handle directly (tracing is already true, so the state path would be a
   * no-op and the button would go dead).
   */
  readonly handleRedrawPolygon: () => void;
  /** "Borrar" — imperative wipe; `draw.delete` clears the ficha. */
  readonly handleDeletePolygon: () => void;
}

/**
 * Container wiring for the ficha free-draw session (T4).
 *
 * Extracted from `MapaMapLibre` so the two non-obvious decisions it encodes are
 * testable without mounting a 1200-line map component:
 *
 *  1. `escapeMode` synthesises `'ficha-dibujo'` for the whole session, not just
 *     while tracing.
 *  2. "Otro" goes through STATE (`redrawPolygon`) when tracing is off.
 *     Post-`draw.create`, calling `drawControlRef.current.startDrawing()`
 *     directly would put MapboxDraw in `draw_polygon` while React still
 *     believed the map was click-selectable, so a click aimed at a vertex
 *     would resolve a parcel instead. MID-trace is the one exception (see
 *     `handleRedrawPolygon`): there the state path is a no-op and the direct
 *     call is safe because MapboxDraw already owns the clicks.
 */
export function useFichaDrawWiring({
  interactionMode,
  drawSession,
  redrawPolygon,
  drawControlRef,
}: UseFichaDrawWiringParams): UseFichaDrawWiringResult {
  const isTracing = interactionMode === 'ficha-dibujo';

  // DrawControl's mount effect (which populates the handle) is a CHILD passive
  // effect and runs BEFORE this parent effect, so the ref is ready here. Runs
  // again whenever "Otro" re-arms tracing.
  useEffect(() => {
    if (isTracing) drawControlRef.current?.startDrawing();
  }, [isTracing, drawControlRef]);

  const handleRedrawPolygon = useCallback(() => {
    if (isTracing) {
      // Mid-trace restart: `tracing` is already true, so the state path is a
      // no-op (the kick-off effect will not re-run) and the button would go
      // dead. Going straight to the handle is safe HERE and only here:
      // MapboxDraw already owns the clicks, so the hazard documented above
      // (draw_polygon over a live click whitelist) cannot occur.
      // `startDrawing()` discards the half-placed vertices and restarts.
      drawControlRef.current?.startDrawing();
      return;
    }
    redrawPolygon();
  }, [isTracing, redrawPolygon, drawControlRef]);

  const handleDeletePolygon = useCallback(() => {
    drawControlRef.current?.clearDrawing();
  }, [drawControlRef]);

  return {
    isTracing,
    isDrawSession: drawSession,
    escapeMode: drawSession ? 'ficha-dibujo' : interactionMode,
    handleRedrawPolygon,
    handleDeletePolygon,
  };
}
