/**
 * TerrainViewer3DCanalesSync.test.tsx
 *
 * Phase 2 (Batch C) of `pilar-verde-y-canales-3d` — wires the canales layer
 * sync helper (`syncCanalesLayers`) into the 3D viewer via a dedicated hook
 * `useTerrainCanalesEffects`, mirroring the 2D blueprint
 * (`useMapLayerEffects.ts` lines 299-346).
 *
 * Contract asserted by these tests:
 *   1. When `useCanales()` resolves with non-null `relevados` + `propuestas`
 *      AND the map is mounted, `syncCanalesLayers` is called ONCE with:
 *        { relevados, propuestas,
 *          relevadosVisible: <matches master toggle>,
 *          propuestasVisible: <matches master toggle>,
 *          visibleRelevadoIds: <from `isCanalVisible` per-canal gate>,
 *          visiblePropuestaIds: <from `getVisiblePropuestaIds('map3d')`>,
 *          activeEtapas: <non-empty subset of ALL_ETAPAS OR fallback ALL_ETAPAS> }.
 *   2. Toggling an etapa in `propuestasEtapasVisibility` re-fires the sync with
 *      the updated `activeEtapas` subset.
 *   3. The map instance passed to `syncCanalesLayers` is the SAME MapLibre
 *      instance created by `TerrainViewer3D` (proven via ref equality over
 *      the shared `MapStub` singleton).
 *
 * The z-order hoist is NOT asserted here: `syncCanalesLayers` auto-invokes
 * the private `raiseCanalesStack` at its tail (see `mapLayerEffectHelpers.ts`
 * line 626). Asserting twice would couple the 3D wiring to helper internals.
 */

import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, act } from '@testing-library/react';
import type { FeatureCollection, LineString } from 'geojson';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type {
  CanalFeatureProperties,
  IndexFile,
} from '../../src/types/canales';

// ---------------------------------------------------------------------------
// Hook mocks — controlled per-test via the *Mock handles below.
// ---------------------------------------------------------------------------

const useCanalesMock = vi.fn();
const usePilarVerdeMock = vi.fn();

vi.mock('../../src/hooks/useCanales', () => ({
  useCanales: (...args: unknown[]) => useCanalesMock(...args),
  CANALES_PATHS: {},
}));

vi.mock('../../src/hooks/usePilarVerde', () => ({
  usePilarVerde: (...args: unknown[]) => usePilarVerdeMock(...args),
  PILAR_VERDE_PUBLIC_PATHS: {},
}));

vi.mock('../../src/hooks/useGeoLayers', () => ({
  useGeoLayers: () => ({ layers: [] }),
  buildTileUrl: () => 'https://tiles.test/{z}/{x}/{y}.png',
}));
vi.mock('../../src/hooks/useGEELayers', () => ({
  useGEELayers: () => ({ layers: {} }),
  GEE_LAYER_COLORS: { candil: '#000', ml: '#000', noroeste: '#000', norte: '#000' },
}));
vi.mock('../../src/hooks/useBasins', () => ({ useBasins: () => ({ basins: null }) }));
vi.mock('../../src/hooks/useApprovedZones', () => ({
  useApprovedZones: () => ({ approvedZones: null }),
}));
vi.mock('../../src/hooks/useCaminosColoreados', () => ({
  useCaminosColoreados: () => ({ caminos: null }),
}));
vi.mock('../../src/hooks/useCatastroMap', () => ({
  useCatastroMap: () => ({ catastroMap: null }),
}));
vi.mock('../../src/hooks/useSoilMap', () => ({
  useSoilMap: () => ({ soilMap: null }),
  getSoilColor: () => '#888',
}));
vi.mock('../../src/hooks/useSelectedImage', () => ({
  useSelectedImageListener: () => null,
}));
vi.mock('../../src/hooks/useWaterways', () => ({
  useWaterways: () => ({ waterways: [] }),
  WATERWAY_DEFS: [],
}));

// ---------------------------------------------------------------------------
// Sync helper mocks — spy on `syncCanalesLayers` + stub the 5 PV helpers so
// their state-mutation is inert (the PV pipeline is asserted elsewhere).
// ---------------------------------------------------------------------------

const syncCanalesLayersMock = vi.fn();
const syncBpaHistoricoLayerMock = vi.fn();
const syncAgroAceptadaLayerMock = vi.fn();
const syncAgroPresentadaLayerMock = vi.fn();
const syncAgroZonasLayerMock = vi.fn();
const syncPorcentajeForestacionLayerMock = vi.fn();

