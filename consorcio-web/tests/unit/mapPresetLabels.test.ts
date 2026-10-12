import { describe, expect, it } from 'vitest';

import { MAP_PRESETS, pickPresetRasterId } from '../../src/components/map2d/mapPresets';

describe('MAP_PRESETS labels (UX-26)', () => {
  it('uses task names, not family names', () => {
    const labels = MAP_PRESETS.map((preset) => preset.label);
    expect(labels).toEqual([
      'Dónde hay agua',
      'Obras de canales',
      'Red vial',
      'BPA y bosque',
      'Parcelas y suelos',
    ]);
    expect(labels).not.toContain('Agua');
    expect(labels).not.toContain('Pilar Verde');
    expect(labels).not.toContain('Catastro');
  });

  it('picks a water-ish raster for the agua vista (UX-04)', () => {
    expect(
      pickPresetRasterId('agua', [
        { value: 'slope', label: 'Pendiente' },
        { value: 'flood', label: 'Riesgo de inundación' },
      ])
    ).toBe('flood');
    expect(pickPresetRasterId('agua', [{ value: 'dem-1', label: 'Elevación' }])).toBe('dem-1');
    expect(
      pickPresetRasterId('canales', [{ value: 'flood', label: 'Riesgo de inundación' }])
    ).toBeNull();
  });
});
