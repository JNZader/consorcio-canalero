import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import TerrainViewer3D from '../../src/components/terrain/TerrainViewer3D';
import { playFlythrough } from '../../src/components/terrain/canalFlythrough';
import { createTerrainMapLibreMap } from '../../src/components/terrain/terrainMapLifecycle';
import { useMapCameraStore } from '../../src/stores/mapCameraStore';

const chromePropsSpy = vi.fn();

vi.mock('../../src/hooks/useCanales', () => ({
  useCanales: () => ({ relevados: null, propuestas: null, index: null }),
}));
vi.mock('../../src/hooks/usePilarVerde', () => ({
  usePilarVerde: () => ({ data: null }),
}));
vi.mock('../../src/hooks/useGeoLayers', () => ({
  useGeoLayers: () => ({ layers: [] }),
  buildTileUrl: () => 'https://tiles.test/{z}/{x}/{y}.png',
}));
vi.mock('../../src/hooks/useGEELayers', () => ({
  useGEELayers: () => ({ layers: {}, unavailableLayers: [] }),
  GEE_LAYER_COLORS: { candil: '#000', ml: '#000', noroeste: '#000', norte: '#000' },
}));
vi.mock('../../src/hooks/useBasins', () => ({ useBasins: () => ({ basins: null }) }));
vi.mock('../../src/hooks/useApprovedZones', () => ({
  useApprovedZones: () => ({ approvedZones: null }),
}));
vi.mock('../../src/hooks/useCaminosColoreados', () => ({
  useCaminosColoreados: () => ({ caminos: null }),
}));
vi.mock('../../src/hooks/useWaterways', () => ({
  useWaterways: () => ({ waterways: [] }),
}));
vi.mock('../../src/hooks/useConflictos', () => ({
  useConflictos: () => ({ conflictos: null }),
}));
vi.mock('../../src/hooks/useSelectedImage', () => ({
  useSelectedImageListener: () => null,
  getSelectedImageSync: () => null,
}));
vi.mock('../../src/lib/soilPmtiles', () => ({
  ensureSoilPmtilesArchive: vi.fn(),
  getSoilPmtilesArchiveKey: () => null,
}));
vi.mock('../../src/components/terrain/canalFlythrough', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../src/components/terrain/canalFlythrough')>();
  return {
    ...actual,
    playFlythrough: vi.fn(() => new Promise<void>(() => {})),
  };
});

let latestMapStub: {
  triggerLoad: () => void;
  setSelectedFeatures?: (features: unknown[]) => void;
} | null = null;

vi.mock('../../src/components/terrain/terrainMapLifecycle', () => ({
  createTerrainMapLibreMap: vi.fn(async () => {
    let loadCb: (() => void) | null = null;
    const map = {
      addControl: vi.fn(),
      on: vi.fn((event: string, cb: () => void) => {
        if (event === 'load') loadCb = cb;
      }),
      off: vi.fn(),
      once: vi.fn(),
      getCanvas: vi.fn(() => null),
      getCenter: vi.fn(() => ({ lng: -62.7, lat: -32.4 })),
      getZoom: vi.fn(() => 11),
      getBearing: vi.fn(() => 0),
      getPitch: vi.fn(() => 0),
      isStyleLoaded: vi.fn(() => true),
      getLayer: vi.fn(() => undefined),
      getSource: vi.fn(() => undefined),
      setLayoutProperty: vi.fn(),
      setPaintProperty: vi.fn(),
      setTerrain: vi.fn(),
      addSource: vi.fn(),
      addLayer: vi.fn(),
      removeLayer: vi.fn(),
      removeSource: vi.fn(),
      easeTo: vi.fn(),
      resize: vi.fn(),
      remove: vi.fn(),
    };
    latestMapStub = {
      triggerLoad: () => loadCb?.(),
    };
    return map;
  }),
  destroyMapLibreMap: vi.fn(),
}));

