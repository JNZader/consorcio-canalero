import type maplibregl from 'maplibre-gl';
import { describe, expect, it, vi } from 'vitest';

import {
  COMPARISON_RENDERABLE_UI_LAYER_IDS,
  type ComparisonMapConstructor,
  type ComparisonOverlaySyncInputs,
  createComparisonOverlayController,
  syncComparisonVectorLayers,
} from '../../src/components/map2d/comparisonOverlay';
import {
  LAYER_RENDER_REGISTRY,
  RENDERABLE_UI_LAYER_IDS,
} from '../../src/components/map2d/layerRenderRegistry';
import { WATERWAY_DEFS } from '../../src/hooks/useWaterways';
import { ALL_ETAPAS } from '../../src/types/canales';

interface FakeMapHarness {
  map: maplibregl.Map;
  layers: Map<string, { id: string }>;
  setLayoutProperty: ReturnType<typeof vi.fn>;
  setPaintProperty: ReturnType<typeof vi.fn>;
  remove: ReturnType<typeof vi.fn>;
  off: ReturnType<typeof vi.fn>;
  triggerLoad: () => void;
}

function createFakeMap(initialStyleLoaded = true): FakeMapHarness {
  const sources = new Map<string, { setData: ReturnType<typeof vi.fn> }>();
  const layers = new Map<string, { id: string }>();
  const listeners = new Map<string, Set<() => void>>();
  let styleLoaded = initialStyleLoaded;

  const setLayoutProperty = vi.fn();
  const setPaintProperty = vi.fn();
  const remove = vi.fn();
  const off = vi.fn((event: string, listener: () => void) => {
    listeners.get(event)?.delete(listener);
  });

  const map = {
    getSource: (id: string) => sources.get(id),
    addSource: (id: string) => {
      sources.set(id, { setData: vi.fn() });
    },
    removeSource: (id: string) => {
      sources.delete(id);
    },
    getLayer: (id: string) => layers.get(id),
    addLayer: (layer: { id: string }) => {
      layers.set(layer.id, layer);
    },
    removeLayer: (id: string) => {
      layers.delete(id);
    },
    getStyle: () => ({ layers: [...layers.values()] }),
    setLayoutProperty,
    setPaintProperty,
    setFilter: vi.fn(),
    moveLayer: vi.fn(),
    jumpTo: vi.fn(),
    resize: vi.fn(),
    remove,
    isStyleLoaded: () => styleLoaded,
    once: (event: string, listener: () => void) => {
      const eventListeners = listeners.get(event) ?? new Set<() => void>();
      eventListeners.add(listener);
      listeners.set(event, eventListeners);
    },
    off,
    // A real MapLibre `Map` always exposes these; the mock was simply
    // incomplete. `syncCatastroLayers` now registers hover handlers so the
    // clickable parcel fill gets a pointer cursor, which needs both.
    on: vi.fn(),
    getCanvas: vi.fn(() => ({ style: {} as Record<string, string> })),
  } as unknown as maplibregl.Map;

  return {
    map,
    layers,
    setLayoutProperty,
    setPaintProperty,
    remove,
    off,
    triggerLoad: () => {
      styleLoaded = true;
      const eventListeners = [...(listeners.get('load') ?? [])];
      listeners.delete('load');
      for (const listener of eventListeners) listener();
    },
  };
}

function createInputs(
  overrides: Partial<ComparisonOverlaySyncInputs> = {}
): ComparisonOverlaySyncInputs {
  const visible = Object.fromEntries(RENDERABLE_UI_LAYER_IDS.map((id) => [id, true])) as Record<
    string,
    boolean
  >;

  return {
    leftTileUrl: 'https://tiles.test/left/{z}/{x}/{y}.png',
    vectorVisibility: {
      ...visible,
      waterways_rio_tercero: true,
      waterways_canal_desviador: true,
      waterways_canal_litin_tortugas: true,
      waterways_arroyo_algodon: true,
      waterways_arroyo_las_mojarras: true,
    },
    waterwaysDefs: WATERWAY_DEFS,
    soilCollection: { type: 'FeatureCollection', features: [] },
    roadsCollection: { type: 'FeatureCollection', features: [] },
    basins: { type: 'FeatureCollection', features: [] },
    approvedZonesCollection: { type: 'FeatureCollection', features: [] },
    pilarVerde: null,
    canales: {
      relevados: { type: 'FeatureCollection', features: [] },
      propuestas: { type: 'FeatureCollection', features: [] },
      visibleRelevadoIds: [],
      visiblePropuestaIds: [],
      activeEtapas: ALL_ETAPAS,
    },
    escuelasCollection: null,
    opacityByLayer: {},
    orderByLayer: [],
    ...overrides,
  };
}

