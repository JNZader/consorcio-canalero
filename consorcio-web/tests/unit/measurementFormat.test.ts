/**
 * Unit tests for measurement unit-formatting helpers.
 *
 * Module under test: src/components/map2d/measurement/measurementFormat.ts
 *
 * Thresholds & conventions (locked by these tests):
 * - formatDistance:
 *   - < 1000 m → "N m" (Math.round to integer)
 *   - >= 1000 m → "X.Y km" (toFixed(1), keeps trailing zero → "1.0 km")
 *   - Threshold check uses the PRE-rounding value. 999.9 is below 1000 m,
 *     so it stays in the meter branch and renders as "1000 m" (rounded up
 *     but still formatted as meters). This is the intentional cheap cut:
 *     we do not re-check the threshold after rounding.
 *   - Negative input → treated as soft error, clamped to 0 → "0 m".
 *   - NaN / Infinity / -Infinity → sentinel "— m" (em dash + m).
 *
 * - formatArea:
 *   - < 10_000 m² → "N m²" (Math.round)
 *   - >= 10_000 m² → "X.Y ha" (toFixed(1)), even for very large areas.
 *   - Argentine agricultural convention: hectares all the way up — no km²
 *     ladder. A consorcio of ~88_277 ha is expressed as "88277.0 ha", not
 *     "882.8 km²". Keeping a single unit above the m² threshold avoids
 *     unit-switching surprises in field workflows.
 *   - Negative → "0 m²"; NaN/Infinity → "— m²".
 *
 * Rounding mode: Math.round (IEEE 754 round-half-to-even is NOT required for
 * display; the few half-even edge cases do not affect spec tests).
 *
 * toFixed(1) keeps the trailing zero, so we get "1.0 km" instead of "1 km".
 * This is the spec — do not change to parseFloat().toString().
 */

import { describe, expect, it } from 'vitest';

import {
  formatArea,
  formatDistance,
} from '@/components/map2d/measurement/measurementFormat';

describe('measurementFormat', () => {
  describe('formatDistance', () => {
    it('formats 0 meters as "0 m"', () => {
      expect(formatDistance(0)).toBe('0 m');
    });

    it('formats 1 meter as "1 m"', () => {
      expect(formatDistance(1)).toBe('1 m');
    });

    it('formats 743 m as integer meters', () => {
      expect(formatDistance(743)).toBe('743 m');
    });

    it('rounds fractional meters to nearest integer below 1000', () => {
      expect(formatDistance(999.4)).toBe('999 m');
    });

    // Edge case: 999.9 is < 1000 BEFORE rounding, so it stays in meter branch.
    // Math.round(999.9) === 1000, so output is "1000 m". Documented — do not
    // "fix" by re-checking the threshold after rounding.
    it('keeps 999.9 in meter branch (rounds up to "1000 m")', () => {
      expect(formatDistance(999.9)).toBe('1000 m');
    });

    it('formats exactly 1000 m as "1.0 km" (km threshold)', () => {
      expect(formatDistance(1000)).toBe('1.0 km');
    });

    it('formats 1234 m as "1.2 km" (1 decimal for km)', () => {
      expect(formatDistance(1234)).toBe('1.2 km');
    });

    it('formats 8234 m as "8.2 km"', () => {
      expect(formatDistance(8234)).toBe('8.2 km');
    });

    it('formats 12345.6 m as "12.3 km"', () => {
      expect(formatDistance(12345.6)).toBe('12.3 km');
    });

    it('clamps negative input to 0 m (soft error)', () => {
      expect(formatDistance(-5)).toBe('0 m');
    });

    it('returns sentinel for NaN', () => {
      expect(formatDistance(Number.NaN)).toBe('— m');
    });

    it('returns sentinel for +Infinity', () => {
      expect(formatDistance(Number.POSITIVE_INFINITY)).toBe('— m');
    });

    it('returns sentinel for -Infinity', () => {
      expect(formatDistance(Number.NEGATIVE_INFINITY)).toBe('— m');
    });
  });

  describe('formatArea', () => {
    it('formats 0 m² as "0 m²"', () => {
      expect(formatArea(0)).toBe('0 m²');
    });

    it('formats 1 m² as "1 m²"', () => {
      expect(formatArea(1)).toBe('1 m²');
    });

    it('formats 500 m² as integer m²', () => {
      expect(formatArea(500)).toBe('500 m²');
    });

    it('formats 9999 m² as integer m² (just below ha threshold)', () => {
      expect(formatArea(9999)).toBe('9999 m²');
    });

    it('formats exactly 10000 m² as "1.0 ha" (ha threshold)', () => {
      expect(formatArea(10000)).toBe('1.0 ha');
    });

    it('formats 123456 m² as "12.3 ha"', () => {
      expect(formatArea(123456)).toBe('12.3 ha');
    });

    it('formats 9999999 m² as "1000.0 ha" (stays in ha branch)', () => {
      expect(formatArea(9999999)).toBe('1000.0 ha');
    });

    it('formats exactly 10000000 m² as "1000.0 ha" (no km² ladder)', () => {
      expect(formatArea(10000000)).toBe('1000.0 ha');
    });

    // Sanity check: consorcio area is ~88277 ha. Argentine convention keeps
    // hectares all the way up — we never switch to km². This locks the
    // real-world usage we care about.
    it('formats consorcio-scale area (88277 ha) as "88277.0 ha"', () => {
      expect(formatArea(88277 * 10000)).toBe('88277.0 ha');
    });

    it('clamps negative input to "0 m²" (soft error)', () => {
      expect(formatArea(-1)).toBe('0 m²');
    });

    it('returns sentinel for NaN', () => {
      expect(formatArea(Number.NaN)).toBe('— m²');
    });

    it('returns sentinel for +Infinity', () => {
      expect(formatArea(Number.POSITIVE_INFINITY)).toBe('— m²');
    });

    it('returns sentinel for -Infinity', () => {
      expect(formatArea(Number.NEGATIVE_INFINITY)).toBe('— m²');
    });
  });
});
