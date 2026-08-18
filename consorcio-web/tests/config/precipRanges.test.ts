/**
 * precipRanges.test.ts
 *
 * Shared frontend contract (H2): the CHIRPS precip-normal rescale / legend
 * boundaries live in ONE module consumed by both the tile-rescale builder and the
 * legend ramp. These tests lock the annual 0–1800 mm and monthly 0–200 mm ranges
 * and the month→range mapping.
 */

import { describe, expect, it } from 'vitest';

import {
  PRECIP_ANNUAL_MAX_MM,
  PRECIP_MIN_MM,
  PRECIP_MONTHLY_MAX_MM,
  precipMaxForMonth,
  precipRangeForMonth,
} from '../../src/config/precipRanges';

describe('precipRanges — shared frontend contract (H2)', () => {
  it('exposes the canonical constants for the rescale / legend boundaries', () => {
    expect(PRECIP_MIN_MM).toBe(0);
    expect(PRECIP_ANNUAL_MAX_MM).toBe(1800);
    expect(PRECIP_MONTHLY_MAX_MM).toBe(200);
  });

  it('maps the annual aggregate to the 0–1800 mm range', () => {
    expect(precipMaxForMonth('anual')).toBe(PRECIP_ANNUAL_MAX_MM);
    expect(precipRangeForMonth('anual')).toEqual({
      min: PRECIP_MIN_MM,
      max: PRECIP_ANNUAL_MAX_MM,
    });
  });

  it('maps every monthly value (01–12) to the 0–200 mm range', () => {
    for (const m of [
      '01',
      '02',
      '03',
      '04',
      '05',
      '06',
      '07',
      '08',
      '09',
      '10',
      '11',
      '12',
    ]) {
      expect(precipMaxForMonth(m)).toBe(PRECIP_MONTHLY_MAX_MM);
      expect(precipRangeForMonth(m)).toEqual({
        min: PRECIP_MIN_MM,
        max: PRECIP_MONTHLY_MAX_MM,
      });
    }
  });

  it('treats any non-annual month string as monthly (preserves prior behavior)', () => {
    expect(precipMaxForMonth('')).toBe(PRECIP_MONTHLY_MAX_MM);
    expect(precipMaxForMonth('anual ')).toBe(PRECIP_MONTHLY_MAX_MM);
  });
});