vi.mock('../../src/components/map2d/mapLayerEffectHelpers', async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>;
  return {
    ...actual,
    syncCanalesLayers: (...args: unknown[]) => syncCanalesLayersMock(...args),
    syncBpaHistoricoLayer: (...args: unknown[]) => syncBpaHistoricoLayerMock(...args),
    syncAgroAceptadaLayer: (...args: unknown[]) => syncAgroAceptadaLayerMock(...args),
    syncAgroPresentadaLayer: (...args: unknown[]) => syncAgroPresentadaLayerMock(...args),
    syncAgroZonasLayer: (...args: unknown[]) => syncAgroZonasLayerMock(...args),
    syncPorcentajeForestacionLayer: (...args: unknown[]) =>
      syncPorcentajeForestacionLayerMock(...args),
  };
});

// ---------------------------------------------------------------------------
// MapLibre stub — records the created instance so tests can assert
// ref-equality of the `map` argument passed to `syncCanalesLayers`.
// `on('load', cb)` fires `cb()` synchronously so the viewer's `ready` state
// flips to true and the vector-layer effects execute within the same render
// pass. `setFilter`, `addSource`, etc. are no-op stubs.
// ---------------------------------------------------------------------------

interface MapStubInstance {
  on: (event: string, cb: (e?: unknown) => void) => void;
  off: () => void;
  once: () => void;
  addControl: () => void;
  remove: () => void;
  isStyleLoaded: () => boolean;
  getLayer: () => undefined;
  getSource: () => undefined;
  addLayer: () => void;
  addSource: () => void;
  removeLayer: () => void;
  removeSource: () => void;
  setLayoutProperty: () => void;
  setPaintProperty: () => void;
  setTerrain: () => void;
  moveLayer: () => void;
  setFilter: () => void;
}

let lastMapInstance: MapStubInstance | null = null;

vi.mock('maplibre-gl', () => {
  class MapStub {
    constructor() {
      lastMapInstance = this as unknown as MapStubInstance;
    }
    on(event: string, cb: (e?: unknown) => void) {
      if (event === 'load') {
        cb();
      }
    }
    off() {}
    once() {}
    addControl() {}
    remove() {
      lastMapInstance = null;
    }
    isStyleLoaded() {
      return true;
    }
    getLayer() {
      return undefined;
    }
    getSource() {
      return undefined;
    }
    addLayer() {}
    addSource() {}
    removeLayer() {}
    removeSource() {}
    setLayoutProperty() {}
    setPaintProperty() {}
    setTerrain() {}
    moveLayer() {}
    setFilter() {}
  }
  return {
    default: {
      Map: MapStub,
      NavigationControl: class {},
      addProtocol: () => {},
      removeProtocol: () => {},
    },
    Map: MapStub,
    NavigationControl: class {},
    addProtocol: () => {},
    removeProtocol: () => {},
  };
});

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

function makeCanalesCollection(
  label: string,
): FeatureCollection<LineString, CanalFeatureProperties> {
  return {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        geometry: { type: 'LineString', coordinates: [[0, 0], [1, 1]] },
        properties: {
          id: `${label}-id`,
          estado: 'relevado',
          nombre: label,
          codigo: null,
          prioridad: null,
          longitud_m: 100,
          featured: false,
          obras: null,
          tipo: null,
          tipo_obra: null,
          ejecutor: null,
          fecha_inicio: null,
          fecha_fin: null,
          fuente: null,
          source_file: null,
          source_style: null,
        } as CanalFeatureProperties,
      },
    ],
  };
}

function makeIndex(): IndexFile {
  return {
    schema_version: '1.0',
    generated_at: '2026-04-20T00:00:00Z',
    counts: { relevados: 1, propuestas: 1, total: 2 },
    relevados: [
      {
        id: 'rel-one',
        nombre: 'Relevado Uno',
        codigo: null,
        longitud_m: 100,
        featured: false,
      },
    ],
    propuestas: [
      {
        id: 'prop-alta',
        nombre: 'Propuesto Alta',
        codigo: null,
        prioridad: 'Alta',
        longitud_m: 200,
        featured: false,
      },
      {
        id: 'prop-media-alta',
        nombre: 'Propuesto Media-Alta',
        codigo: null,
        prioridad: 'Media-Alta',
        longitud_m: 150,
        featured: false,
      },
    ],
  };
}

function renderViewer(ui: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MantineProvider>{ui}</MantineProvider>
    </QueryClientProvider>,
  );
}

