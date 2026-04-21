/**
 * kmzLayerRegistry.test.ts
 *
 * Batch B — Phase 1 [RED] for change `kmz-export-all-layers`.
 *
 * Pins the KMZ export allowlist/denylist and the per-layer color contract.
 *
 * Key invariants:
 *   - Registry has EXACTLY 13 entries.
 *   - Excluded keys (`puntos_conflicto`, `approved_zones`, `basins`) are NEVER
 *     present — the export mustn't leak heavy/MVT or draft-only layers.
 *   - Each entry's `color` must come from the same source-of-truth constant
 *     the MapLibre paint uses. If a layer's color isn't exported as a named
 *     constant (escuelas circle, roads line, catastro fill), the registry
 *     hardcodes it with an inline comment linking back to the paint file
 *     and this test pins the literal hex.
 *   - Key names match the store's `defaultVisibleVectors` (Pilar Verde keys
 *     use the `*_historico` / `*_aceptada` / `*_presentada` / `*_agro_zonas`
 *     / `*_porcentaje_forestacion` forms, NOT the proposal shorthand). The
 *     `ypf-estacion-bombeo` key matches `YPF_ESTACION_BOMBEO_SOURCE_ID`
 *     (always-on layer — no visibility toggle in the store).
 */

import { describe, expect, it } from 'vitest';

import {
  KMZ_EXCLUDED_LAYER_KEYS,
  KMZ_LAYER_REGISTRY,
  type KmzLayerEntry,
  type KmzLayerGeometry,
} from '../../src/lib/kmzExport/kmzLayerRegistry';
import { CANALES_COLORS } from '../../src/components/map2d/canalesLayers';
import { PILAR_VERDE_COLORS } from '../../src/components/map2d/pilarVerdeLayers';
import {
  YPF_ESTACION_BOMBEO_COLOR,
  YPF_ESTACION_BOMBEO_LABEL,
} from '../../src/components/map2d/ypfEstacionBombeoLayer';
import { WATERWAY_DEFS } from '../../src/hooks/useWaterways';
import { SOIL_CAPABILITY_COLORS } from '../../src/hooks/useSoilMap';

// ---------------------------------------------------------------------------
// Expected canonical key set (ground truth = store + MapLibre source ids).
// ---------------------------------------------------------------------------

const EXPECTED_KEYS = [
  'canales_relevados',
  'canales_propuestos',
  'escuelas',
  'pilar_verde_bpa_historico',
  'pilar_verde_agro_aceptada',
  'pilar_verde_agro_presentada',
  'pilar_verde_agro_zonas',
  'pilar_verde_porcentaje_forestacion',
  'waterways',
  'roads',
  'catastro',
  'soil',
  'ypf-estacion-bombeo',
] as const;

const EXPECTED_EXCLUDED = ['puntos_conflicto', 'approved_zones', 'basins'] as const;

const LINE_KEYS = new Set<string>([
  'canales_relevados',
  'canales_propuestos',
  'waterways',
  'roads',
]);

const POLYGON_KEYS = new Set<string>([
  'pilar_verde_bpa_historico',
  'pilar_verde_agro_aceptada',
  'pilar_verde_agro_presentada',
  'pilar_verde_agro_zonas',
  'pilar_verde_porcentaje_forestacion',
  'catastro',
  'soil',
]);

const POINT_KEYS = new Set<string>(['escuelas', 'ypf-estacion-bombeo']);

function findEntry(key: string): KmzLayerEntry | undefined {
  return KMZ_LAYER_REGISTRY.find((entry) => entry.key === key);
}

// ---------------------------------------------------------------------------
// Registry shape
// ---------------------------------------------------------------------------

