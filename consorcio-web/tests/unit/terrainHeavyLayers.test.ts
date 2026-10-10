import { describe, expect, it } from 'vitest';

import {
  HEAVY_3D_WARNING,
  heavy3dLoadLines,
  heavy3dWarning,
} from '../../src/components/terrain/terrainHeavyLayers';

describe('heavy3dWarning', () => {
  it('is silent when only light layers are on', () => {
    expect(heavy3dWarning({ roads: true, waterways: true, catastro: false, soil: false })).toBeNull();
  });

  it('warns when catastro or soil is on', () => {
    expect(heavy3dWarning({ catastro: true })).toBe(HEAVY_3D_WARNING);
    expect(heavy3dWarning({ soil: true })).toBe(HEAVY_3D_WARNING);
  });
});

describe('heavy3dLoadLines', () => {
  it('reports catastro loading only when the layer is on', () => {
    expect(
      heavy3dLoadLines({
        catastroOn: true,
        catastroLoading: true,
        catastroError: null,
        soilOn: false,
        soilLoading: true,
        soilError: null,
      }),
    ).toEqual({ loading: ['Cargando catastro…'], errors: [] });
  });
});
