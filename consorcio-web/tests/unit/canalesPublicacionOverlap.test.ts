import { describe, expect, it } from 'vitest';

import { srPaFeatureId } from '../../src/lib/aprhiSrPa';
import {
  ADMIN_CANAL_LINE_LAYER_ID,
  CANAL_HIT_LAYER,
  OVERLAP_CLICK_PAD_PX,
  OVERLAP_OFFSET_PX,
  OVERLAY_DIM_OPACITY,
  clickBbox,
  collectCanalHits,
  kmzGroupVisible,
  overlayLabelsVisible,
  overlayLineOffsetPx,
  overlayLineOpacity,
  pickDefaultHit,
} from '../../src/lib/canalesPublicacionOverlap';

describe('kmzGroupVisible', () => {
  it('is on when either KMZ group is on', () => {
    expect(kmzGroupVisible(true, true)).toBe(true);
    expect(kmzGroupVisible(true, false)).toBe(true);
    expect(kmzGroupVisible(false, true)).toBe(true);
  });

  it('is off only when both groups are off', () => {
    expect(kmzGroupVisible(false, false)).toBe(false);
  });
});

describe('overlayLineOffsetPx', () => {
  it('keeps KMZ and idle overlays on the alignment', () => {
    expect(overlayLineOffsetPx(CANAL_HIT_LAYER.KMZ, true)).toBe(0);
    expect(overlayLineOffsetPx(CANAL_HIT_LAYER.SR_PA, false)).toBe(0);
    expect(overlayLineOffsetPx(CANAL_HIT_LAYER.EXISTENTES, false)).toBe(0);
  });

  it('pushes APRHI left and existentes right while KMZ is on', () => {
    expect(overlayLineOffsetPx(CANAL_HIT_LAYER.SR_PA, true)).toBe(-OVERLAP_OFFSET_PX);
    expect(overlayLineOffsetPx(CANAL_HIT_LAYER.EXISTENTES, true)).toBe(OVERLAP_OFFSET_PX);
  });
});

describe('overlayLineOpacity', () => {
  it('keeps the selected overlay at full opacity', () => {
    expect(overlayLineOpacity(true, true)).toBe(1);
    expect(overlayLineOpacity(false, true)).toBe(1);
  });

  it('dims unselected overlays only while KMZ is on', () => {
    expect(overlayLineOpacity(true, false)).toBe(OVERLAY_DIM_OPACITY);
    expect(overlayLineOpacity(false, false)).toBe(0.9);
  });
});

describe('overlayLabelsVisible', () => {
  it('shows overlay labels only when that overlay is on and KMZ is off', () => {
    expect(overlayLabelsVisible(true, false)).toBe(true);
    expect(overlayLabelsVisible(true, true)).toBe(false);
    expect(overlayLabelsVisible(false, false)).toBe(false);
    expect(overlayLabelsVisible(false, true)).toBe(false);
  });
});

describe('clickBbox', () => {
  it('builds a padded box around the click, defaulting to 8px', () => {
    expect(clickBbox({ x: 40, y: 20 })).toEqual([
      [40 - OVERLAP_CLICK_PAD_PX, 20 - OVERLAP_CLICK_PAD_PX],
      [40 + OVERLAP_CLICK_PAD_PX, 20 + OVERLAP_CLICK_PAD_PX],
    ]);
  });

  it('accepts a custom pad', () => {
    expect(clickBbox({ x: 10, y: 10 }, 5)).toEqual([
      [5, 5],
      [15, 15],
    ]);
  });
});

