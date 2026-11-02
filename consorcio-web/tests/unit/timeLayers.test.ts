import { describe, expect, it } from 'vitest';

import { yearOptions } from '../../src/lib/api/timeLayers';

describe('yearOptions', () => {
  it('lists Sentinel-2 from the current year down to 2017', () => {
    const years = yearOptions('s2', new Date('2026-11-02T00:00:00Z'));
    expect(years[0]).toBe(2026);
    expect(years.at(-1)).toBe(2017);
    expect(years).toContain(2018);
    expect(years).not.toContain(2016);
  });

  it('lists JRC yearly history from 2021 down to 1984', () => {
    const years = yearOptions('jrc', new Date('2026-11-02T00:00:00Z'));
    expect(years[0]).toBe(2021);
    expect(years.at(-1)).toBe(1984);
    expect(years).not.toContain(2022);
    expect(years).not.toContain(1983);
  });
});
