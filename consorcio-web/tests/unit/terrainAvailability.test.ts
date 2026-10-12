import { describe, expect, it } from 'vitest';

import {
  resolveTerrainAvailability,
  terrainAvailabilityHint,
} from '../../src/components/map2d/terrainAvailability';

describe('resolveTerrainAvailability (UX-10)', () => {
  it('prefers loading over empty', () => {
    expect(resolveTerrainAvailability({ loading: true, error: null, hasDemRaw: false })).toBe(
      'loading',
    );
    expect(terrainAvailabilityHint('loading')).toMatch(/Cargando/);
  });

  it('surfaces error even if a stale layer exists', () => {
    expect(
      resolveTerrainAvailability({ loading: false, error: 'boom', hasDemRaw: true }),
    ).toBe('error');
    expect(terrainAvailabilityHint('error')).toMatch(/relieve/);
  });

  it('is ready only with a DEM and no error', () => {
    expect(resolveTerrainAvailability({ loading: false, error: null, hasDemRaw: true })).toBe(
      'ready',
    );
    expect(resolveTerrainAvailability({ loading: false, error: null, hasDemRaw: false })).toBe(
      'empty',
    );
  });
});
