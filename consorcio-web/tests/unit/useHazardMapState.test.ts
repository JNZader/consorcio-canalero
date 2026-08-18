/**
 * useHazardMapState.test.ts
 *
 * Integration-level tests for the Multi-Hazard map state hook.
 * Verifies that enabling hazard mode applies the canonical layer stack,
 * that non-operator users are gated out, and that the map-side basin filter
 * is built/removed as the basin selection changes.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import type { Feature } from 'geojson';
import type { MutableRefObject } from 'react';
import type maplibregl from 'maplibre-gl';
import { useHazardMapState } from '../../src/components/map2d/useHazardMapState';
import type { HazardUrlState } from '../../src/hooks/useHazardUrlState';

const CANONICAL_STACK = [
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
    isHazardActive: false,
    basin: null,
    riskClasses: [],
    precipMonth: 'anual',
    setHazard: vi.fn(),
    setBasin: vi.fn(),
    setRiskClasses: vi.fn(),
    setPrecipMonth: vi.fn(),
    resetToDefaults: vi.fn(),
  } as HazardUrlState,
  store: {
    panelOpen: true,
    mobileExpanded: false,
    pendingBasinZoom: false,
    setPanelOpen: vi.fn(),
    setMobileExpanded: vi.fn(),
    setPendingBasinZoom: vi.fn(),
    minimizeForFicha: vi.fn(),
    reset: vi.fn(),
  },
  shared: {
    map2d: {
      visibleVectors: {
        roads: true,
        waterways: true,
        catastro: true,
        soil: false,
      } as Record<string, boolean>,
    },
    setVectorVisibility: vi.fn(),
  },
}));

function createFakeMap() {
  const layers = new Map<string, unknown>();
  const sources = new Map<string, unknown>();
  const handlers = new Map<string, Array<() => void>>();
  return {
    getLayer: (id: string) => layers.get(id) ?? undefined,
    getSource: (id: string) => sources.get(id) ?? undefined,
    addSource: vi.fn((id: string, source: unknown) => sources.set(id, source)),
    removeSource: vi.fn((id: string) => sources.delete(id)),
    addLayer: vi.fn((layer: { id: string }) => layers.set(layer.id, layer)),
    removeLayer: vi.fn((id: string) => layers.delete(id)),
    setFilter: vi.fn(),
    setLayoutProperty: vi.fn(),
    setPaintProperty: vi.fn(),
    moveLayer: vi.fn(),
    fitBounds: vi.fn(),
    once: vi.fn((event: string, fn: () => void) => {
      const list = handlers.get(event) ?? [];
      list.push(fn);
      handlers.set(event, list);
    }),
    off: vi.fn(),
    getCanvas: () => ({ style: { cursor: '' } }),
    getStyle: () => ({ layers: [] }),
  };
}

vi.mock('../../src/hooks/useMultiHazardGate', () => ({
  useMultiHazardGate: () => mocks.gateOpen,
}));

vi.mock('../../src/hooks/useHazardUrlState', () => ({
  useHazardUrlState: () => mocks.url,
  HAZARD_DEFAULT_LAYERS: [
    'flood_risk',
    'drainage_need',
    'soil',
    'canales_relevados',
    'basins',
    'precip_normal',
  ],
  HAZARD_DEFAULT_RISK_CLASSES: ['Bajo', 'Medio', 'Alto', 'Crítico'],
  HAZARD_DEFAULT_PRECIP_MONTH: 'anual',
  RISK_CLASS_LABELS: ['Bajo', 'Medio', 'Alto', 'Crítico'],
}));

vi.mock('../../src/stores/hazardMapStore', () => ({
  useHazardMapStore: () => mocks.store,
}));

vi.mock('../../src/stores/mapLayerSyncStore', () => ({
  useMapLayerSyncStore: (selector: (state: typeof mocks.shared) => unknown) =>
    selector(mocks.shared),
}));

describe('useHazardMapState', () => {
  beforeEach(() => {
    mocks.gateOpen = true;
    mocks.url.hazard = false;
    mocks.url.isHazardActive = false;
    mocks.url.basin = null;
    mocks.url.riskClasses = [];
    mocks.url.precipMonth = 'anual';
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('applies the canonical layer stack when hazard mode turns on', () => {
    const map = createFakeMap();
    const mapRef = { current: map as unknown as maplibregl.Map } as MutableRefObject<maplibregl.Map>;

    const { rerender } = renderHook(
      ({ active }) => {
        mocks.url.hazard = active;
        mocks.url.isHazardActive = active && mocks.gateOpen;
        return useHazardMapState({
          mapRef,
          mapReady: true,
          basins: { type: 'FeatureCollection', features: [] },
          allGeoLayers: [],
          fichaActive: false,
        });
      },
      { initialProps: { active: false } }
    );

    expect(mocks.shared.setVectorVisibility).not.toHaveBeenCalledWith(
      'map2d',
      'flood_risk',
      true
    );

    act(() => rerender({ active: true }));

    for (const layerId of CANONICAL_STACK) {
      expect(mocks.shared.setVectorVisibility).toHaveBeenCalledWith('map2d', layerId, true);
    }
  });

  it('does not force the canonical stack when hazard mode is off', () => {
    const map = createFakeMap();
    const mapRef = { current: map as unknown as maplibregl.Map } as MutableRefObject<maplibregl.Map>;

    renderHook(() =>
      useHazardMapState({
        mapRef,
        mapReady: true,
        basins: { type: 'FeatureCollection', features: [] },
        allGeoLayers: [],
        fichaActive: false,
      })
    );

    expect(mocks.shared.setVectorVisibility).not.toHaveBeenCalledWith(
      'map2d',
      'flood_risk',
      true
    );
    expect(mocks.shared.setVectorVisibility).not.toHaveBeenCalledWith(
      'map2d',
      'precip_normal',
      true
    );
  });

  it('ignores hazard=1 when the user lacks the admin/operador role', () => {
    mocks.gateOpen = false;
    mocks.url.hazard = true;
    mocks.url.isHazardActive = false;

    const map = createFakeMap();
    const mapRef = { current: map as unknown as maplibregl.Map } as MutableRefObject<maplibregl.Map>;

    renderHook(() =>
      useHazardMapState({
        mapRef,
        mapReady: true,
        basins: { type: 'FeatureCollection', features: [] },
        allGeoLayers: [],
        fichaActive: false,
      })
    );

    expect(mocks.shared.setVectorVisibility).not.toHaveBeenCalledWith(
      'map2d',
      'flood_risk',
      true
    );
    expect(mocks.url.setRiskClasses).not.toHaveBeenCalled();
  });

  it('sets a basin filter on the catastro layer when a basin is selected', () => {
    const basin = {
      type: 'Feature',
      geometry: {
        type: 'Polygon',
        coordinates: [
          [
            [-62.5, -32.5],
            [-62.4, -32.5],
            [-62.4, -32.6],
            [-62.5, -32.6],
            [-62.5, -32.5],
          ],
        ],
      },
      properties: { id: 'cuenca-1', nombre: 'Cuenca Test' },
    };

    const map = createFakeMap();
    map.getLayer = (id: string) => (id === 'map2d-catastro-fill' || id === 'map2d-catastro-line' ? {} : undefined);
    const mapRef = { current: map as unknown as maplibregl.Map } as MutableRefObject<maplibregl.Map>;

    const { rerender } = renderHook(
      ({ basinId }: { basinId: string | null }) => {
        mocks.url.hazard = true;
        mocks.url.isHazardActive = true;
        mocks.url.basin = basinId;
        return useHazardMapState({
          mapRef,
          mapReady: true,
          basins: { type: 'FeatureCollection', features: [basin as Feature] },
          allGeoLayers: [],
          fichaActive: false,
        });
      },
      { initialProps: { basinId: null } }
    );

    // Initial mount with no basin clears any existing filter by writing
    // `undefined` to both catastro layers.
    expect(map.setFilter).toHaveBeenCalledWith('map2d-catastro-fill', undefined);
    expect(map.setFilter).toHaveBeenCalledWith('map2d-catastro-line', undefined);

    act(() => rerender({ basinId: 'cuenca-1' }));

    const fillCalls = map.setFilter.mock.calls.filter(
      ([layerId]) => layerId === 'map2d-catastro-fill'
    );
    const lastFillCall = fillCalls[fillCalls.length - 1];
    expect(lastFillCall[1]).toEqual(
      expect.arrayContaining(['within', expect.objectContaining({ type: 'Feature' })])
    );
  });
});
