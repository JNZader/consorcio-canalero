/**
 * useMapEscapeExit — Escape is the universal "get me out of this mode" key.
 *
 * Before this hook the map had NO exit path from a non-idle interaction mode:
 * `useMeasurement.cancel()` existed but was never wired to any UI, the toolbar's
 * trash button only rendered once at least one measurement had been saved, and
 * no keydown listener existed anywhere in the map tree. A user who started a
 * measurement (or entered draw / canal mode) and changed their mind was stuck
 * with a crosshair cursor and a map that would not select anything.
 *
 * Contract:
 *   - `measuring-distance` / `measuring-area` → `onCancelMeasurement()`
 *   - `ficha-dibujo`                          → `onExitDraw()`
 *   - `ficha-canal`                           → `onExitCanal()`
 *   - `idle`                                  → no-op (Escape stays available to
 *     modals, menus and the browser)
 *
 * Lifecycle: the `window` listener exists ONLY while a non-idle mode is active
 * (the effect early-returns on `idle`, so nothing is bound), and it is
 * re-subscribed whenever `mode` or any handler identity changes — the effect
 * cleanup removes the previous listener first, so there is never more than one.
 * Keystrokes originating in a text field are ignored so Escape keeps its native
 * meaning while the user is typing (e.g. clearing a search input).
 */

import { useEffect } from 'react';

import type { MapInteractionMode } from './measurement/useMeasurement';

export interface UseMapEscapeExitParams {
  /** The single interaction-mode value (see `useFichaInteraction`). */
  readonly mode: MapInteractionMode;
  /** Back to idle from a measurement, discarding the in-progress shape. */
  readonly onCancelMeasurement: () => void;
  /** Leave ficha free-draw mode. */
  readonly onExitDraw: () => void;
  /** Leave ficha canal-selection mode. */
  readonly onExitCanal: () => void;
}

/** True when the event came from a field where Escape has its own meaning. */
function isFromTextEntry(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable;
}

export function useMapEscapeExit({
  mode,
  onCancelMeasurement,
  onExitDraw,
  onExitCanal,
}: UseMapEscapeExitParams): void {
  useEffect(() => {
    if (mode === 'idle') return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      if (isFromTextEntry(event.target)) return;

      if (mode === 'measuring-distance' || mode === 'measuring-area') {
        onCancelMeasurement();
      } else if (mode === 'ficha-dibujo') {
        onExitDraw();
      } else if (mode === 'ficha-canal') {
        onExitCanal();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [mode, onCancelMeasurement, onExitDraw, onExitCanal]);
}
