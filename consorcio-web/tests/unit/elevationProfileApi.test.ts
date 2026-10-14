/**
 * Public/operator boundary of the elevation-profile API.
 *
 * The plain GLO-30 profile is a public read (anonymous route, no session).
 * AW3D30/NASADEM bring GEE cost, so they stay on the authenticated route.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }));

vi.mock('../../src/lib/api/core', () => ({ apiFetch: apiFetchMock }));

import { fetchElevationProfile } from '../../src/lib/api/elevationProfile';

const line = {
  type: 'LineString' as const,
  coordinates: [
    [-62.7, -32.6],
    [-62.71, -32.61],
  ],
};

describe('elevationProfile API boundary', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiFetchMock.mockResolvedValue({});
  });

  it('samples the local DEM on the anonymous public route by default', async () => {
    await fetchElevationProfile(line);

    expect(apiFetchMock).toHaveBeenCalledWith('/public/map/elevation-profile', {
      method: 'POST',
      skipAuth: true,
      body: JSON.stringify({ geometry: line, area_id: null }),
    });
  });

  it('forwards area_id without asking for a session', async () => {
    await fetchElevationProfile(line, 'area-9');

    const [endpoint, options] = apiFetchMock.mock.calls[0];
    expect(endpoint).toBe('/public/map/elevation-profile');
    expect(options.skipAuth).toBe(true);
    expect(JSON.parse(options.body)).toEqual({ geometry: line, area_id: 'area-9' });
  });

  it('keeps GEE DEM comparison on the authenticated operator route', async () => {
    await fetchElevationProfile(line, undefined, true);

    const [endpoint, options] = apiFetchMock.mock.calls[0];
    expect(endpoint).toBe('/geo/elevation-profile');
    expect(options).not.toHaveProperty('skipAuth');
    expect(JSON.parse(options.body)).toEqual({
      geometry: line,
      area_id: null,
      compare_dems: true,
    });
  });
});
