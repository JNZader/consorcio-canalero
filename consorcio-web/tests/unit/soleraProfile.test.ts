import { describe, expect, it } from 'vitest';

import {
  pairedSurveys,
  simulateCanalSolera,
  soleraCover,
} from '../../src/components/map2d/soleraProfile';

describe('solera and survey comparison', () => {
  it('shades cover only when an invert is present', () => {
    const missing = soleraCover([
      { distance_m: 0, elevation_m: 100 },
      { distance_m: 30, elevation_m: 99 },
    ]);
    expect(missing).toEqual({ ok: false, reason: 'missing' });
    const present = soleraCover([
      { distance_m: 0, elevation_m: 100, solera_m: 98 },
      { distance_m: 30, elevation_m: 99, solera_m: 97.5 },
    ]);
    expect(present.ok).toBe(true);
    if (present.ok) expect(present.rows[0]?.cover_m).toBe(2);
  });

  it('refuses a second profile that was never stored', () => {
    expect(
      pairedSurveys(
        { id: 'a', label: '2024', samples: [{ distance_m: 0, elevation_m: 1 }, { distance_m: 1, elevation_m: 2 }] },
        null
      )
    ).toEqual({ ok: false, reason: 'missing' });
  });

  describe('simulateCanalSolera', () => {
    it('returns missing when there are fewer than 2 valid points', () => {
      expect(simulateCanalSolera([])).toEqual({ ok: false, reason: 'missing' });
      expect(simulateCanalSolera([{ distance_m: 0, elevation_m: 100 }])).toEqual({
        ok: false,
        reason: 'missing',
      });
    });

    it('simulates a gravity canal solera and detects excavation cut at an obstacle (eucalyptus grove)', () => {
      // 5 km trace: starts at 118.6m, ends at 117.8m, with a 125.4m obstacle at 1.1 km
      const samples = [
        { distance_m: 0, elevation_m: 118.6 },
        { distance_m: 1100, elevation_m: 125.4 }, // eucalyptus spike
        { distance_m: 5000, elevation_m: 117.8 },
      ];
      const result = simulateCanalSolera(samples, 'digitizado');
      expect(result.ok).toBe(true);
      if (!result.ok) return;

      expect(result.stats.zStart).toBe(118.6);
      expect(result.stats.zEnd).toBe(117.8);
      expect(result.stats.deltaZ).toBeCloseTo(-0.8);
      // Slope: -0.8 / 5000 * 100 = -0.016 % = -0.16 por mil
      expect(result.stats.slopePct).toBeCloseTo(-0.016);
      expect(result.stats.slopePerMil).toBeCloseTo(-0.16);

      // Solera at 1100 m: 118.6 + (-0.00016 * 1100) = 118.6 - 0.176 = 118.424 m
      // Cut at 1100 m: 125.4 - 118.424 = 6.976 m (approx 7.0 m!)
      expect(result.stats.maxCut_m).toBeCloseTo(6.976, 2);
      expect(result.stats.dMaxCut_m).toBe(1100);
      expect(result.rows[1]?.simulatedCut_m).toBeCloseTo(6.976, 2);
    });

    it('respects inverso flow direction for upstream and downstream endpoints', () => {
      const samples = [
        { distance_m: 0, elevation_m: 110.0 }, // downstream exit
        { distance_m: 1000, elevation_m: 112.0 }, // upstream head
      ];
      const result = simulateCanalSolera(samples, 'inverso');
      expect(result.ok).toBe(true);
      if (!result.ok) return;

      expect(result.stats.orientation).toBe('inverso');
      expect(result.stats.zStart).toBe(112.0); // upstream
      expect(result.stats.zEnd).toBe(110.0); // downstream
      expect(result.stats.deltaZ).toBe(-2.0);
      expect(result.stats.slopePct).toBe(-0.2);
    });
  });
});
