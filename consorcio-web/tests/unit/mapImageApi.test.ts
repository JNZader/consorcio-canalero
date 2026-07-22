import { beforeEach, describe, expect, it, vi } from 'vitest';

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }));

vi.mock('../../src/lib/api/core', () => ({
  GEE_TIMEOUT: 300_000,
  apiFetch: apiFetchMock,
}));

import { mapImageApi } from '../../src/lib/api/mapImage';

describe('mapImageApi GEE boundary', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiFetchMock.mockResolvedValue({});
  });

  it('uses the fixed no-parameter public current-image URL', async () => {
    await mapImageApi.getPublicCurrentImage();

    expect(apiFetchMock).toHaveBeenCalledWith('/public/map/gee/current-image', {
      skipAuth: true,
      timeout: 300_000,
    });
    expect(apiFetchMock.mock.calls[0][0]).not.toContain('?');
  });

  it('keeps legacy parameter reads authenticated', async () => {
    await mapImageApi.getImageParams();

    expect(apiFetchMock).toHaveBeenCalledWith('/public/settings/mapa/imagen');
  });

  it('keeps arbitrary regeneration protected and carries AbortSignal', async () => {
    const controller = new AbortController();

    await mapImageApi.regenerateTile(
      {
        sensor: 'Landsat 8',
        target_date: '2026-03-05',
        visualization: 'ndvi',
        max_cloud: 20,
        days_buffer: 10,
        mode: 'composite',
      },
      { signal: controller.signal }
    );

    const [endpoint, options] = apiFetchMock.mock.calls[0];
    expect(endpoint).toBe(
      '/geo/gee/images/landsat8?target_date=2026-03-05&days_buffer=10&visualization=ndvi&max_cloud=20&mode=composite'
    );
    expect(options).toEqual({ timeout: 300_000, signal: controller.signal });
    expect(options).not.toHaveProperty('skipAuth');
  });
});
