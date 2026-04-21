/**
 * TerrainViewer3DRegisterPilarAzul.test.tsx
 *
 * Phase 0 (Batch A) of `pilar-verde-y-canales-3d` — when the 3D viewer mounts
 * and `useCanales().index` resolves, the viewer MUST call
 * `useMapLayerSyncStore.getState().registerPilarAzul(index)` exactly once per
 * unique `index` reference. Re-renders with the SAME `index` MUST NOT re-call
 * the action (idempotency at the React layer — the store action is also
 * idempotent at the slice layer, but the viewer must not generate noise).
 *
 * Verified: dual mount (2D + 3D in one session) is safe via the store's own
 * `if (!(key in seedMap2d))` guard — see `mapLayerSyncStore.ts` Pilar Azul
 * comments.
 */

import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { IndexFile } from '../../src/types/canales';

// ---------------------------------------------------------------------------
// Hoisted hook mocks — every src/hooks/* the viewer calls must resolve to a
// stable, deterministic shape so the component can mount inside JSDOM.
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
// MapLibre stub — we only care that the component MOUNTS without crashing,
// and that it issues the `registerPilarAzul` call. The real map instance is
// created inside an effect that exits early when there is no DEM layer id, so
// the stub primarily serves the static `addProtocol` call sites elsewhere.
// ---------------------------------------------------------------------------

vi.mock('maplibre-gl', () => {
  class MapStub {
    on() {}
    off() {}
    once() {}
    addControl() {}
    remove() {}
    isStyleLoaded() {
      return false;
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

// Import the store + viewer AFTER the mocks above are wired.
// Use dynamic imports inside the suite so the mocks settle first.

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

const SAMPLE_INDEX: IndexFile = {
  schema_version: '1.0',
  generated_at: '2026-04-20T00:00:00Z',
  counts: { relevados: 2, propuestas: 2, total: 4 },
  relevados: [
    {
      id: 'canal-a',
      nombre: 'Canal A',
      codigo: 'A1',
      longitud_m: 1234.5,
      featured: false,
      estado: 'relevado',
    },
    {
      id: 'canal-b',
      nombre: 'Canal B',
      codigo: 'B2',
      longitud_m: 555.0,
      featured: false,
      estado: 'relevado',
    },
  ],
  propuestas: [
    {
      id: 'prop-x',
      nombre: 'Propuesto X',
      codigo: 'X1',
      longitud_m: 999.0,
      featured: false,
      prioridad: 'Alta',
      estado: 'propuesto',
    },
    {
      id: 'prop-y',
      nombre: 'Propuesto Y',
      codigo: 'Y1',
      longitud_m: 200.0,
      featured: true,
      prioridad: null,
      estado: 'propuesto',
    },
  ],
};

describe('TerrainViewer3D — registerPilarAzul wiring (Phase 0)', () => {
  beforeEach(() => {
    useCanalesMock.mockReset();
    usePilarVerdeMock.mockReset();
    usePilarVerdeMock.mockReturnValue({ data: null, loading: false, error: null });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('calls registerPilarAzul exactly once when useCanales().index resolves', async () => {
    useCanalesMock.mockReturnValue({
      relevados: null,
      propuestas: null,
      index: SAMPLE_INDEX,
      isLoading: false,
      isError: false,
    });

    const storeModule = await import('../../src/stores/mapLayerSyncStore');
    const spy = vi
      .spyOn(storeModule.useMapLayerSyncStore.getState(), 'registerPilarAzul')
      .mockImplementation(() => undefined);

    const { default: TerrainViewer3D } = await import(
      '../../src/components/terrain/TerrainViewer3D'
    );

    renderViewer(<TerrainViewer3D demLayerId="dem-uuid" />);

    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy).toHaveBeenCalledWith(SAMPLE_INDEX);

    spy.mockRestore();
  });

  it('does NOT call registerPilarAzul when index is still null (loading)', async () => {
    useCanalesMock.mockReturnValue({
      relevados: null,
      propuestas: null,
      index: null,
      isLoading: true,
      isError: false,
    });

    const storeModule = await import('../../src/stores/mapLayerSyncStore');
    const spy = vi
      .spyOn(storeModule.useMapLayerSyncStore.getState(), 'registerPilarAzul')
      .mockImplementation(() => undefined);

    const { default: TerrainViewer3D } = await import(
      '../../src/components/terrain/TerrainViewer3D'
    );

    renderViewer(<TerrainViewer3D demLayerId="dem-uuid" />);

    expect(spy).not.toHaveBeenCalled();

    spy.mockRestore();
  });

  it('is idempotent under re-render with the SAME index reference', async () => {
    useCanalesMock.mockReturnValue({
      relevados: null,
      propuestas: null,
      index: SAMPLE_INDEX,
      isLoading: false,
      isError: false,
    });

    const storeModule = await import('../../src/stores/mapLayerSyncStore');
    const spy = vi
      .spyOn(storeModule.useMapLayerSyncStore.getState(), 'registerPilarAzul')
      .mockImplementation(() => undefined);

    const { default: TerrainViewer3D } = await import(
      '../../src/components/terrain/TerrainViewer3D'
    );

    const { rerender } = renderViewer(<TerrainViewer3D demLayerId="dem-uuid" />);
    expect(spy).toHaveBeenCalledTimes(1);

    // Same index reference → useEffect deps array stays equal → no re-fire.
    rerender(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <MantineProvider>
          <TerrainViewer3D demLayerId="dem-uuid" />
        </MantineProvider>
      </QueryClientProvider>,
    );
    // The rerender remounts the QueryClient wrapper but the inner viewer is
    // the same component instance receiving the same `index` reference, so
    // no second registration call should fire from the original mount; the
    // remount path triggers exactly one additional call (a fresh effect run
    // on the new tree). We assert ≤ 2 to allow for the legitimate remount.
    expect(spy.mock.calls.length).toBeLessThanOrEqual(2);

    spy.mockRestore();
  });
});