describe('KMZ_LAYER_REGISTRY · shape', () => {
  it('exports exactly 13 entries', () => {
    expect(KMZ_LAYER_REGISTRY).toHaveLength(13);
  });

  it('every entry has { key, label, geometryHint, color } with correct types', () => {
    const validGeometries: KmzLayerGeometry[] = ['point', 'line', 'polygon'];
    for (const entry of KMZ_LAYER_REGISTRY) {
      expect(typeof entry.key).toBe('string');
      expect(entry.key.length).toBeGreaterThan(0);
      expect(typeof entry.label).toBe('string');
      expect(entry.label.length).toBeGreaterThan(0);
      expect(validGeometries).toContain(entry.geometryHint);
      expect(typeof entry.color).toBe('string');
      expect(entry.color).toMatch(/^#[0-9a-fA-F]{6}$/);
      if (entry.strokeColor !== undefined) {
        expect(entry.strokeColor).toMatch(/^#[0-9a-fA-F]{6}$/);
      }
    }
  });

  it('keys are unique (no duplicates)', () => {
    const keys = KMZ_LAYER_REGISTRY.map((entry) => entry.key);
    expect(new Set(keys).size).toBe(keys.length);
  });
});

// ---------------------------------------------------------------------------
// Key allowlist
// ---------------------------------------------------------------------------

describe('KMZ_LAYER_REGISTRY · allowlist', () => {
  it('includes all 13 expected keys (store-canonical names)', () => {
    const registryKeys = new Set(KMZ_LAYER_REGISTRY.map((e) => e.key));
    for (const key of EXPECTED_KEYS) {
      expect(registryKeys.has(key)).toBe(true);
    }
  });

  it('contains NO keys outside the expected allowlist', () => {
    const allowed = new Set<string>(EXPECTED_KEYS);
    for (const entry of KMZ_LAYER_REGISTRY) {
      expect(allowed.has(entry.key)).toBe(true);
    }
  });
});

// ---------------------------------------------------------------------------
// Exclusion list
// ---------------------------------------------------------------------------

describe('KMZ_EXCLUDED_LAYER_KEYS · denylist invariant', () => {
  it('is a readonly tuple of exactly the 3 excluded keys', () => {
    expect(KMZ_EXCLUDED_LAYER_KEYS).toEqual(EXPECTED_EXCLUDED);
    expect(KMZ_EXCLUDED_LAYER_KEYS).toHaveLength(3);
  });

  it('registry contains NONE of the excluded keys', () => {
    KMZ_LAYER_REGISTRY.forEach((entry) => {
      expect(KMZ_EXCLUDED_LAYER_KEYS).not.toContain(entry.key);
    });
  });
});

// ---------------------------------------------------------------------------
// Color source-of-truth wiring
// ---------------------------------------------------------------------------

describe('KMZ_LAYER_REGISTRY · color source-of-truth', () => {
  it('canales_relevados uses CANALES_COLORS.relevadoSinObra (blue-700 primary)', () => {
    expect(findEntry('canales_relevados')?.color).toBe(CANALES_COLORS.relevadoSinObra);
  });

  it('canales_propuestos uses CANALES_COLORS.propuestoAlta (red-600 — highest-priority representative)', () => {
    expect(findEntry('canales_propuestos')?.color).toBe(CANALES_COLORS.propuestoAlta);
  });

  it('escuelas mirrors the MapLibre circle-color #1976d2 (NOT exported from escuelasLayers.ts — hardcoded with a comment in the registry)', () => {
    expect(findEntry('escuelas')?.color).toBe('#1976d2');
  });

  it('ypf-estacion-bombeo uses the exported YPF_ESTACION_BOMBEO_COLOR', () => {
    expect(findEntry('ypf-estacion-bombeo')?.color).toBe(YPF_ESTACION_BOMBEO_COLOR);
  });

  it('ypf-estacion-bombeo label matches YPF_ESTACION_BOMBEO_LABEL', () => {
    expect(findEntry('ypf-estacion-bombeo')?.label).toBe(YPF_ESTACION_BOMBEO_LABEL);
  });

  it('pilar_verde_bpa_historico uses the middle BPA gradient stop (bpaHistoricoStop5, green-600)', () => {
    expect(findEntry('pilar_verde_bpa_historico')?.color).toBe(
      PILAR_VERDE_COLORS.bpaHistoricoStop5,
    );
  });

  it('pilar_verde_agro_aceptada uses PILAR_VERDE_COLORS.agroAceptadaFill', () => {
    expect(findEntry('pilar_verde_agro_aceptada')?.color).toBe(
      PILAR_VERDE_COLORS.agroAceptadaFill,
    );
  });

  it('pilar_verde_agro_presentada uses PILAR_VERDE_COLORS.agroPresentadaFill', () => {
    expect(findEntry('pilar_verde_agro_presentada')?.color).toBe(
      PILAR_VERDE_COLORS.agroPresentadaFill,
    );
  });

  it('pilar_verde_agro_zonas uses PILAR_VERDE_COLORS.agroZonasFill (fallback/anchor)', () => {
    expect(findEntry('pilar_verde_agro_zonas')?.color).toBe(
      PILAR_VERDE_COLORS.agroZonasFill,
    );
  });

  it('pilar_verde_porcentaje_forestacion uses the middle-tier porcentajeForestacionMedia (violet-500)', () => {
    expect(findEntry('pilar_verde_porcentaje_forestacion')?.color).toBe(
      PILAR_VERDE_COLORS.porcentajeForestacionMedia,
    );
  });

  it('waterways uses the Río Tercero primary waterway color from WATERWAY_DEFS', () => {
    const rioTercero = WATERWAY_DEFS.find((def) => def.id === 'rio_tercero');
    expect(rioTercero).toBeDefined();
    expect(findEntry('waterways')?.color).toBe(rioTercero?.style.color);
  });

  it('roads mirrors the MapLibre road line-color #FFEB3B (coalesce fallback — not exported)', () => {
    // See `mapLayerEffectHelpers.ts::syncRoadLayers` for the paint source.
    expect(findEntry('roads')?.color).toBe('#FFEB3B');
  });

  it('catastro mirrors the MapLibre catastro fill-color #8d6e63 and stroke #FFFFFF (not exported)', () => {
    // See `mapLayerEffectHelpers.ts::syncCatastroLayers` for the paint source.
    const entry = findEntry('catastro');
    expect(entry?.color).toBe('#8d6e63');
    expect(entry?.strokeColor).toBe('#FFFFFF');
  });

  it('soil uses SOIL_CAPABILITY_COLORS.IV as the representative middle of the 8-class palette', () => {
    expect(findEntry('soil')?.color).toBe(SOIL_CAPABILITY_COLORS.IV);
  });
});

// ---------------------------------------------------------------------------
// Geometry hint dispatch (for Phase 2 styles)
// ---------------------------------------------------------------------------

describe('KMZ_LAYER_REGISTRY · geometryHint', () => {
  it('line layers are tagged geometryHint="line"', () => {
    for (const key of LINE_KEYS) {
      expect(findEntry(key)?.geometryHint).toBe('line');
    }
  });

  it('polygon layers are tagged geometryHint="polygon"', () => {
    for (const key of POLYGON_KEYS) {
      expect(findEntry(key)?.geometryHint).toBe('polygon');
    }
  });

  it('point layers are tagged geometryHint="point"', () => {
    for (const key of POINT_KEYS) {
      expect(findEntry(key)?.geometryHint).toBe('point');
    }
  });
});

// ---------------------------------------------------------------------------
// Label wiring (spot-check for the store-facing labels)
// ---------------------------------------------------------------------------

describe('KMZ_LAYER_REGISTRY · labels (spot-check vs. map2dDerived.buildVectorLayerItems)', () => {
  it('matches the human-readable labels used by the layer controls panel', () => {
    const expected: Record<string, string> = {
      canales_relevados: 'Canales relevados',
      canales_propuestos: 'Canales propuestos',
      escuelas: 'Escuelas rurales',
      pilar_verde_bpa_historico: 'BPA histórico (por años)',
      pilar_verde_agro_aceptada: 'Agroforestal: Cumplen',
      pilar_verde_agro_presentada: 'Agroforestal: Presentaron',
      pilar_verde_agro_zonas: 'Zonas Agroforestales',
      pilar_verde_porcentaje_forestacion: '% Forestación obligatoria',
      waterways: 'Hidrografía',
      roads: 'Red vial',
      catastro: 'Catastro rural',
      soil: 'Suelos IDECOR',
      'ypf-estacion-bombeo': YPF_ESTACION_BOMBEO_LABEL,
    };
    for (const [key, label] of Object.entries(expected)) {
      expect(findEntry(key)?.label).toBe(label);
    }
  });
});
