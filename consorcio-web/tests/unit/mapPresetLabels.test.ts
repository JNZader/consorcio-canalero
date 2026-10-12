import { describe, expect, it } from 'vitest';

import { MAP_PRESETS } from '../../src/components/map2d/mapPresets';

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
});
