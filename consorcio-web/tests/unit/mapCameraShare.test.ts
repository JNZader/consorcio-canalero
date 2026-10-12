import { describe, expect, it } from 'vitest';

import {
  hasMapLibreCameraHash,
  shouldApplyQueryCamera,
  stripCameraQuery,
} from '../../src/components/map2d/mapCameraShare';

describe('mapCameraShare UX-03', () => {
  it('detects MapLibre hash v packs', () => {
    expect(hasMapLibreCameraHash('#v=12.4/-32.54/-62.53')).toBe(true);
    expect(hasMapLibreCameraHash('v=11/-32/-62')).toBe(true);
    expect(hasMapLibreCameraHash('#preset=agua')).toBe(false);
    expect(hasMapLibreCameraHash('')).toBe(false);
  });

  it('strips leftover query camera keys', () => {
    expect(stripCameraQuery('?lat=-32.5&lng=-62.5&zoom=12&preset=agua')).toBe('?preset=agua');
    expect(stripCameraQuery('?lat=-32.5')).toBe('');
  });

  it('does not fly from query when hash already owns the camera', () => {
    expect(shouldApplyQueryCamera('?lat=-32.5&lng=-62.5', '#v=12/-32.5/-62.5')).toBe(false);
    expect(shouldApplyQueryCamera('?lat=-32.5&lng=-62.5', '')).toBe(true);
    expect(shouldApplyQueryCamera('?preset=agua', '')).toBe(false);
  });
});