describe('collectCanalHits', () => {
  it('returns nothing for an empty query', () => {
    expect(collectCanalHits([])).toEqual([]);
  });

  it('skips unknown layers and KMZ/existentes without a string id', () => {
    expect(
      collectCanalHits([
        { layerId: 'satellite', properties: { id: 'nope' } },
        { layerId: ADMIN_CANAL_LINE_LAYER_ID.KMZ, properties: null },
        { layerId: ADMIN_CANAL_LINE_LAYER_ID.KMZ, properties: { id: 12 } },
        { layerId: ADMIN_CANAL_LINE_LAYER_ID.EXISTENTES, properties: { nombre_publico: 'Viejo' } },
      ])
    ).toEqual([]);
  });

  it('uses nombre_publico for KMZ and existentes, falling back to id', () => {
    expect(
      collectCanalHits([
        {
          layerId: ADMIN_CANAL_LINE_LAYER_ID.KMZ,
          properties: { id: 'canal-1', nombre_publico: 'Canal 10 de Mayo' },
        },
        {
          layerId: ADMIN_CANAL_LINE_LAYER_ID.EXISTENTES,
          properties: { id: 'aprhi-canal-viejo' },
        },
      ])
    ).toEqual([
      { id: 'canal-1', layer: CANAL_HIT_LAYER.KMZ, label: 'Canal 10 de Mayo' },
      { id: 'aprhi-canal-viejo', layer: CANAL_HIT_LAYER.EXISTENTES, label: 'aprhi-canal-viejo' },
    ]);
  });

  it('prefers list_id for SR PA and concatenates Identificador · Nombre_Obra', () => {
    expect(
      collectCanalHits([
        {
          layerId: ADMIN_CANAL_LINE_LAYER_ID.SR_PA,
          properties: {
            list_id: 'srpa:CA00140',
            Identificador: 'CA00140',
            Nombre_Obra: 'Tramo Nuevo - Canal San Marcos',
          },
        },
      ])
    ).toEqual([
      {
        id: 'srpa:CA00140',
        layer: CANAL_HIT_LAYER.SR_PA,
        label: 'CA00140 · Tramo Nuevo - Canal San Marcos',
      },
    ]);
  });

  it('falls back to srPaFeatureId and skips empty label parts', () => {
    const properties = { Identificador: 'CA00140', Nombre_Obra: '  ' };
    expect(collectCanalHits([{ layerId: ADMIN_CANAL_LINE_LAYER_ID.SR_PA, properties }])).toEqual([
      {
        id: srPaFeatureId(properties),
        layer: CANAL_HIT_LAYER.SR_PA,
        label: 'CA00140',
      },
    ]);
    expect(
      collectCanalHits([
        {
          layerId: ADMIN_CANAL_LINE_LAYER_ID.SR_PA,
          properties: { list_id: 'srpa:3513', Nombre_Obra: 'Canal Los Patos' },
        },
      ])
    ).toEqual([{ id: 'srpa:3513', layer: CANAL_HIT_LAYER.SR_PA, label: 'Canal Los Patos' }]);
  });

  it('uses the id as label when SR PA has no identificador or name', () => {
    expect(
      collectCanalHits([
        {
          layerId: ADMIN_CANAL_LINE_LAYER_ID.SR_PA,
          properties: { list_id: 'srpa:sin-id' },
        },
      ])
    ).toEqual([{ id: 'srpa:sin-id', layer: CANAL_HIT_LAYER.SR_PA, label: 'srpa:sin-id' }]);
  });

  it('dedups by id with first-seen winning (MapLibre z-order)', () => {
    expect(
      collectCanalHits([
        {
          layerId: ADMIN_CANAL_LINE_LAYER_ID.KMZ,
          properties: { id: 'canal-1', nombre_publico: 'Arriba' },
        },
        {
          layerId: ADMIN_CANAL_LINE_LAYER_ID.KMZ,
          properties: { id: 'canal-1', nombre_publico: 'Abajo' },
        },
        {
          layerId: ADMIN_CANAL_LINE_LAYER_ID.SR_PA,
          properties: { list_id: 'srpa:CA00140', Identificador: 'CA00140' },
        },
      ])
    ).toEqual([
      { id: 'canal-1', layer: CANAL_HIT_LAYER.KMZ, label: 'Arriba' },
      { id: 'srpa:CA00140', layer: CANAL_HIT_LAYER.SR_PA, label: 'CA00140' },
    ]);
  });
});

describe('pickDefaultHit', () => {
  it('returns null when there are no hits', () => {
    expect(pickDefaultHit([])).toBeNull();
  });

  it('prefers KMZ, then SR PA, then the first remaining hit', () => {
    const existentes = {
      id: 'aprhi-canal-viejo',
      layer: CANAL_HIT_LAYER.EXISTENTES,
      label: 'Canal Viejo',
    } as const;
    const srPa = {
      id: 'srpa:CA00140',
      layer: CANAL_HIT_LAYER.SR_PA,
      label: 'CA00140',
    } as const;
    const kmz = { id: 'canal-1', layer: CANAL_HIT_LAYER.KMZ, label: 'Canal 10 de Mayo' } as const;
    expect(pickDefaultHit([existentes, srPa, kmz])).toEqual(kmz);
    expect(pickDefaultHit([existentes, srPa])).toEqual(srPa);
    expect(pickDefaultHit([existentes])).toEqual(existentes);
  });
});
