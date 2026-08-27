import { act, renderHook } from '@testing-library/react';
import type { Polygon } from 'geojson';
import type { MutableRefObject } from 'react';
import type maplibregl from 'maplibre-gl';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useHazardMapState } from '../../src/components/map2d/useHazardMapState';

const CANONICAL_LAYER_IDS = [
  'flood_risk',
  'drainage_need',
  'soil',
  'canales_relevados',
  'basins',
  'precip_normal',
];

const mocks = vi.hoisted(() => ({
  gateOpen: true,
  url: {
    hazard: false,
    basin: null,
    riskClasses: ['Bajo', 'Medio', 'Alto', 'Crítico'],
    precipMonth: 'anual',
  },
  shared: {
    map2d: { visibleVectors: { roads: true, soil: false } },
    setVectorVisibility: vi.fn(),
  },
  hazardStore: {
    minimizeForFicha: vi.fn(),
    reset: vi.fn(),
    pendingBasinZoom: false,
    setPendingBasinZoom: vi.fn(),
  },
}));

vi.mock('../../src/hooks/useMultiHazardGate', () => ({
  useMultiHazardGate: () => mocks.gateOpen,
}));

vi.mock('../../src/hooks/useHazardUrlState', () => ({
  useHazardUrlState: () => mocks.url,
  // Re-exported for mapRasterOverlayHelpers, which imports the constant from
  // this module — the full-module mock would otherwise leave it undefined.
  HAZARD_RISK_CLASSES: ['Bajo', 'Medio', 'Alto', 'Crítico'],
}));

vi.mock('../../src/stores/mapLayerSyncStore', () => ({
  useMapLayerSyncStore: Object.assign(
    (selector: (state: typeof mocks.shared) => unknown) => selector(mocks.shared),
    { getState: () => mocks.shared }
  ),
}));

vi.mock('../../src/stores/hazardMapStore', () => ({
  useHazardMapStore: (selector: (state: typeof mocks.hazardStore) => unknown) =>
    selector(mocks.hazardStore),
}));

function createMapRef(): MutableRefObject<maplibregl.Map | null> {
  return { current: null };
}

describe('useHazardMapState', () => {
  beforeEach(() => {
    mocks.gateOpen = true;
    mocks.url.hazard = false;
    mocks.shared.map2d.visibleVectors = { roads: true, soil: false };
    vi.clearAllMocks();
  });

  it('captures once and applies the canonical stack only on an inactive-to-active transition', () => {
    const { rerender } = renderHook(
      ({ hazard }) => {
        mocks.url.hazard = hazard;
        return useHazardMapState({ mapRef: createMapRef(), mapReady: false });
      },
      { initialProps: { hazard: false } }
    );

    act(() => rerender({ hazard: true }));
    act(() => rerender({ hazard: true }));

    for (const layerId of CANONICAL_LAYER_IDS) {
      expect(mocks.shared.setVectorVisibility).toHaveBeenCalledWith('map2d', layerId, true);
    }
    expect(mocks.shared.setVectorVisibility).toHaveBeenCalledTimes(CANONICAL_LAYER_IDS.length);
  });

  it('restores the captured visibility when hazard mode becomes inactive', () => {
    const { rerender } = renderHook(
      ({ hazard }) => {
        mocks.url.hazard = hazard;
        return useHazardMapState({ mapRef: createMapRef(), mapReady: false });
      },
      { initialProps: { hazard: true } }
    );

    vi.clearAllMocks();
    act(() => rerender({ hazard: false }));

    expect(mocks.shared.setVectorVisibility).toHaveBeenCalledWith('map2d', 'roads', true);
    expect(mocks.shared.setVectorVisibility).toHaveBeenCalledWith('map2d', 'soil', false);
    expect(mocks.hazardStore.reset).toHaveBeenCalledOnce();
  });

  it('turns absent canonical layers off while restoring captured values exactly', () => {
    mocks.shared.map2d.visibleVectors = { roads: true, flood_risk: true, soil: false };

    const { rerender } = renderHook(
      ({ hazard }) => {
        mocks.url.hazard = hazard;
        return useHazardMapState({ mapRef: createMapRef(), mapReady: false });
      },
      { initialProps: { hazard: true } }
    );

    vi.clearAllMocks();
    act(() => rerender({ hazard: false }));

    for (const layerId of CANONICAL_LAYER_IDS) {
      expect(mocks.shared.setVectorVisibility).toHaveBeenCalledWith(
        'map2d',
        layerId,
        layerId === 'flood_risk'
      );
    }
    expect(mocks.shared.setVectorVisibility).toHaveBeenCalledWith('map2d', 'roads', true);
    expect(mocks.shared.setVectorVisibility).toHaveBeenCalledWith('map2d', 'soil', false);
  });

  it('does not mutate visibility while the gate is closed', () => {
    mocks.gateOpen = false;
    mocks.url.hazard = true;

    renderHook(() => useHazardMapState({ mapRef: createMapRef(), mapReady: false }));

    expect(mocks.shared.setVectorVisibility).not.toHaveBeenCalled();
  });
});

