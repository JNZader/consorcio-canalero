import { describe, expect, it } from 'vitest';

import { formatLongitud, formatLongitudMeters } from '../../src/components/map2d/canalesFormat';

describe('canalesFormat', () => {
  it('formats meters with an es-AR thousands separator and m suffix', () => {
    expect(formatLongitudMeters(1355)).toBe('1.355 m');
    expect(formatLongitudMeters(0)).toBe('0 m');
  });

  it('omits the declared annotation when declared is null or omitted', () => {
    expect(formatLongitud(1355)).toBe('1.355 m');
    expect(formatLongitud(1355, null)).toBe('1.355 m');
    expect(formatLongitud(1355, undefined)).toBe('1.355 m');
  });

  it('appends declared meters only when they differ after rounding', () => {
    expect(formatLongitud(1355, 1500)).toBe('1.355 m · (1.500 m declarada)');
    expect(formatLongitud(1355.4, 1355)).toBe('1.355 m');
  });
});
