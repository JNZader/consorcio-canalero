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

    it('Option B: applies design slope and anchor depth to drain depressions (lagunas)', () => {
      // 5 km trace modeled on user screenshot:
      // start at 118.7m, low point at 3 km (117.5m), outlet at 5 km (118.0m)
      const samples = [
        { distance_m: 0, elevation_m: 118.7 },
        { distance_m: 600, elevation_m: 120.4 }, // parcel ridge
        { distance_m: 3000, elevation_m: 117.5 }, // laguna low point
        { distance_m: 5000, elevation_m: 118.0 }, // outlet near arroyo
      ];

      // Shallow outlet cut (0.2m): not deep enough to drain the 117.5m depression at 0.3‰
      const shallow = simulateCanalSolera(samples, {
        anchor: 'descarga',
        depthAtAnchor_m: 0.2,
        designSlopePerMil: 0.3,
      });
      expect(shallow.ok).toBe(true);
      if (!shallow.ok) return;

      expect(shallow.stats.zEnd).toBe(117.8); // 118.0 - 0.2
      // Solera at 3000m (2000m from outlet): 117.8 + (0.3/1000 * 2000) = 118.4m
      // Ground is at 117.5m, so solera is ABOVE ground by 0.9m!
      expect(shallow.stats.isDraining).toBe(false);
      expect(shallow.stats.maxEmbankment_m).toBeCloseTo(0.9, 1);
      expect(shallow.stats.requiredDeepening_m).toBeCloseTo(0.9, 1);

      // Deep outlet cut (1.5m into arroyo box): solera at outlet = 116.5m
      const deep = simulateCanalSolera(samples, {
        anchor: 'descarga',
        depthAtAnchor_m: 1.5,
        designSlopePerMil: 0.3,
      });
      expect(deep.ok).toBe(true);
      if (!deep.ok) return;

      expect(deep.stats.zEnd).toBe(116.5); // 118.0 - 1.5
      // Solera at 3000m: 116.5 + (0.3/1000 * 2000) = 117.1m
      // Ground is 117.5m, solera is 117.1m => cut of +0.4m (fully drains!)
      expect(deep.stats.isDraining).toBe(true);
      expect(deep.stats.maxEmbankment_m).toBe(0);
      expect(deep.stats.maxCut_m).toBeCloseTo(20.4 - 17.82, 0); // ridge cut ~2.6m
    });
  });
});
