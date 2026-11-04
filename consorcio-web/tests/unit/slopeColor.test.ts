import { describe, expect, it } from 'vitest';

import { coarseProfile, terrainRgbMeters, tilePixel } from '../../src/components/map2d/coarseDem';
import {
  CANAL_SLOPE_SCALE,
  DEFAULT_SLOPE_SCALE,
  profileSlopeScale,
  SLOPE_COLOR_STOPS,
  slopeColor,
  slopeLineFeatures,
  slopeSegments,
  slopeSeverityLabel,
  TRANSICION_SLOPE_SCALE,
} from '../../src/components/map2d/slopeColor';

describe('slope color (A11Y-07 colorblind-safe Okabe-Ito ramp)', () => {
  it('uses Okabe-Ito blue when flat, amber around 2%, and vermilion from 5% up', () => {
    expect(slopeColor(0)).toBe(SLOPE_COLOR_STOPS.LOW);
    expect(slopeColor(2)).toBe(SLOPE_COLOR_STOPS.MEDIUM);
    expect(slopeColor(5)).toBe(SLOPE_COLOR_STOPS.HIGH);
    expect(slopeColor(-5)).toBe(SLOPE_COLOR_STOPS.HIGH);
    expect(slopeSeverityLabel(0.5)).toBe('Baja');
    expect(slopeSeverityLabel(3)).toBe('Media');
    expect(slopeSeverityLabel(-6)).toBe('Alta');
  });

  it('colors each chart step and the matching map segment', () => {
    const samples = [
      { distance_m: 0, elevation_m: 100, lon: 0, lat: 0 },
      { distance_m: 100, elevation_m: 100, lon: 0.001, lat: 0 },
      { distance_m: 130, elevation_m: 110, lon: 0.002, lat: 0 },
    ];
    const pieces = slopeSegments(samples);
    expect(pieces[0]?.color).toBe(SLOPE_COLOR_STOPS.LOW);
    expect(pieces[1]?.color).not.toBe(SLOPE_COLOR_STOPS.LOW);
    expect(slopeLineFeatures(samples)).toHaveLength(2);
  });

  it('adaptively classifies flat canal profiles into the Canal / Llanura regime', () => {
    // 1 km canal with gentle slope (0.05 m per 100 m = 0.05 %)
    const canalSamples = [
      { distance_m: 0, elevation_m: 114.0 },
      { distance_m: 200, elevation_m: 113.9 },
      { distance_m: 400, elevation_m: 113.8 },
      { distance_m: 600, elevation_m: 113.7 },
      { distance_m: 800, elevation_m: 113.6 },
      { distance_m: 1000, elevation_m: 113.5 },
    ];
    const scale = profileSlopeScale(canalSamples);
    expect(scale.regime).toBe('canal');
    expect(scale.regimeLabel).toBe('Canal / Llanura');
    expect(scale.lowMax).toBe(0.05);
    expect(scale.mediumMax).toBe(0.2);

    expect(slopeSeverityLabel(0.02, scale)).toBe('Baja');
    expect(slopeSeverityLabel(0.1, scale)).toBe('Media');
    expect(slopeSeverityLabel(0.25, scale)).toBe('Alta');

    expect(slopeColor(0.05, scale)).toBe(SLOPE_COLOR_STOPS.MEDIUM);
    expect(slopeColor(0.25, scale)).toBe(SLOPE_COLOR_STOPS.HIGH);
  });

  it('adaptively classifies transition profiles and steep terrain profiles', () => {
    const transitionSamples = [
      { distance_m: 0, elevation_m: 100 },
      { distance_m: 100, elevation_m: 101 }, // 1 % slope
      { distance_m: 200, elevation_m: 102 }, // 1 % slope
    ];
    expect(profileSlopeScale(transitionSamples).regime).toBe('transicion');

    const steepSamples = [
      { distance_m: 0, elevation_m: 100 },
      { distance_m: 100, elevation_m: 105 }, // 5 % slope
      { distance_m: 200, elevation_m: 110 },
    ];
    expect(profileSlopeScale(steepSamples).regime).toBe('terreno');
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
