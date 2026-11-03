import { describe, expect, it } from 'vitest';

import { pairedSurveys, soleraCover } from '../../src/components/map2d/soleraProfile';

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
});
