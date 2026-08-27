import { act, renderHook } from '@testing-library/react';
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
  },
}));

vi.mock('../../src/hooks/useMultiHazardGate', () => ({
  useMultiHazardGate: () => mocks.gateOpen,
}));

vi.mock('../../src/hooks/useHazardUrlState', () => ({
  useHazardUrlState: () => mocks.url,
}));

vi.mock('../../src/stores/mapLayerSyncStore', () => ({
  useMapLayerSyncStore: (selector: (state: typeof mocks.shared) => unknown) =>
    selector(mocks.shared),
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
