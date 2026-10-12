import { describe, expect, it } from 'vitest';

import {
  KNOWN_RASTER_TIPOS,
  mergeRasterSearchOptions,
} from '../../src/components/map2d/knownRasterCatalog';

describe('knownRasterCatalog (UX-12)', () => {
  it('falls back to the known catalog when DEM options are empty', () => {
    const options = mergeRasterSearchOptions([], 'hand');
    expect(options.some((option) => option.label.includes('HAND'))).toBe(true);
    expect(options.every((option) => option.available === false)).toBe(true);
    expect(KNOWN_RASTER_TIPOS).toContain('hand');
  });

  it('prefers live DEM options when the catalog loaded', () => {
    const options = mergeRasterSearchOptions([{ value: 'id-1', label: 'Pendiente' }], '');
    expect(options).toEqual([{ value: 'id-1', label: 'Pendiente', available: true }]);
  });
});
