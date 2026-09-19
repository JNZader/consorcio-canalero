import { beforeEach, describe, expect, it, vi } from 'vitest';

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }));

vi.mock('../../src/lib/api/core', () => ({
  apiFetch: apiFetchMock,
}));

import {
  PUNTO_INTERES_TIPOS,
  createPuntoInteres,
  deletePuntoInteres,
  fetchPuntosInteres,
} from '../../src/lib/api/puntosInteres';

describe('PUNTO_INTERES_TIPOS', () => {
  it('exposes the four persisted kinds', () => {
    expect(PUNTO_INTERES_TIPOS).toEqual({
      ALCANTARILLA: 'alcantarilla',
      ALTEO: 'alteo',
      TAPONAMIENTO: 'taponamiento',
      OTRO: 'otro',
    });
  });
});

describe('puntosInteres API client', () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
  });

  it('GETs /geo/puntos-interes', async () => {
    apiFetchMock.mockResolvedValue({ type: 'FeatureCollection', features: [] });
    await fetchPuntosInteres();
    expect(apiFetchMock).toHaveBeenCalledWith('/geo/puntos-interes', { signal: undefined });
  });

  it('POSTs /geo/puntos-interes', async () => {
    apiFetchMock.mockResolvedValue({ type: 'Feature' });
    await createPuntoInteres({
      lng: -62.8,
      lat: -32.5,
      titulo: 'Alteo',
      tipo: PUNTO_INTERES_TIPOS.ALTEO,
    });
    expect(apiFetchMock).toHaveBeenCalledWith('/geo/puntos-interes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        lng: -62.8,
        lat: -32.5,
        titulo: 'Alteo',
        tipo: 'alteo',
      }),
      signal: undefined,
    });
  });

  it('DELETEs /geo/puntos-interes/:id', async () => {
    apiFetchMock.mockResolvedValue(undefined);
    await deletePuntoInteres('11111111-1111-4111-8111-111111111111');
    expect(apiFetchMock).toHaveBeenCalledWith(
      '/geo/puntos-interes/11111111-1111-4111-8111-111111111111',
      { method: 'DELETE', signal: undefined }
    );
  });
});
