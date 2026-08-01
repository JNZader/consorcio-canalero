/**
 * useFichaInteraction — the ONE interaction-mode coordinator (A5.2, JDB-012).
 *
 * Pins the invariants the design mandates without mounting a map:
 *   - starting a drawing DISCARDS the previous parcel ficha (spec "Switching
 *     modes discards previous result") and cancels measurement (mutual exclusion);
 *   - a completed polygon fires a `tipo=poligono` request and stays in draw mode;
 *   - the derived `interactionMode` is the single machine: `ficha-dibujo` while
 *     drawing, otherwise it passes the measurement mode straight through;
 *   - a parcel click is ignored WHILE drawing (DrawControl owns clicks) and
 *     supersedes a drawn ficha otherwise.
 */

import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { DrawnPolygon } from '../../src/components/map/DrawControl';
import { useFichaInteraction } from '../../src/components/map2d/useFichaInteraction';

const PARCELA = { nomenclatura: '13-06-01-0203', nroCuenta: '110123' };
const POLY: DrawnPolygon = {
  type: 'Polygon',
  coordinates: [
    [
      [-62, -32],
      [-62, -32.1],
      [-61.9, -32.1],
      [-62, -32],
    ],
  ],
};

describe('useFichaInteraction', () => {
  it('starts idle: no request, mode mirrors the measurement mode', () => {
    const { result } = renderHook(() => useFichaInteraction('idle', vi.fn()));
    expect(result.current.request).toBeNull();
    expect(result.current.interactionMode).toBe('idle');
    expect(result.current.state.drawing).toBe(false);
  });

  it('passes the measurement mode through when not drawing (one machine)', () => {
    const { result } = renderHook(() => useFichaInteraction('measuring-area', vi.fn()));
    expect(result.current.interactionMode).toBe('measuring-area');
  });

  it('starting a drawing DISCARDS the previous parcel ficha and cancels measurement', () => {
    const onEnterDraw = vi.fn();
    const { result } = renderHook(() => useFichaInteraction('idle', onEnterDraw));

    // A parcel is selected first (a prior click).
    act(() => result.current.resolveParcela(PARCELA));
    expect(result.current.request).toEqual({ tipo: 'parcela', nomenclatura: PARCELA.nomenclatura });

    // Entering draw mode wipes it and cancels any live measurement.
    act(() => result.current.startDraw());
    expect(onEnterDraw).toHaveBeenCalledTimes(1);
    expect(result.current.state.drawing).toBe(true);
    expect(result.current.interactionMode).toBe('ficha-dibujo');
    expect(result.current.request).toBeNull(); // previous parcel ficha discarded
    expect(result.current.nroCuenta).toBeNull();
  });

  it('a completed polygon fires a tipo=poligono request and stays in draw mode', () => {
    const { result } = renderHook(() => useFichaInteraction('idle', vi.fn()));
    act(() => result.current.startDraw());
    act(() => result.current.completePolygon(POLY));

    expect(result.current.request).toEqual({ tipo: 'poligono', geometry: POLY });
    expect(result.current.tipo).toBe('poligono');
    expect(result.current.state.drawing).toBe(true); // shape stays visible while its ficha shows
    expect(result.current.interactionMode).toBe('ficha-dibujo');
  });

  it('ignores a parcel click WHILE drawing (DrawControl owns clicks)', () => {
    const { result } = renderHook(() => useFichaInteraction('idle', vi.fn()));
    act(() => result.current.startDraw());
    act(() => result.current.completePolygon(POLY));

    act(() => result.current.resolveParcela(PARCELA)); // a stray click mid-draw
    expect(result.current.request).toEqual({ tipo: 'poligono', geometry: POLY });
  });

  it('a fresh parcel click supersedes a drawn ficha once drawing has stopped', () => {
    const { result } = renderHook(() => useFichaInteraction('idle', vi.fn()));
    act(() => result.current.startDraw());
    act(() => result.current.completePolygon(POLY));
    act(() => result.current.stopDraw()); // leave draw mode → everything cleared

    expect(result.current.request).toBeNull();

    act(() => result.current.resolveParcela(PARCELA));
    expect(result.current.request).toEqual({ tipo: 'parcela', nomenclatura: PARCELA.nomenclatura });
    expect(result.current.nroCuenta).toBe('110123');
  });

  it('stopDraw and clearFicha reset to idle', () => {
    const { result } = renderHook(() => useFichaInteraction('idle', vi.fn()));
    act(() => result.current.startDraw());
    act(() => result.current.stopDraw());
    expect(result.current.state.drawing).toBe(false);
    expect(result.current.request).toBeNull();

    act(() => result.current.resolveParcela(PARCELA));
    act(() => result.current.clearFicha());
    expect(result.current.request).toBeNull();
  });

  it('deletePolygon clears the drawn ficha without leaving draw mode', () => {
    const { result } = renderHook(() => useFichaInteraction('idle', vi.fn()));
    act(() => result.current.startDraw());
    act(() => result.current.completePolygon(POLY));
    act(() => result.current.deletePolygon());
    expect(result.current.request).toBeNull();
    expect(result.current.state.drawing).toBe(true);
  });
});
