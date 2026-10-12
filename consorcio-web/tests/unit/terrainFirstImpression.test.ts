import { describe, expect, it } from 'vitest';

import {
  resolveTerrainStartPitch,
  TERRAIN_DEFAULT_EXAGGERATION,
} from '../../src/components/terrain/terrainExaggeration';

describe('3D first impression (audit 3D-01 / 3D-02)', () => {
  it('ignores inherited 2D pitch 0 so the scene is not nadir', () => {
    expect(resolveTerrainStartPitch(undefined)).toBe(60);
    expect(resolveTerrainStartPitch(0)).toBe(60);
    expect(resolveTerrainStartPitch(5)).toBe(60);
    expect(resolveTerrainStartPitch(45)).toBe(45);
  });

  it('defaults exaggeration to ×20 for pampa, not ×200', () => {
    expect(TERRAIN_DEFAULT_EXAGGERATION).toBe(20);
  });
});