describe('comparison overlay vector coverage', () => {
  it('is set-equal to the canonical renderable UI layer registry', () => {
    expect([...COMPARISON_RENDERABLE_UI_LAYER_IDS].sort()).toEqual(
      [...RENDERABLE_UI_LAYER_IDS].sort()
    );
  });

  it('mounts every concrete layer represented by the canonical registry', () => {
    const harness = createFakeMap();

    syncComparisonVectorLayers(harness.map, createInputs());

    for (const id of RENDERABLE_UI_LAYER_IDS) {
      for (const layer of LAYER_RENDER_REGISTRY[id].mlLayers) {
        expect(harness.layers.has(layer.id), `comparison omitted ${id}/${layer.id}`).toBe(true);
      }
    }
  });

  it('reacts to subfilters, opacity and order on the same map', () => {
    const harness = createFakeMap();
    const inputs = createInputs({
      vectorVisibility: {
        ...createInputs().vectorVisibility,
        waterways_arroyo_algodon: false,
      },
      opacityByLayer: { roads: 0.5 },
      orderByLayer: [...RENDERABLE_UI_LAYER_IDS],
    });

    syncComparisonVectorLayers(harness.map, inputs);

    expect(harness.setLayoutProperty).toHaveBeenCalledWith(
      'map2d-waterways-arroyo-algodon-line',
      'visibility',
      'none'
    );
    expect(harness.setPaintProperty).toHaveBeenCalledWith('map2d-roads-line', 'line-opacity', 0.45);
  });
});

describe('comparison overlay lifecycle', () => {
  it('keeps one overlay instance across reactive updates and applies the latest pre-load inputs', () => {
    const overlay = createFakeMap(false);
    const baseOn = vi.fn();
    const baseOff = vi.fn();
    const baseMap = {
      getCenter: () => ({ toArray: () => [-62.6, -32.5] }),
      getZoom: () => 10,
      getBearing: () => 0,
      getPitch: () => 0,
      on: baseOn,
      off: baseOff,
    } as unknown as maplibregl.Map;

    const mapConstructor = vi.fn(function ComparisonMapMock() {
      return overlay.map;
    }) as unknown as ComparisonMapConstructor;

    const controller = createComparisonOverlayController({
      mapConstructor,
      container: document.createElement('div'),
      baseMap,
      initialInputs: createInputs(),
    });

    controller.update(
      createInputs({
        vectorVisibility: {
          ...createInputs().vectorVisibility,
          roads: false,
        },
        opacityByLayer: { roads: 0.5 },
      })
    );

    expect(mapConstructor).toHaveBeenCalledTimes(1);
    expect(overlay.setLayoutProperty).not.toHaveBeenCalled();

    overlay.triggerLoad();

    expect(overlay.setLayoutProperty).toHaveBeenCalledWith(
      'map2d-roads-line',
      'visibility',
      'none'
    );
    expect(overlay.setPaintProperty).toHaveBeenCalledWith('map2d-roads-line', 'line-opacity', 0.45);

    controller.update(
      createInputs({
        opacityByLayer: { roads: 0.25 },
      })
    );

    expect(mapConstructor).toHaveBeenCalledTimes(1);
    expect(overlay.setPaintProperty).toHaveBeenLastCalledWith(
      'map2d-roads-line',
      'line-opacity',
      0.225
    );

    controller.dispose();

    expect(baseOff).toHaveBeenCalledWith('move', expect.any(Function));
    expect(baseOff).toHaveBeenCalledWith('resize', expect.any(Function));
    expect(overlay.off).toHaveBeenCalledWith('load', expect.any(Function));
    expect(overlay.remove).toHaveBeenCalledTimes(1);
  });
});
