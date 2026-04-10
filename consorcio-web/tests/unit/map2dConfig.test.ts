import { describe, expect, it } from 'vitest';

import { WATERWAY_DEFS } from '../../src/hooks/useWaterways';
import { GEE_LAYER_NAMES, SOURCE_IDS, buildWaterwayLayerConfigs } from '../../src/components/map2d/map2dConfig';

describe('map2dConfig', () => {
  it('exports stable source ids used by the 2D map', () => {
    expect(SOURCE_IDS.WATERWAYS).toBe('map2d-waterways');
    expect(SOURCE_IDS.IGN).toBe('map2d-ign-overlay');
    expect(SOURCE_IDS.PUBLIC_LAYERS_PREFIX).toBe('map2d-public-');
  });

  it('exports the supported 2D GEE layer names', () => {
    expect(GEE_LAYER_NAMES).toEqual(['zona']);
  });

  it('builds waterway layer configs in the intended rendering order', () => {
    const configs = buildWaterwayLayerConfigs(WATERWAY_DEFS);

    expect(configs).toHaveLength(6);
    expect(configs[0]).toMatchObject({
      id: `${SOURCE_IDS.WATERWAYS}-rio-tercero`,
      layer: 'rio_tercero',
      url: 'pmtiles:///waterways/rio_tercero.pmtiles',
    });
    expect(configs.at(-1)).toMatchObject({
      id: `${SOURCE_IDS.WATERWAYS}-canales-existentes`,
      layer: 'canales_existentes',
      url: 'pmtiles:///waterways/canales_existentes.pmtiles',
    });
  });

  it('prefers shared waterway colors and falls back when a definition is missing', () => {
    const fromDefs = buildWaterwayLayerConfigs(WATERWAY_DEFS);
    const existingFromDefs = fromDefs.find((item) => item.layer === 'canales_existentes');
    expect(existingFromDefs?.color).toBe(
      WATERWAY_DEFS.find((item) => item.id === 'canales_existentes')?.style.color
    );

    const fallbackOnly = buildWaterwayLayerConfigs([] as typeof WATERWAY_DEFS);
    const existingFallback = fallbackOnly.find((item) => item.layer === 'canales_existentes');
    expect(existingFallback?.color).toBe('#0B3D91');
  });
});
