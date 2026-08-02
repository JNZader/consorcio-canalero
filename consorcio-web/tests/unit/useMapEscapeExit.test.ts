/**
 * useMapEscapeExit.test.ts
 *
 * map-fluidity T1 — measurement / draw / canal modes used to be one-way doors:
 * `useMeasurement.cancel()` had no caller anywhere in the tree and no keydown
 * listener existed at all, so a user who started a mode and changed their mind
 * was stuck with a crosshair and a map that selected nothing.
 *
 * Contract pinned here: Escape exits whichever mode is active, is inert in
 * `idle`, ignores keystrokes coming from text-entry fields, and unregisters its
 * listener on unmount.
 */

import { renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { MapInteractionMode } from '../../src/components/map2d/measurement/useMeasurement';
import { useMapEscapeExit } from '../../src/components/map2d/useMapEscapeExit';

function setup(mode: MapInteractionMode) {
  const handlers = {
    onCancelMeasurement: vi.fn(),
    onExitDraw: vi.fn(),
    onExitCanal: vi.fn(),
  };
  const view = renderHook(() => useMapEscapeExit({ mode, ...handlers }));
  return { ...handlers, ...view };
}

function pressEscape(target: EventTarget = window) {
  const event = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true });
  target.dispatchEvent(event);
}

afterEach(() => {
  document.body.innerHTML = '';
});

describe('useMapEscapeExit', () => {
  it('cancels the measurement when Escape is pressed in measuring-distance', () => {
    const { onCancelMeasurement, onExitDraw, onExitCanal } = setup('measuring-distance');

    pressEscape();

    expect(onCancelMeasurement).toHaveBeenCalledTimes(1);
    expect(onExitDraw).not.toHaveBeenCalled();
    expect(onExitCanal).not.toHaveBeenCalled();
  });

  it('cancels the measurement when Escape is pressed in measuring-area', () => {
    const { onCancelMeasurement } = setup('measuring-area');

    pressEscape();

    expect(onCancelMeasurement).toHaveBeenCalledTimes(1);
  });

  it('exits draw mode when Escape is pressed in ficha-dibujo', () => {
    const { onExitDraw, onCancelMeasurement, onExitCanal } = setup('ficha-dibujo');

    pressEscape();

    expect(onExitDraw).toHaveBeenCalledTimes(1);
    expect(onCancelMeasurement).not.toHaveBeenCalled();
    expect(onExitCanal).not.toHaveBeenCalled();
  });

  it('exits canal mode when Escape is pressed in ficha-canal', () => {
    const { onExitCanal, onCancelMeasurement, onExitDraw } = setup('ficha-canal');

    pressEscape();

    expect(onExitCanal).toHaveBeenCalledTimes(1);
    expect(onCancelMeasurement).not.toHaveBeenCalled();
    expect(onExitDraw).not.toHaveBeenCalled();
  });

  it('does nothing in idle so Escape stays available to modals and menus', () => {
    const { onCancelMeasurement, onExitDraw, onExitCanal } = setup('idle');

    pressEscape();

    expect(onCancelMeasurement).not.toHaveBeenCalled();
    expect(onExitDraw).not.toHaveBeenCalled();
    expect(onExitCanal).not.toHaveBeenCalled();
  });

  it('ignores keys other than Escape', () => {
    const { onCancelMeasurement } = setup('measuring-distance');

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));

    expect(onCancelMeasurement).not.toHaveBeenCalled();
  });

  it('ignores Escape typed inside a text field (native meaning wins there)', () => {
    const { onCancelMeasurement } = setup('measuring-distance');
    const input = document.createElement('input');
    document.body.appendChild(input);

    pressEscape(input);

    expect(onCancelMeasurement).not.toHaveBeenCalled();
  });

  it('removes its listener on unmount', () => {
    const { onCancelMeasurement, unmount } = setup('measuring-distance');

    unmount();
    pressEscape();

    expect(onCancelMeasurement).not.toHaveBeenCalled();
  });
});
