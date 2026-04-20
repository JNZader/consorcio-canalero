/**
 * fmt.test.ts
 *
 * RED/GREEN tests for the Pilar Verde widget's locale-aware number formatter.
 *
 * The helper (`src/components/admin/pilarVerdeWidget/fmt.ts`) MUST:
 *   - Use es-AR locale (thousand separator "." and decimal ",")
 *   - Keep up to ONE decimal place (matches how `aggregates.json` numbers are
 *     already rounded — see ETL `compute_*` helpers)
 *   - Emit integer-looking output when the number has no meaningful decimals
 *   - Return an em dash ("—") for `null` / `undefined` / `NaN` (NOT a zero)
 *   - Preserve zero as a valid value (0 → "0 ha")
 *   - Append unit with a single space, except "%" which concatenates directly
 *
 * Pinning the locale explicitly here prevents a test-host locale override from
 * changing the expected output.
 */

import { describe, expect, it } from 'vitest';

import { fmt } from '../../src/components/admin/pilarVerdeWidget/fmt';

describe('fmt()', () => {
  it('formats decimal hectares with the es-AR thousand/decimal separators', () => {
    expect(fmt(1234.56, 'ha')).toBe('1.234,6 ha');
  });

  it('formats integer hectares without decimals when none are present', () => {
    expect(fmt(88307, 'ha')).toBe('88.307 ha');
  });

  it('appends "%" directly with no space', () => {
    expect(fmt(33.0, '%')).toBe('33,0%');
  });

  it('keeps exactly one decimal on a tenths value', () => {
    expect(fmt(43.5, '%')).toBe('43,5%');
  });

  it('returns the em dash sentinel for null', () => {
    expect(fmt(null)).toBe('—');
  });

  it('returns the em dash sentinel for undefined', () => {
    expect(fmt(undefined)).toBe('—');
  });

  it('returns the em dash sentinel for NaN', () => {
    expect(fmt(Number.NaN)).toBe('—');
  });

  it('treats zero as a valid value (not null)', () => {
    expect(fmt(0, 'ha')).toBe('0 ha');
  });

  it('formats without unit when none is supplied', () => {
    expect(fmt(1234)).toBe('1.234');
  });

  it('never falls back to em dash for negative numbers', () => {
    expect(fmt(-50, 'ha')).toBe('-50 ha');
  });
});
