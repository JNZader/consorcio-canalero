/**
 * mapLayerSyncStoreCanales.test.ts
 *
 * Verifies the Pilar Azul additions to the mapLayerSyncStore:
 *   - `PILAR_AZUL_LAYER_IDS` master tuple (`canales_relevados`, `canales_propuestos`)
 *   - Defaults: relevados master ON, propuestos master OFF (per user decision)
 *   - `propuestasEtapasVisibility` slice defaulting to all-true for the 5 etapas
 *   - `setEtapaVisible(etapa, visible)` action toggles a single etapa
 *   - `registerPilarAzul(index)` bootstraps dynamic per-canal ids into each view
 *     with per-canal defaults = true (master gates visibility)
 *   - `getVisiblePropuestaIds()` selector applies the combined filter:
 *     per-canal visibility AND etapa filter
 *   - `isCanalVisible(id)` helper gates per-canal visibility on master toggle.
 *
 * The `persist` middleware is neutralised (same pattern as the Pilar Verde
 * suite) — we only care about the in-memory store shape, not the localStorage
 * round-trip here.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

vi.mock('zustand/middleware', async () => {
  const actual = await vi.importActual<typeof import('zustand/middleware')>(
    'zustand/middleware',
  );
  return {
    ...actual,
    persist: (fn: unknown) => fn,
  };
});

import {
  ALL_ETAPAS,
  type IndexFile,
} from '../../src/types/canales';
import {
  PILAR_AZUL_LAYER_IDS,
  PILAR_AZUL_DEFAULT_VISIBILITY,
  PROPUESTAS_ETAPAS_DEFAULTS,
  useMapLayerSyncStore,
} from '../../src/stores/mapLayerSyncStore';

const SAMPLE_INDEX: IndexFile = {
  schema_version: '1.0',
  generated_at: '2026-04-20T20:18:51Z',
  counts: { relevados: 2, propuestas: 3, total: 5 },
  relevados: [
    {
      id: 'canal-ne-sin-intervencion',
      nombre: 'Canal NE (sin intervención)',
      codigo: null,
      longitud_m: 8218.1,
      featured: false,
    },
    {
      id: 's1-canal-chico-este-san-marcos-sud-readecuacion',
      nombre: 'Canal chico este San Marcos Sud · readecuación',
      codigo: 'S1',
      longitud_m: 6054.1,
      featured: false,
    },
  ],
  propuestas: [
    {
      id: 'n3-tramo-faltante-de-interconexion',
      nombre: 'Tramo faltante de interconexión',
      codigo: 'N3',
      prioridad: 'Alta',
      longitud_m: 685.5,
      featured: true,
    },
    {
      id: 'n5-extension-zona-noroeste-primer-ramal',
      nombre: 'Extensión zona Noroeste primer ramal',
      codigo: 'N5',
      prioridad: 'Media-Alta',
      longitud_m: 2511.7,
      featured: false,
    },
    {
      id: 's2-complemento-opcional-p12-sujeto-a-presupuesto',
      nombre: 'S2 complemento opcional (P12) · sujeto a presupuesto',
      codigo: null,
      prioridad: null,
      longitud_m: 5914.8,
      featured: false,
    },
  ],
};

function resetToDefaults() {
  useMapLayerSyncStore.setState((s) => {
    // Strip any lingering canal_* per-canal keys from prior tests so each
    // test starts from the real defaults.
    const stripCanalKeys = (vv: Record<string, boolean>) => {
      const out: Record<string, boolean> = {};
      for (const [k, v] of Object.entries(vv)) {
        if (k.startsWith('canal_relevado_') || k.startsWith('canal_propuesto_')) continue;
        out[k] = v;
      }
      return out;
    };
    return {
      ...s,
      map2d: {
        activeRasterType: null,
        visibleVectors: {
          ...stripCanalKeys(s.map2d.visibleVectors),
          ...PILAR_AZUL_DEFAULT_VISIBILITY,
        },
      },
      map3d: {
        activeRasterType: null,
        visibleVectors: {
          ...stripCanalKeys(s.map3d.visibleVectors),
          ...PILAR_AZUL_DEFAULT_VISIBILITY,
        },
      },
      canalesPropuestasPrioridad: {},
      propuestasEtapasVisibility: { ...PROPUESTAS_ETAPAS_DEFAULTS },
    };
  });
}

describe('mapLayerSyncStore · Pilar Azul constants', () => {
  it('exposes the 2 master layer IDs in the expected order', () => {
    expect(PILAR_AZUL_LAYER_IDS).toEqual(['canales_relevados', 'canales_propuestos']);
  });

  it('default visibility: relevados ON, propuestos OFF', () => {
    expect(PILAR_AZUL_DEFAULT_VISIBILITY.canales_relevados).toBe(true);
    expect(PILAR_AZUL_DEFAULT_VISIBILITY.canales_propuestos).toBe(false);
  });

  it('PROPUESTAS_ETAPAS_DEFAULTS has all 5 etapas defaulting to true', () => {
    for (const etapa of ALL_ETAPAS) {
      expect(PROPUESTAS_ETAPAS_DEFAULTS[etapa]).toBe(true);
    }
  });
});

describe('mapLayerSyncStore · Pilar Azul defaults in store state', () => {
  beforeEach(() => resetToDefaults());

  it('map2d master toggles follow the spec defaults', () => {
    const { map2d } = useMapLayerSyncStore.getState();
    expect(map2d.visibleVectors.canales_relevados).toBe(true);
    expect(map2d.visibleVectors.canales_propuestos).toBe(false);
  });

  it('initial propuestasEtapasVisibility has all 5 etapas true', () => {
    const { propuestasEtapasVisibility } = useMapLayerSyncStore.getState();
    for (const etapa of ALL_ETAPAS) {
      expect(propuestasEtapasVisibility[etapa]).toBe(true);
    }
  });
});

describe('mapLayerSyncStore · setEtapaVisible action', () => {
  beforeEach(() => resetToDefaults());

  it('flips a single etapa to false and leaves the others untouched', () => {
    const { setEtapaVisible } = useMapLayerSyncStore.getState();
    setEtapaVisible('Alta', false);
    const state = useMapLayerSyncStore.getState().propuestasEtapasVisibility;
    expect(state.Alta).toBe(false);
    expect(state['Media-Alta']).toBe(true);
    expect(state.Media).toBe(true);
    expect(state.Opcional).toBe(true);
    expect(state['Largo plazo']).toBe(true);
  });

  it('round-trip: flip off then on restores the etapa', () => {
    const { setEtapaVisible } = useMapLayerSyncStore.getState();
    setEtapaVisible('Media', false);
    expect(useMapLayerSyncStore.getState().propuestasEtapasVisibility.Media).toBe(false);
    setEtapaVisible('Media', true);
    expect(useMapLayerSyncStore.getState().propuestasEtapasVisibility.Media).toBe(true);
  });
});

describe('mapLayerSyncStore · registerPilarAzul', () => {
  beforeEach(() => resetToDefaults());

  it('bootstraps all 5 per-canal ids into each view with default true', () => {
    const { registerPilarAzul } = useMapLayerSyncStore.getState();
    registerPilarAzul(SAMPLE_INDEX);

    const state = useMapLayerSyncStore.getState();
    // 2 relevados
    expect(state.map2d.visibleVectors.canal_relevado_canal_ne_sin_intervencion).toBe(true);
    expect(
      state.map2d.visibleVectors.canal_relevado_s1_canal_chico_este_san_marcos_sud_readecuacion,
    ).toBe(true);
    // 3 propuestas
    expect(
      state.map2d.visibleVectors.canal_propuesto_n3_tramo_faltante_de_interconexion,
    ).toBe(true);
    expect(
      state.map2d.visibleVectors.canal_propuesto_n5_extension_zona_noroeste_primer_ramal,
    ).toBe(true);
    expect(
      state.map2d.visibleVectors
        .canal_propuesto_s2_complemento_opcional_p12_sujeto_a_presupuesto,
    ).toBe(true);

    // Same keys also present on map3d (both views track canales)
    expect(state.map3d.visibleVectors.canal_relevado_canal_ne_sin_intervencion).toBe(true);
  });

  it('masters untouched — relevados stays true, propuestos stays false', () => {
    const { registerPilarAzul } = useMapLayerSyncStore.getState();
    registerPilarAzul(SAMPLE_INDEX);
    const state = useMapLayerSyncStore.getState();
    expect(state.map2d.visibleVectors.canales_relevados).toBe(true);
    expect(state.map2d.visibleVectors.canales_propuestos).toBe(false);
  });

  it('is idempotent — a second registerPilarAzul preserves user-set per-canal values', () => {
    const { registerPilarAzul, setVectorVisibility } = useMapLayerSyncStore.getState();
    registerPilarAzul(SAMPLE_INDEX);
    // User flips a per-canal OFF
    setVectorVisibility(
      'map2d',
      'canal_propuesto_n3_tramo_faltante_de_interconexion',
      false,
    );
    // Re-register (e.g. fresh page mount) MUST NOT clobber the user's choice.
    registerPilarAzul(SAMPLE_INDEX);

    expect(
      useMapLayerSyncStore.getState().map2d.visibleVectors
        .canal_propuesto_n3_tramo_faltante_de_interconexion,
    ).toBe(false);
    // Unmodified peers stay true
    expect(
      useMapLayerSyncStore.getState().map2d.visibleVectors
        .canal_propuesto_n5_extension_zona_noroeste_primer_ramal,
    ).toBe(true);
  });
});

describe('mapLayerSyncStore · selectors', () => {
  beforeEach(() => resetToDefaults());

  it('getVisiblePropuestaIds returns all ids when master ON and all etapas ON', () => {
    const { registerPilarAzul } = useMapLayerSyncStore.getState();
    registerPilarAzul(SAMPLE_INDEX);
    // Flip propuestos master ON (default is OFF)
    useMapLayerSyncStore.getState().setVectorVisibility(
      'map2d',
      'canales_propuestos',
      true,
    );
    const ids = useMapLayerSyncStore.getState().getVisiblePropuestaIds('map2d');
    expect(ids).toEqual(
      expect.arrayContaining([
        'n3-tramo-faltante-de-interconexion',
        'n5-extension-zona-noroeste-primer-ramal',
        's2-complemento-opcional-p12-sujeto-a-presupuesto',
      ]),
    );
    expect(ids).toHaveLength(3);
  });

  it('getVisiblePropuestaIds: an etapa filter removes matching canales', () => {
    const { registerPilarAzul, setVectorVisibility, setEtapaVisible } =
      useMapLayerSyncStore.getState();
    registerPilarAzul(SAMPLE_INDEX);
    setVectorVisibility('map2d', 'canales_propuestos', true);

    // Hide "Alta" — the N3 propuesto drops out. N5 (Media-Alta) stays.
    // The null-prioridad P12 stays (v1 always-visible policy for null etapa).
    setEtapaVisible('Alta', false);

    const ids = useMapLayerSyncStore.getState().getVisiblePropuestaIds('map2d');
    expect(ids).not.toContain('n3-tramo-faltante-de-interconexion');
    expect(ids).toContain('n5-extension-zona-noroeste-primer-ramal');
    expect(ids).toContain('s2-complemento-opcional-p12-sujeto-a-presupuesto');
    expect(ids).toHaveLength(2);
  });

  it('getVisiblePropuestaIds: a per-canal flip OFF removes that one id', () => {
    const { registerPilarAzul, setVectorVisibility } = useMapLayerSyncStore.getState();
    registerPilarAzul(SAMPLE_INDEX);
    setVectorVisibility('map2d', 'canales_propuestos', true);
    setVectorVisibility(
      'map2d',
      'canal_propuesto_n5_extension_zona_noroeste_primer_ramal',
      false,
    );

    const ids = useMapLayerSyncStore.getState().getVisiblePropuestaIds('map2d');
    expect(ids).not.toContain('n5-extension-zona-noroeste-primer-ramal');
    expect(ids).toContain('n3-tramo-faltante-de-interconexion');
    expect(ids).toContain('s2-complemento-opcional-p12-sujeto-a-presupuesto');
    expect(ids).toHaveLength(2);
  });

  it('isCanalVisible: master OFF hides every relevant per-canal', () => {
    const { registerPilarAzul, setVectorVisibility } = useMapLayerSyncStore.getState();
    registerPilarAzul(SAMPLE_INDEX);
    // propuestos master stays OFF by default; per-canal state remains true.
    // Even though the per-canal is true, the master gate wins.
    const isVisible = useMapLayerSyncStore
      .getState()
      .isCanalVisible('map2d', 'canal_propuesto_n3_tramo_faltante_de_interconexion');
    expect(isVisible).toBe(false);

    // Relevados master ON by default → its per-canals are visible.
    const relVisible = useMapLayerSyncStore
      .getState()
      .isCanalVisible('map2d', 'canal_relevado_canal_ne_sin_intervencion');
    expect(relVisible).toBe(true);

    // Flip propuestos master ON → the per-canal becomes visible.
    setVectorVisibility('map2d', 'canales_propuestos', true);
    const afterFlip = useMapLayerSyncStore
      .getState()
      .isCanalVisible('map2d', 'canal_propuesto_n3_tramo_faltante_de_interconexion');
    expect(afterFlip).toBe(true);
  });
});
