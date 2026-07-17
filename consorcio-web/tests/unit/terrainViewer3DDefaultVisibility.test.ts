/**
 * terrainViewer3DDefaultVisibility.test.ts
 *
 * Phase 0 (Batch A) of `pilar-verde-y-canales-3d` — 3D terrain defaults.
 *
 * The 3D `TERRAIN_DEFAULT_VECTOR_LAYER_VISIBILITY` derives BOTH its layer ids
 * and its values from `mapLayerSyncStore`'s unified map3d defaults (acb1d23):
 * the store is the single source of truth for startup visibility; the
 * constant only adds shape/fallback keys, excludes `zona` and forces
 * `cuencas` off in 3D.
 *
 * Companion to Task 0.5 (smoke test for the `mapLayerSyncStore.map3d` slice
 * shape) — both share this single suite to avoid spinning up two near-empty
 * files for closely-related read-only assertions.
 */

import { describe, expect, it } from 'vitest';

import { PRIORITY_3D_VECTOR_LAYERS } from '../../src/components/terrain/terrainLayerConfig';
import {
  buildClickableLayers3D,
  TERRAIN_DEFAULT_VECTOR_LAYER_VISIBILITY,
} from '../../src/components/terrain/terrainViewer3DUtils';
import {
  PILAR_AZUL_DEFAULT_VISIBILITY,
  PILAR_AZUL_LAYER_IDS,
  PILAR_VERDE_DEFAULT_VISIBILITY,
  PILAR_VERDE_LAYER_IDS,
  useMapLayerSyncStore,
} from '../../src/stores/mapLayerSyncStore';

describe('TERRAIN_DEFAULT_VECTOR_LAYER_VISIBILITY', () => {
  it('mirrors every Pilar Verde default from the shared store constant', () => {
    for (const layerId of PILAR_VERDE_LAYER_IDS) {
      expect(TERRAIN_DEFAULT_VECTOR_LAYER_VISIBILITY).toHaveProperty(layerId);
      expect(TERRAIN_DEFAULT_VECTOR_LAYER_VISIBILITY[layerId]).toBe(
        PILAR_VERDE_DEFAULT_VISIBILITY[layerId],
      );
    }
  });

  it('contains every Pilar Azul (Canales) master key from the shared store constant', () => {
    for (const layerId of PILAR_AZUL_LAYER_IDS) {
      expect(TERRAIN_DEFAULT_VECTOR_LAYER_VISIBILITY).toHaveProperty(layerId);
    }
  });

  it('mirrors the unified map3d store defaults (acb1d23 — no divergent copy)', () => {
    // Single source of truth: the constant derives from
    // MAP3D_DEFAULT_VISIBLE_VECTORS, so every store-tracked key must match
    // (except `zona`, excluded in 3D, and `cuencas`, forced off in 3D).
    const storeDefaults = useMapLayerSyncStore.getState().map3d.visibleVectors;
    for (const [key, value] of Object.entries(storeDefaults)) {
      if (key === 'zona' || key === 'cuencas') continue;
      expect(TERRAIN_DEFAULT_VECTOR_LAYER_VISIBILITY[key], key).toBe(value);
    }
    // Spot-checks of the unified policy: core context layers start VISIBLE.
    expect(PILAR_AZUL_DEFAULT_VISIBILITY.canales_relevados).toBe(true);
    expect(TERRAIN_DEFAULT_VECTOR_LAYER_VISIBILITY.canales_relevados).toBe(true);
    expect(TERRAIN_DEFAULT_VECTOR_LAYER_VISIBILITY.roads).toBe(true);
    expect(TERRAIN_DEFAULT_VECTOR_LAYER_VISIBILITY.waterways).toBe(true);
    expect(TERRAIN_DEFAULT_VECTOR_LAYER_VISIBILITY.canales_propuestos).toBe(false);
    expect(TERRAIN_DEFAULT_VECTOR_LAYER_VISIBILITY.pilar_verde_bpa_historico).toBe(false);
  });

  it('preserves the existing terrain base defaults', () => {
    // Sanity: keys not tracked by the store keep their fallback, and the
    // 3D-specific overrides hold.
    expect(TERRAIN_DEFAULT_VECTOR_LAYER_VISIBILITY.approved_zones).toBe(false);
    expect(TERRAIN_DEFAULT_VECTOR_LAYER_VISIBILITY.cuencas).toBe(false);
    expect(TERRAIN_DEFAULT_VECTOR_LAYER_VISIBILITY.basins).toBe(false);
    expect(TERRAIN_DEFAULT_VECTOR_LAYER_VISIBILITY.soil).toBe(false);
    expect(TERRAIN_DEFAULT_VECTOR_LAYER_VISIBILITY.catastro).toBe(false);
  });

  // Removal task — the 3D viewer no longer owns the "Zona Consorcio" outline
  // (the 3D mesh itself IS the consorcio area). 2D keeps its own zona layer.
  it('does NOT expose a `zona` key in the 3D base visibility record', () => {
    expect(
      Object.prototype.hasOwnProperty.call(TERRAIN_DEFAULT_VECTOR_LAYER_VISIBILITY, 'zona'),
    ).toBe(false);
  });
});

describe('PRIORITY_3D_VECTOR_LAYERS (3D toggles panel config)', () => {
  // Removal task — dropping the zona entry means the 3D "Capas vectoriales
  // 3D" checkbox list no longer offers a "Zona Consorcio" row. 2D keeps its
  // own toggle untouched.
  it('does NOT list a zona entry in the 3D toggles vector config', () => {
    const ids = PRIORITY_3D_VECTOR_LAYERS.map((layer) => layer.id);
    expect(ids).not.toContain('zona');

    const labels = PRIORITY_3D_VECTOR_LAYERS.map((layer) => layer.label);
    expect(labels).not.toContain('Zona Consorcio');
  });
});

describe('buildClickableLayers3D (click-target whitelist)', () => {
  // Removal task — the zona-fill layer was only registered in 2D; it never
  // existed in the 3D MapLibre instance (3D rendered a zona-line outline via
  // `terrainVectorLayerEffects`). The clickable whitelist carried a stale
  // `zona-fill` id that never matched. We drop it so the whitelist reflects
  // reality and so no future code re-introduces a zona id by accident.
  it('does NOT include any zona layer id in the click-target whitelist', () => {
    const ids = buildClickableLayers3D();
    expect(ids.some((id) => id.includes('zona'))).toBe(false);
  });
});

describe('mapLayerSyncStore — map3d slice shape (Phase 0 smoke)', () => {
  it('seeds the 5 Pilar Verde keys + 2 Canales master keys with lightweight 3D defaults', () => {
    // Read directly from the live store so we exercise the actual `defaultVisibleVectors`
    // value the 3D viewer will see at first mount (empty localStorage path).
    const visible = useMapLayerSyncStore.getState().map3d.visibleVectors;

    for (const layerId of PILAR_VERDE_LAYER_IDS) {
      expect(visible).toHaveProperty(layerId);
      expect(visible[layerId]).toBe(PILAR_VERDE_DEFAULT_VISIBILITY[layerId]);
    }

    for (const layerId of PILAR_AZUL_LAYER_IDS) {
      expect(visible).toHaveProperty(layerId);
    }

    // Store map3d defaults mirror map2d since acb1d23 ('unify 2D and 3D
    // viewer layer behaviour'): canales relevados start visible.
    expect(visible.canales_relevados).toBe(true);
    expect(visible.canales_propuestos).toBe(false);
  });
});
