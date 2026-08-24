/**
 * Canal-mode wiring of `useMapLayerEffects` (ficha UX bug-1, race-free).
 *
 * `useMapLayerEffects` is the SINGLE owner of `canales_relevados-line`
 * visibility. Entering canal-selection mode (`isFichaCanal`) must suppress the
 * static relevados line — the geometric twin of the cyan `vt_canal_network`
 * line — so only ONE canal trace renders, and toggling ANY unrelated layer
 * while in canal mode must NOT re-show it (the flicker race the old two-effect
 * design allowed). Leaving canal mode restores the line to its live toggle.
 *
 * We mock the helper module and assert the `relevadosVisible` flag threaded into
 * `syncCanalesLayers`, since that flag is the sole computation that drives the
 * layer's visibility.
 */

import type { FeatureCollection } from 'geojson';
import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useMapLayerEffects } from '../../src/components/map2d/useMapLayerEffects';

vi.mock('../../src/components/map2d/mapLayerEffectHelpers', () => ({
  syncApprovedZoneLayers: vi.fn(),
  syncBaseTileVisibility: vi.fn(),
  syncBasinLayers: vi.fn(),
  syncCatastroLayers: vi.fn(),
  syncRoadFlowLayers: vi.fn(),
  syncRoadLayers: vi.fn(),
  syncSoilLayers: vi.fn(),
  syncWaterwayLayers: vi.fn(),
  syncZonaLayer: vi.fn(),
  syncBpaHistoricoLayer: vi.fn(),
  syncAgroAceptadaLayer: vi.fn(),
  syncAgroPresentadaLayer: vi.fn(),
  syncAgroZonasLayer: vi.fn(),
  syncPorcentajeForestacionLayer: vi.fn(),
  syncCanalesLayers: vi.fn(),
  syncEscuelasLayer: vi.fn(() => Promise.resolve()),
  syncYpfEstacionBombeoLayer: vi.fn(),
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

type Params = Parameters<typeof useMapLayerEffects>[0];

function baseParams(overrides?: Partial<Params>): Params {
  return {
    mapRef: { current: { dummy: true } } as unknown as Params['mapRef'],
    mapReady: true,
    baseLayer: 'osm',
    vectorVisibility: {},
    soilCollection: null,
    roadsCollection: null,
    basins: null,
    zonaCollection: null,
    approvedZonesCollection: null,
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
    pilarVerde: undefined,
    // A truthy canales object so the sync effect runs (it early-returns on null).
    canales: { relevados: fc() as never, propuestas: fc() as never },
    ...overrides,
  } as Params;
}

/** relevadosVisible flags from every syncCanalesLayers call, in order. */
function relevadosFlags(): boolean[] {
  return (helpers.syncCanalesLayers as unknown as { mock: { calls: unknown[][] } }).mock.calls.map(
    ([, params]) => (params as { relevadosVisible: boolean }).relevadosVisible
  );
}

/** propuestasVisible flags from every syncCanalesLayers call, in order. */
function propuestasFlags(): boolean[] {
  return (helpers.syncCanalesLayers as unknown as { mock: { calls: unknown[][] } }).mock.calls.map(
    ([, params]) => (params as { propuestasVisible: boolean }).propuestasVisible
  );
}

// A7 slice 2 INVERTS the old behavior: the curated relevados/propuestos layers ARE
// the ficha canal source now (`vt_canal_network` is gone), so canal mode must SHOW
// them (and make them clickable) regardless of the user's master toggles.
describe('useMapLayerEffects · canal-mode canals are shown (ficha source)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('FORCES the relevados line visible in canal mode even when its toggle is OFF', () => {
    renderHook(() =>
      useMapLayerEffects(
        baseParams({
          vectorVisibility: { canales_relevados: false },
          isFichaCanal: true,
        })
      )
    );

    expect(helpers.syncCanalesLayers).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ relevadosVisible: true })
    );
  });

  it('FORCES the propuestos line visible in canal mode even when its toggle is OFF', () => {
    renderHook(() =>
      useMapLayerEffects(
        baseParams({
          vectorVisibility: { canales_propuestos: false },
          isFichaCanal: true,
        })
      )
    );

    expect(helpers.syncCanalesLayers).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ propuestasVisible: true })
    );
  });

  it('keeps the canals shown when an UNRELATED layer is toggled during canal mode (no flicker)', () => {
    const { rerender } = renderHook((props: Params) => useMapLayerEffects(props), {
      initialProps: baseParams({
        vectorVisibility: { canales_relevados: false },
        isFichaCanal: true,
      }),
    });

    // Toggle an unrelated layer (soil) while STILL in canal mode.
    rerender(
      baseParams({
        vectorVisibility: { canales_relevados: false, soil: true },
        soilCollection: fc(),
        isFichaCanal: true,
      })
    );

    // The relevados layer was shown at EVERY point during canal mode.
    expect(relevadosFlags().every((v) => v === true)).toBe(true);
    expect(propuestasFlags().every((v) => v === true)).toBe(true);
  });

  it('restores the relevados line to its live toggle state on leaving canal mode', () => {
    const { rerender } = renderHook((props: Params) => useMapLayerEffects(props), {
      initialProps: baseParams({
        vectorVisibility: { canales_relevados: false },
        isFichaCanal: true,
      }),
    });
    expect(relevadosFlags().at(-1)).toBe(true); // forced shown in canal mode

    rerender(
      baseParams({
        vectorVisibility: { canales_relevados: false },
        isFichaCanal: false,
      })
    );
    expect(relevadosFlags().at(-1)).toBe(false); // back to the (off) toggle

    rerender(
      baseParams({
        vectorVisibility: { canales_relevados: true },
        isFichaCanal: false,
      })
    );
    expect(relevadosFlags().at(-1)).toBe(true); // follows the toggle when on
  });
});