// ---------------------------------------------------------------------------
// Suite
// ---------------------------------------------------------------------------

describe('TerrainViewer3D — Canales layer sync (Phase 2)', () => {
  beforeEach(async () => {
    useCanalesMock.mockReset();
    usePilarVerdeMock.mockReset();
    syncCanalesLayersMock.mockReset();
    syncBpaHistoricoLayerMock.mockReset();
    syncAgroAceptadaLayerMock.mockReset();
    syncAgroPresentadaLayerMock.mockReset();
    syncAgroZonasLayerMock.mockReset();
    syncPorcentajeForestacionLayerMock.mockReset();
    lastMapInstance = null;

    // Default: no Pilar Verde payload — Batch C tests exercise canales only.
    usePilarVerdeMock.mockReturnValue({
      data: null,
      loading: false,
      error: null,
    });

    // Reset store to clean state: etapas all ON, masters ON for both canales
    // layers. `initializedViews.map3d = true` tells the viewer to SKIP the
    // `seedViewFromOther('map3d', 'map2d')` effect — otherwise the viewer
    // would overwrite our `canales_propuestos: true` with the 2D default
    // (false) on mount.
    const storeModule = await import('../../src/stores/mapLayerSyncStore');
    storeModule.useMapLayerSyncStore.setState((prev) => ({
      ...prev,
      propuestasEtapasVisibility: { ...storeModule.PROPUESTAS_ETAPAS_DEFAULTS },
      initializedViews: { ...prev.initializedViews, map3d: true },
      map3d: {
        ...prev.map3d,
        visibleVectors: {
          ...prev.map3d.visibleVectors,
          canales_relevados: true,
          canales_propuestos: true,
        },
      },
    }));
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('calls syncCanalesLayers with the relevados+propuestas payload, master toggles ON, and all 5 etapas active', async () => {
    const relevados = makeCanalesCollection('relevados');
    const propuestas = makeCanalesCollection('propuestas');
    const index = makeIndex();

    useCanalesMock.mockReturnValue({
      relevados,
      propuestas,
      index,
      isLoading: false,
      isError: false,
    });

    const { default: TerrainViewer3D } = await import(
      '../../src/components/terrain/TerrainViewer3D'
    );

    renderViewer(<TerrainViewer3D demLayerId="dem-uuid" />);

    expect(lastMapInstance).not.toBeNull();
    expect(syncCanalesLayersMock).toHaveBeenCalled();
    const lastCall =
      syncCanalesLayersMock.mock.calls[syncCanalesLayersMock.mock.calls.length - 1];
    const [mapArg, params] = lastCall as [MapStubInstance, Record<string, unknown>];
    expect(mapArg).toBe(lastMapInstance);
    expect(params.relevados).toBe(relevados);
    expect(params.propuestas).toBe(propuestas);
    expect(params.relevadosVisible).toBe(true);
    expect(params.propuestasVisible).toBe(true);
    // All 5 etapas active (defaults)
    const activeEtapas = params.activeEtapas as readonly string[];
    expect(new Set(activeEtapas)).toEqual(
      new Set(['Alta', 'Media-Alta', 'Media', 'Opcional', 'Largo plazo']),
    );
    // `visibleRelevadoIds` contains the sole relevado (per-canal default true).
    expect(params.visibleRelevadoIds).toEqual(['rel-one']);
    // `visiblePropuestaIds` includes both propuestas (etapas Alta + Media-Alta both ON).
    const visiblePropuestaIds = params.visiblePropuestaIds as readonly string[];
    expect(new Set(visiblePropuestaIds)).toEqual(new Set(['prop-alta', 'prop-media-alta']));
  });

  it('re-fires syncCanalesLayers with the updated activeEtapas subset when an etapa toggles OFF', async () => {
    const relevados = makeCanalesCollection('relevados');
    const propuestas = makeCanalesCollection('propuestas');
    const index = makeIndex();

    useCanalesMock.mockReturnValue({
      relevados,
      propuestas,
      index,
      isLoading: false,
      isError: false,
    });

    const storeModule = await import('../../src/stores/mapLayerSyncStore');
    // Precondition: all 5 etapas ON (beforeEach resets this).
    const { default: TerrainViewer3D } = await import(
      '../../src/components/terrain/TerrainViewer3D'
    );

    renderViewer(<TerrainViewer3D demLayerId="dem-uuid" />);

    expect(syncCanalesLayersMock).toHaveBeenCalled();

    // Toggle `Media-Alta` OFF.
    await act(async () => {
      storeModule.useMapLayerSyncStore.setState((prev) => ({
        ...prev,
        propuestasEtapasVisibility: {
          ...prev.propuestasEtapasVisibility,
          'Media-Alta': false,
        },
      }));
    });

    const lastCall =
      syncCanalesLayersMock.mock.calls[syncCanalesLayersMock.mock.calls.length - 1];
    const params = lastCall[1] as Record<string, unknown>;
    const activeEtapas = params.activeEtapas as readonly string[];
    expect(activeEtapas).not.toContain('Media-Alta');
    // Remaining 4 still active.
    expect(new Set(activeEtapas)).toEqual(
      new Set(['Alta', 'Media', 'Opcional', 'Largo plazo']),
    );
    // `visiblePropuestaIds` now excludes the Media-Alta propuesto.
    const visiblePropuestaIds = params.visiblePropuestaIds as readonly string[];
    expect(visiblePropuestaIds).toContain('prop-alta');
    expect(visiblePropuestaIds).not.toContain('prop-media-alta');
  });

  it('falls back to ALL_ETAPAS when every etapa is toggled OFF (so the layer is not left empty)', async () => {
    const relevados = makeCanalesCollection('relevados');
    const propuestas = makeCanalesCollection('propuestas');
    const index = makeIndex();

    useCanalesMock.mockReturnValue({
      relevados,
      propuestas,
      index,
      isLoading: false,
      isError: false,
    });

    const storeModule = await import('../../src/stores/mapLayerSyncStore');

    const { default: TerrainViewer3D } = await import(
      '../../src/components/terrain/TerrainViewer3D'
    );

    renderViewer(<TerrainViewer3D demLayerId="dem-uuid" />);

    // Toggle ALL 5 etapas OFF.
    await act(async () => {
      storeModule.useMapLayerSyncStore.setState((prev) => ({
        ...prev,
        propuestasEtapasVisibility: {
          'Alta': false,
          'Media-Alta': false,
          'Media': false,
          'Opcional': false,
          'Largo plazo': false,
        },
      }));
    });

    const lastCall =
      syncCanalesLayersMock.mock.calls[syncCanalesLayersMock.mock.calls.length - 1];
    const params = lastCall[1] as Record<string, unknown>;
    const activeEtapas = params.activeEtapas as readonly string[];
    // Fallback to ALL_ETAPAS (all 5) so the user still sees propuestos.
    expect(activeEtapas.length).toBe(5);
    expect(new Set(activeEtapas)).toEqual(
      new Set(['Alta', 'Media-Alta', 'Media', 'Opcional', 'Largo plazo']),
    );
  });

  it('passes relevadosVisible=false when the canales_relevados master is OFF', async () => {
    const relevados = makeCanalesCollection('relevados');
    const propuestas = makeCanalesCollection('propuestas');
    const index = makeIndex();

    useCanalesMock.mockReturnValue({
      relevados,
      propuestas,
      index,
      isLoading: false,
      isError: false,
    });

    const storeModule = await import('../../src/stores/mapLayerSyncStore');
    // Flip relevados master OFF. `initializedViews.map3d` stays `true`
    // (set in beforeEach) so the viewer won't reseed from map2d.
    storeModule.useMapLayerSyncStore.setState((prev) => ({
      ...prev,
      initializedViews: { ...prev.initializedViews, map3d: true },
      map3d: {
        ...prev.map3d,
        visibleVectors: {
          ...prev.map3d.visibleVectors,
          canales_relevados: false,
        },
      },
    }));

    const { default: TerrainViewer3D } = await import(
      '../../src/components/terrain/TerrainViewer3D'
    );

    renderViewer(<TerrainViewer3D demLayerId="dem-uuid" />);

    const lastCall =
      syncCanalesLayersMock.mock.calls[syncCanalesLayersMock.mock.calls.length - 1];
    const params = lastCall[1] as Record<string, unknown>;
    expect(params.relevadosVisible).toBe(false);
  });

  it('does NOT call syncCanalesLayers when both relevados and propuestas are null', async () => {
    useCanalesMock.mockReturnValue({
      relevados: null,
      propuestas: null,
      index: null,
      isLoading: false,
      isError: false,
    });

    const { default: TerrainViewer3D } = await import(
      '../../src/components/terrain/TerrainViewer3D'
    );

    renderViewer(<TerrainViewer3D demLayerId="dem-uuid" />);

    expect(syncCanalesLayersMock).not.toHaveBeenCalled();
  });
});