describe('JD-B3B-001 — unmount while hazard is active', () => {
  beforeEach(() => {
    mocks.gateOpen = true;
    mocks.url.hazard = false;
    mocks.shared.map2d.visibleVectors = { roads: true, soil: false, canales_relevados: true };
    vi.clearAllMocks();
  });

  it('restores the exact captured visibility on unmount, turning absent canonical layers off', () => {
    const { unmount } = renderHook(() => {
      mocks.url.hazard = true;
      return useHazardMapState({ mapRef: createMapRef(), mapReady: false });
    });

    vi.clearAllMocks();
    unmount();

    for (const layerId of CANONICAL_LAYER_IDS) {
      expect(mocks.shared.setVectorVisibility).toHaveBeenCalledWith(
        'map2d',
        layerId,
        layerId === 'canales_relevados'
      );
    }
    expect(mocks.shared.setVectorVisibility).toHaveBeenCalledWith('map2d', 'roads', true);
    expect(mocks.hazardStore.reset).not.toHaveBeenCalled();
  });

  it('does not restore a second time when unmount follows an active→inactive exit', () => {
    const { rerender, unmount } = renderHook(
      ({ hazard }) => {
        mocks.url.hazard = hazard;
        return useHazardMapState({ mapRef: createMapRef(), mapReady: false });
      },
      { initialProps: { hazard: true } }
    );

    act(() => rerender({ hazard: false }));
    vi.clearAllMocks();
    unmount();

    expect(mocks.shared.setVectorVisibility).not.toHaveBeenCalled();
  });

  it('writes nothing when unmounted while hazard is inactive', () => {
    const { unmount } = renderHook(() =>
      useHazardMapState({ mapRef: createMapRef(), mapReady: false })
    );

    unmount();

    expect(mocks.shared.setVectorVisibility).not.toHaveBeenCalled();
  });
});

describe('JD-B3B-003 — basin zoom on selection', () => {
  const RING = [
    [-62.75, -32.66],
    [-62.35, -32.66],
    [-62.35, -32.44],
    [-62.75, -32.44],
    [-62.75, -32.66],
  ];
  const basinOptions = [
    {
      id: 'basin-1',
      label: 'Cuenca 1',
      geometry: { type: 'Polygon', coordinates: [RING] } as Polygon,
    },
    { id: 'basin-2', label: 'Cuenca 2', geometry: null },
  ];

  function createZoomMap() {
    return {
      fitBounds: vi.fn(),
      once: vi.fn(),
      off: vi.fn(),
      getLayer: vi.fn(() => undefined),
      getSource: vi.fn(() => undefined),
      getContainer: () => ({ clientWidth: 800, clientHeight: 600 }),
    };
  }

  function renderZoom(map: ReturnType<typeof createZoomMap>) {
    return renderHook(() =>
      useHazardMapState({
        mapRef: { current: map as unknown as maplibregl.Map },
        mapReady: true,
        basinOptions,
      })
    );
  }

  beforeEach(() => {
    mocks.gateOpen = true;
    mocks.url.hazard = true;
    mocks.url.basin = null;
    mocks.shared.map2d.visibleVectors = { roads: true };
    vi.clearAllMocks();
  });

  it('fits bounded bounds and settles pendingBasinZoom for a selected basin with geometry', () => {
    mocks.url.basin = 'basin-1';
    const map = createZoomMap();
    const { unmount } = renderZoom(map);

    expect(map.fitBounds).toHaveBeenCalledWith(
      [
        [-62.75, -32.66],
        [-62.35, -32.44],
      ],
      expect.objectContaining({ maxZoom: 13, padding: 48 })
    );
    expect(mocks.hazardStore.setPendingBasinZoom).toHaveBeenCalledWith(true);

    const settle = map.once.mock.calls.find(([event]) => event === 'moveend')?.[1] as () => void;
    settle();
    expect(mocks.hazardStore.setPendingBasinZoom).toHaveBeenLastCalledWith(false);

    // Unmount also settles via the cleanup path, without a second fit.
    vi.clearAllMocks();
    unmount();
    expect(map.off).toHaveBeenCalledWith('moveend', expect.any(Function));
    expect(mocks.hazardStore.setPendingBasinZoom).toHaveBeenCalledWith(false);
  });

  it('does not zoom for "Mostrar todo" (null basin) or a geometry-less selection', () => {
    const nullBasinMap = createZoomMap();
    renderZoom(nullBasinMap);
    expect(nullBasinMap.fitBounds).not.toHaveBeenCalled();

    mocks.url.basin = 'basin-2';
    const noGeometryMap = createZoomMap();
    renderZoom(noGeometryMap);

    expect(noGeometryMap.fitBounds).not.toHaveBeenCalled();
    expect(mocks.hazardStore.setPendingBasinZoom).not.toHaveBeenCalled();
  });
});
