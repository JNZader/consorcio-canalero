import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useReportLocation } from '../../src/components/report-form/useReportLocation';

type HookParams = Parameters<typeof useReportLocation>[0];

function renderLocationHook(url: string) {
  // El prefill lee `window.location.search` en el mount: seteamos la URL
  // ANTES de montar el hook.
  window.history.replaceState({}, '', url);
  const form = {
    values: { tipo: '', descripcion: '', foto: null },
  } as unknown as HookParams['form'];
  return renderHook(() => useReportLocation({ announce: vi.fn(), form }));
}

describe('useReportLocation (prefill desde la URL)', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', '/');
  });

  it('no prefila nada cuando falta lat/lng — antes caía en Null Island {lat: 0, lng: 0}', () => {
    // `params.get('lat')` devuelve null y `Number(null) === 0`, que SÍ
    // pasa `Number.isFinite`: sin el guard esta URL prefilleaba el
    // océano frente a África y abría el input manual.
    const { result } = renderLocationHook('/participacion?ubicacion=elegida');

    expect(result.current.ubicacion).toBeNull();
    expect(result.current.mostrarInputManual).toBe(false);
  });

  it('no prefila coordenadas fuera de rango (lat=999)', () => {
    const { result } = renderLocationHook('/participacion?ubicacion=elegida&lat=999&lng=-62.7');

    expect(result.current.ubicacion).toBeNull();
    expect(result.current.mostrarInputManual).toBe(false);
  });

  it('no prefila cuando lat es un string vacío', () => {
    const { result } = renderLocationHook('/participacion?ubicacion=elegida&lat=&lng=-62.7');

    expect(result.current.ubicacion).toBeNull();
    expect(result.current.mostrarInputManual).toBe(false);
  });

  it('prefila lat/lng válidos y abre el input manual', () => {
    const { result } = renderLocationHook('/participacion?ubicacion=elegida&lat=-32.62&lng=-62.7');

    expect(result.current.ubicacion).toEqual({ lat: -32.62, lng: -62.7 });
    expect(result.current.mostrarInputManual).toBe(true);
  });

  it('acepta los límites exactos del rango (lat=±90, lng=±180)', () => {
    const { result } = renderLocationHook('/participacion?ubicacion=elegida&lat=90&lng=-180');

    expect(result.current.ubicacion).toEqual({ lat: 90, lng: -180 });
    expect(result.current.mostrarInputManual).toBe(true);
  });
});
