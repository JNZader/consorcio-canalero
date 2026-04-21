/**
 * Pilar Verde wiring of `useMapLayerEffects`.
 *
 * These tests focus ONLY on the 5 new sync calls introduced in Phase 2.
 * They do NOT attempt to cover the existing layer-sync flows — those are
 * exercised via their own helpers tests.
 *
 * We mock `mapLayerEffectHelpers` so we can assert the hook dispatches each
 * sync call with the correct `(map, collection, isVisible)` triplet derived
 * from `vectorVisibility` + the `pilarVerde` data slot.
 */

import type { FeatureCollection } from 'geojson';
import { renderHook } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import { useMapLayerEffects } from '../../src/components/map2d/useMapLayerEffects';
import type { PilarVerdeData } from '../../src/types/pilarVerde';

// Mock the whole helper module. We only assert on the 5 Pilar Verde calls —
// the rest (waterways / soil / catastro / etc.) are stubbed to no-ops so we
// don't touch their behavior.
vi.mock('../../src/components/map2d/mapLayerEffectHelpers', () => ({
  shouldShowSuggestedZones: vi.fn(() => false),
  syncApprovedZoneLayers: vi.fn(),
  syncBaseTileVisibility: vi.fn(),
  syncBasinLayers: vi.fn(),
  syncCatastroLayers: vi.fn(),
  syncRoadLayers: vi.fn(),
  syncSoilLayers: vi.fn(),
  syncSuggestedZoneLayers: vi.fn(),
  syncWaterwayLayers: vi.fn(),
  syncZonaLayer: vi.fn(),
  // ── Pilar Verde ──
  syncBpaHistoricoLayer: vi.fn(),
  syncAgroAceptadaLayer: vi.fn(),
  syncAgroPresentadaLayer: vi.fn(),
  syncAgroZonasLayer: vi.fn(),
  syncPorcentajeForestacionLayer: vi.fn(),
  // ── Pilar Azul (Canales + Escuelas) ──
  syncCanalesLayers: vi.fn(),
  syncEscuelasLayer: vi.fn(() => Promise.resolve()),
}));

vi.mock('../../src/components/map2d/mapRasterOverlayHelpers', () => ({
  getVisibleRasterLayersForDem: vi.fn(() => []),
  syncDemRasterLayer: vi.fn(),
  syncIgnLayer: vi.fn(),
  syncImageOverlays: vi.fn(),
  syncMartinSuggestionLayers: vi.fn(),
}));

import * as helpers from '../../src/components/map2d/mapLayerEffectHelpers';

function fc(): FeatureCollection {
  return { type: 'FeatureCollection', features: [] };
}

function emptyPilarVerde(): PilarVerdeData {
  return {
    zonaAmpliada: null,
    bpa2025: null,
    bpaHistorico: null,
    agroAceptada: null,
    agroPresentada: null,
    agroZonas: null,
    porcentajeForestacion: null,
    bpaEnriched: null,
    bpaHistory: null,
    aggregates: null,
  };
}

function renderWithParams(overrides?: Partial<Parameters<typeof useMapLayerEffects>[0]>) {
  const mapRef = { current: { dummy: true } } as unknown as Parameters<
    typeof useMapLayerEffects
  >[0]['mapRef'];

  return renderHook(() =>
    useMapLayerEffects({
      mapRef,
      mapReady: true,
      baseLayer: 'osm',
      isAdmin: false,
      vectorVisibility: {},
      soilCollection: null,
      roadsCollection: null,
      basins: null,
      zonaCollection: null,
      approvedZonesCollection: null,
      suggestedZonesDisplay: null,
      showSuggestedZonesPanel: false,
      hasApprovedZones: false,
      activeDemLayerId: null,
      showDemOverlay: false,
      demTileUrl: null,
      allGeoLayers: [],
      setVisibleRasterLayers: vi.fn(),
      showIGNOverlay: false,
      viewMode: 'base',
      selectedImage: null,
      comparison: null,
      waterwaysDefs: [],
      pilarVerde: emptyPilarVerde(),
      ...overrides,
    }),
  );
}

describe('useMapLayerEffects · Pilar Verde wiring', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('dispatches the 5 Pilar Verde sync calls with their matching data slots and visibility flags', () => {
    const bpaHistorico = fc();
    const aceptada = fc();
    const presentada = fc();
    const zonas = fc();
    const forestacion = fc();

    renderWithParams({
      vectorVisibility: {
        pilar_verde_bpa_historico: true,
        pilar_verde_agro_aceptada: true,
        pilar_verde_agro_presentada: false,
        pilar_verde_agro_zonas: true,
        pilar_verde_porcentaje_forestacion: false,
      },
      pilarVerde: {
        ...emptyPilarVerde(),
        bpaHistorico: bpaHistorico as never,
        agroAceptada: aceptada as never,
        agroPresentada: presentada as never,
        agroZonas: zonas as never,
        porcentajeForestacion: forestacion as never,
      },
    });

    expect(helpers.syncBpaHistoricoLayer).toHaveBeenCalledWith(expect.anything(), bpaHistorico, true);
    expect(helpers.syncAgroAceptadaLayer).toHaveBeenCalledWith(expect.anything(), aceptada, true);
    expect(helpers.syncAgroPresentadaLayer).toHaveBeenCalledWith(
      expect.anything(),
      presentada,
      false,
    );
    expect(helpers.syncAgroZonasLayer).toHaveBeenCalledWith(expect.anything(), zonas, true);
    expect(helpers.syncPorcentajeForestacionLayer).toHaveBeenCalledWith(
      expect.anything(),
      forestacion,
      false,
    );
  });

  it('passes null slots through to sync helpers when pilar verde data is absent', () => {
    renderWithParams({
      vectorVisibility: { pilar_verde_bpa_historico: true },
      pilarVerde: emptyPilarVerde(),
    });

    expect(helpers.syncBpaHistoricoLayer).toHaveBeenCalledWith(expect.anything(), null, true);
    expect(helpers.syncAgroAceptadaLayer).toHaveBeenCalledWith(expect.anything(), null, false);
  });

  it('tolerates a missing pilarVerde param — sync helpers still called with null slots and off', () => {
    renderWithParams({
      pilarVerde: undefined,
      vectorVisibility: {},
    });

    expect(helpers.syncBpaHistoricoLayer).toHaveBeenCalledWith(expect.anything(), null, false);
    expect(helpers.syncPorcentajeForestacionLayer).toHaveBeenCalledWith(
      expect.anything(),
      null,
      false,
    );
  });
});
