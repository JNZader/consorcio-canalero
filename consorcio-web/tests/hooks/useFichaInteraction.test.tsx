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

describe('useFichaInteraction · canal buffer (A6)', () => {
  it('entering canal mode derives ficha-canal and cancels measurement, no request yet', () => {
    const onEnterDraw = vi.fn();
    const { result } = renderHook(() => useFichaInteraction('measuring-distance', onEnterDraw));

    act(() => result.current.startCanal());
    expect(onEnterDraw).toHaveBeenCalledTimes(1); // measurement cancelled
    expect(result.current.state.canalMode).toBe(true);
    expect(result.current.interactionMode).toBe('ficha-canal');
    expect(result.current.request).toBeNull(); // no canal clicked yet
  });

  it('resolving a canal fires a tipo=canal_buffer request with the default buffer', () => {
    const { result } = renderHook(() => useFichaInteraction('idle', vi.fn()));
    act(() => result.current.startCanal());
    act(() => result.current.resolveCanal(42));

    expect(result.current.request).toEqual({ tipo: 'canal_buffer', canal_id: 42, buffer_m: 500 });
    expect(result.current.tipo).toBe('canal_buffer');
    expect(result.current.state.canal).toEqual({ canalId: 42, bufferM: 500 });
  });

  it('setBuffer re-fires the request with the new distance, keeping the canal', () => {
    const { result } = renderHook(() => useFichaInteraction('idle', vi.fn()));
    act(() => result.current.startCanal());
    act(() => result.current.resolveCanal(7));
    act(() => result.current.setBuffer(1200));

    expect(result.current.request).toEqual({ tipo: 'canal_buffer', canal_id: 7, buffer_m: 1200 });
  });

  it('picking another canal keeps the buffer the user already dialed in', () => {
    const { result } = renderHook(() => useFichaInteraction('idle', vi.fn()));
    act(() => result.current.startCanal());
    act(() => result.current.resolveCanal(1));
    act(() => result.current.setBuffer(800));
    act(() => result.current.resolveCanal(2)); // click a different canal

    expect(result.current.request).toEqual({ tipo: 'canal_buffer', canal_id: 2, buffer_m: 800 });
  });

  it('setBuffer is a no-op before any canal is selected', () => {
    const { result } = renderHook(() => useFichaInteraction('idle', vi.fn()));
    act(() => result.current.startCanal());
    act(() => result.current.setBuffer(1500));
    expect(result.current.request).toBeNull();
    expect(result.current.state.canal).toBeNull();
  });

  it('starting canal mode DISCARDS a previous parcel ficha', () => {
    const { result } = renderHook(() => useFichaInteraction('idle', vi.fn()));
    act(() => result.current.resolveParcela(PARCELA));
    expect(result.current.tipo).toBe('parcela');

    act(() => result.current.startCanal());
    expect(result.current.request).toBeNull(); // parcel ficha gone
    expect(result.current.state.parcela).toBeNull();
  });

  it('a parcel click is IGNORED while in canal mode (canal owns clicks)', () => {
    const { result } = renderHook(() => useFichaInteraction('idle', vi.fn()));
    act(() => result.current.startCanal());
    act(() => result.current.resolveCanal(9));
    act(() => result.current.resolveParcela(PARCELA)); // stray parcel resolution
    expect(result.current.request).toEqual({ tipo: 'canal_buffer', canal_id: 9, buffer_m: 500 });
  });

  it('startDraw and startCanal are mutually exclusive (one machine)', () => {
    const { result } = renderHook(() => useFichaInteraction('idle', vi.fn()));
    act(() => result.current.startCanal());
    act(() => result.current.resolveCanal(3));
    expect(result.current.interactionMode).toBe('ficha-canal');

    act(() => result.current.startDraw()); // switch to drawing
    expect(result.current.state.canalMode).toBe(false);
    expect(result.current.state.canal).toBeNull();
    expect(result.current.interactionMode).toBe('ficha-dibujo');
    expect(result.current.request).toBeNull();
  });

  it('stopCanal resets to idle', () => {
    const { result } = renderHook(() => useFichaInteraction('idle', vi.fn()));
    act(() => result.current.startCanal());
    act(() => result.current.resolveCanal(5));
    act(() => result.current.stopCanal());
    expect(result.current.state.canalMode).toBe(false);
    expect(result.current.request).toBeNull();
    expect(result.current.interactionMode).toBe('idle');
  });

  it('resolveCanal(null) clears the selection but stays in canal mode', () => {
    const { result } = renderHook(() => useFichaInteraction('idle', vi.fn()));
    act(() => result.current.startCanal());
    act(() => result.current.resolveCanal(5));
    act(() => result.current.resolveCanal(null)); // click missed a canal
    expect(result.current.request).toBeNull();
    expect(result.current.state.canalMode).toBe(true);
  });
});
