import { describe, expect, it } from 'vitest';

import { WATERWAY_DEFS } from '../../src/hooks/useWaterways';
import { GEE_LAYER_NAMES, SOURCE_IDS, buildWaterwayLayerConfigs } from '../../src/components/map2d/map2dConfig';

describe('map2dConfig', () => {
  it('exports stable source ids used by the 2D map', () => {
    expect(SOURCE_IDS.WATERWAYS).toBe('map2d-waterways');
    expect(SOURCE_IDS.IGN).toBe('map2d-ign-overlay');
  });

  it('exports the supported 2D GEE layer names', () => {
    expect(GEE_LAYER_NAMES).toEqual(['zona']);
  });

  // Batch 5 (2026-04-20): the legacy `canales_existentes` waterway was
  // retired — Pilar Azul's `useCanales` replaced it. The waterway stack now
  // contains 5 entries (Río Tercero + canal desviador + Litín-Tortugas +
  // arroyo Algodón + arroyo Las Mojarras).
  it('builds waterway layer configs for the 5 remaining waterways in declared order', () => {
    const configs = buildWaterwayLayerConfigs(WATERWAY_DEFS);

    expect(configs).toHaveLength(5);
    expect(configs[0]).toMatchObject({
      id: `${SOURCE_IDS.WATERWAYS}-rio-tercero`,
      layer: 'rio_tercero',
      url: '/waterways/rio_tercero.geojson',
    });
    expect(configs.at(-1)).toMatchObject({
      id: `${SOURCE_IDS.WATERWAYS}-arroyo-mojarras`,
      layer: 'arroyo_las_mojarras',
      url: '/waterways/arroyo_las_mojarras.geojson',
    });
  });

  it('prefers shared waterway colors and falls back when a definition is missing', () => {
    const fromDefs = buildWaterwayLayerConfigs(WATERWAY_DEFS);
    const rio = fromDefs.find((item) => item.layer === 'rio_tercero');
    expect(rio?.color).toBe(
      WATERWAY_DEFS.find((item) => item.id === 'rio_tercero')?.style.color,
    );

    const fallbackOnly = buildWaterwayLayerConfigs([] as unknown as typeof WATERWAY_DEFS);
    const rioFallback = fallbackOnly.find((item) => item.layer === 'rio_tercero');
    expect(rioFallback?.color).toBe('#1565C0');
  });

  it('waterway layer configs do NOT include the retired canales_existentes', () => {
    const configs = buildWaterwayLayerConfigs(WATERWAY_DEFS);
    const layers = configs.map((c) => c.layer);
    expect(layers).not.toContain('canales_existentes');
  });
});