vi.mock('../../src/components/terrain/TerrainViewer3DChrome', () => ({
  TerrainViewer3DChrome: (props: Record<string, unknown>) => {
    chromePropsSpy(props);
    return (
      <div
        ref={props.mapContainerRef as React.RefObject<HTMLDivElement>}
        data-testid="terrain-chrome-stub"
      />
    );
  },
}));

vi.mock('../../src/components/terrain/useTerrainInteractionEffects', () => ({
  useTerrainInteractionEffects: ({
    setSelectedFeatures,
  }: {
    setSelectedFeatures: (features: unknown[]) => void;
  }) => {
    if (latestMapStub) {
      latestMapStub.setSelectedFeatures = setSelectedFeatures;
    }
  },
}));
vi.mock('../../src/components/terrain/useTerrainHoverTooltip', () => ({
  useTerrainHoverTooltip: () => {},
}));
vi.mock('../../src/components/terrain/useTerrainCanalesEffects', () => ({
  useTerrainCanalesEffects: () => {},
}));
vi.mock('../../src/components/terrain/useTerrainPilarVerdeEffects', () => ({
  useTerrainPilarVerdeEffects: () => {},
}));

describe('TerrainViewer3D stability (W-FE-02)', () => {
  const originalInnerWidth = window.innerWidth;

  beforeEach(() => {
    vi.clearAllMocks();
    latestMapStub = null;
    useMapCameraStore.setState({ camera: null });
    Object.defineProperty(window, 'innerWidth', {
      configurable: true,
      writable: true,
      value: 1280,
    });
  });

  afterEach(() => {
    Object.defineProperty(window, 'innerWidth', {
      configurable: true,
      writable: true,
      value: originalInnerWidth,
    });
  });

  it('does not recreate the MapLibre WebGL instance when viewport crosses 768px and re-renders', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
    const { rerender } = render(
      <QueryClientProvider client={client}>
        <MantineProvider env="test">
          <TerrainViewer3D demLayerId="dem-1" />
        </MantineProvider>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(createTerrainMapLibreMap).toHaveBeenCalledTimes(1);
    });
    expect(vi.mocked(createTerrainMapLibreMap).mock.calls[0]?.[1]).toMatchObject({ zoom: 11 });

    Object.defineProperty(window, 'innerWidth', {
      configurable: true,
      writable: true,
      value: 500,
    });

    rerender(
      <QueryClientProvider client={client}>
        <MantineProvider env="test">
          <TerrainViewer3D demLayerId="dem-1" center={[-62.7, -32.4]} />
        </MantineProvider>
      </QueryClientProvider>
    );

    await Promise.resolve();
    expect(createTerrainMapLibreMap).toHaveBeenCalledTimes(1);
  });

  it('aborts an active flythrough AbortSignal when TerrainViewer3D unmounts', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
    const { unmount } = render(
      <QueryClientProvider client={client}>
        <MantineProvider env="test">
          <TerrainViewer3D demLayerId="dem-1" />
        </MantineProvider>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(createTerrainMapLibreMap).toHaveBeenCalledTimes(1);
    });
    act(() => {
      latestMapStub?.triggerLoad();
      latestMapStub?.setSelectedFeatures?.([
        {
          type: 'Feature',
          properties: { nombre: 'Canal test' },
          geometry: {
            type: 'LineString',
            coordinates: [
              [-62.7, -32.4],
              [-62.69, -32.4],
            ],
          },
        },
      ]);
    });

    await waitFor(() => {
      const last = chromePropsSpy.mock.calls.at(-1)?.[0] as { canFlythrough?: boolean } | undefined;
      expect(last?.canFlythrough).toBe(true);
    });

    const lastProps = chromePropsSpy.mock.calls.at(-1)?.[0] as { onFlythrough: () => void };
    act(() => {
      lastProps.onFlythrough();
    });

    expect(playFlythrough).toHaveBeenCalledTimes(1);
    const signal = vi.mocked(playFlythrough).mock.calls[0]?.[3] as AbortSignal;
    expect(signal).toBeInstanceOf(AbortSignal);
    expect(signal.aborted).toBe(false);

    unmount();
    expect(signal.aborted).toBe(true);
  });
});
