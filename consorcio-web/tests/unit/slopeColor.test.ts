import { describe, expect, it } from 'vitest';

import { coarseProfile, terrainRgbMeters, tilePixel } from '../../src/components/map2d/coarseDem';
import { slopeColor, slopeLineFeatures, slopeSegments } from '../../src/components/map2d/slopeColor';

describe('slope color', () => {
  it('stays green when the trace is flat and red when it is steep', () => {
    expect(slopeColor(0)).toBe('#16a34a');
    expect(slopeColor(5)).toBe('#dc2626');
    expect(slopeColor(-5)).toBe('#dc2626');
  });

  it('colors each chart step and the matching map segment', () => {
    const samples = [
      { distance_m: 0, elevation_m: 100, lon: 0, lat: 0 },
      { distance_m: 100, elevation_m: 100, lon: 0.001, lat: 0 },
      { distance_m: 130, elevation_m: 110, lon: 0.002, lat: 0 },
    ];
    const pieces = slopeSegments(samples);
    expect(pieces[0]?.color).toBe('#16a34a');
    expect(pieces[1]?.color).not.toBe('#16a34a');
    expect(slopeLineFeatures(samples)).toHaveLength(2);
  });
});

describe('client DEM', () => {
  it('decodes terrain-RGB and samples a line from a fake tile', async () => {
    expect(terrainRgbMeters(1, 134, 160)).toBeCloseTo(-10000 + (1 * 65536 + 134 * 256 + 160) * 0.1);
    const pixel = tilePixel(-64.18, -32.41, 2);
    expect(pixel.x).toBeGreaterThanOrEqual(0);
    const rows = await coarseProfile(
      { type: 'LineString', coordinates: [[-64.2, -32.4], [-64.19, -32.4]] },
      { async read() { return { r: 1, g: 134, b: 160 }; } }
    );
    expect(rows).toHaveLength(2);
    expect(rows[1]!.elevation_m).not.toBeNull();
    expect(rows[1]!.distance_m).toBeGreaterThan(0);
  });
});
