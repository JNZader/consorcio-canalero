import type * as maplibregl from 'maplibre-gl';
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
import { ROAD_FLOW_ALL_KINDS_VISIBLE } from '../../src/components/map2d/roadFlowLayers';
import { WATERWAY_DEFS } from '../../src/hooks/useWaterways';
import {
  SOIL_PMTILES_ARCHIVE_KEY,
  setSoilPmtilesArchiveKeyForTests,
} from '../../src/lib/soilPmtiles';
import { ALL_ETAPAS } from '../../src/types/canales';

const RASTER_ONLY_UI_LAYER_IDS = new Set(['precip_normal']);

/**
 * Renderable UI ids that are vectors but are DELIBERATELY absent from the
 * comparison overlay.
 *
 * ⚠️ THE RULE, RATIFIED BY THE OWNER ON 2026-08-23: ⚠️
 * *"toda capa cuyos datos requieren panel autenticado + disclaimer queda fuera
 * del comparador"* — any layer whose data requires an authenticated panel plus
 * a disclaimer stays out of the comparator.
 *
 * That is a RULE, not a per-layer excuse: the comparison slider renders map
 * paint and nothing else, so a layer that can only be read honestly alongside a
 * panel (and the sentence that panel carries) has no honest rendering there.
 * Membership of this set is therefore decided by the rule, and a member that
 * does NOT satisfy it is an oversight, exactly as an unlisted layer would be.
 *
 *   - `road_flow` (flujo-caminos, design D6) — satisfies BOTH halves: its route
 *     is `require_admin_or_operator`, the selector entry is role-gated, and
 *     RFA-R4 requires the non-hydraulic disclaimer to accompany the ranking
 *     wherever it is read (`RoadFlowDisclaimer`, surfaces `lista`/`hoja`/`chip`).
 *     Rendering the points in the slider would show a ranking stripped of the
 *     statement of what it is not.
 *
 * Corrected 2026-10-15 (owner report: "el izquierdo oculta algunas capas
 * mientras el derecho muestra todas las habilitadas"). The four layers that were
 * listed here next to `road_flow` do NOT satisfy the rule's disclaimer half —
 * they are operator-only data, not rankings — and they were absent only because
 * the comparison view never fetched them. `red_vial_oficial` additionally
 * stopped being staff-only the same day (published public and ON by default), so
 * the "requires an authenticated panel" half no longer holds for it either. They
 * are now synced like every other vector layer, behind the SAME role gate the
 * base map uses, so a visitor who cannot see them on the right cannot see them
 * on the left.
 */
const NOT_IN_COMPARISON_UI_LAYER_IDS = new Set(['road_flow']);

const COMPARISON_VECTOR_UI_LAYER_IDS = RENDERABLE_UI_LAYER_IDS.filter(
  (id) => !RASTER_ONLY_UI_LAYER_IDS.has(id) && !NOT_IN_COMPARISON_UI_LAYER_IDS.has(id)
);

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
    // The overlay map has its OWN image registry: it never inherits the base
    // map's, so `hasImage` is false until this map adds the flow arrow itself.
    hasImage: vi.fn(() => false),
    addImage: vi.fn(),
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
    redVialOficial: { shouldMount: true },
    caminosHuecos: { shouldMount: true },
    puntosInteres: { type: 'FeatureCollection', features: [] },
    zona: { type: 'FeatureCollection', features: [] },
    roadFlow: {
      crossings: { type: 'FeatureCollection', features: [] },
      totalFlujoNatural: 0,
      kinds: ROAD_FLOW_ALL_KINDS_VISIBLE,
      flechas: { type: 'FeatureCollection', features: [] },
    },
    ...overrides,
  };
}

describe('comparison overlay vector coverage', () => {
  it('excludes raster-only UI ids from the vector comparison overlay', () => {
    expect([...COMPARISON_RENDERABLE_UI_LAYER_IDS].sort()).toEqual(
      [...COMPARISON_VECTOR_UI_LAYER_IDS].sort()
    );
  });

  it('mounts every concrete comparison-vector layer', () => {
    setSoilPmtilesArchiveKeyForTests(SOIL_PMTILES_ARCHIVE_KEY);
    const harness = createFakeMap();

    syncComparisonVectorLayers(harness.map, createInputs());

    for (const id of COMPARISON_RENDERABLE_UI_LAYER_IDS) {
      for (const layer of LAYER_RENDER_REGISTRY[id].mlLayers) {
        expect(harness.layers.has(layer.id), `comparison omitted ${id}/${layer.id}`).toBe(true);
      }
    }
  });

  it('reacts to subfilters, opacity and order on the same map', () => {
    setSoilPmtilesArchiveKeyForTests(SOIL_PMTILES_ARCHIVE_KEY);
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

  it('hides the operator-only overlays when their flag is off, exactly like the base map', () => {
    setSoilPmtilesArchiveKeyForTests(SOIL_PMTILES_ARCHIVE_KEY);
    const harness = createFakeMap();
    const inputs = createInputs({
      vectorVisibility: {
        ...createInputs().vectorVisibility,
        red_vial_oficial: false,
        caminos_huecos: false,
        puntos_interes: false,
      },
    });

    syncComparisonVectorLayers(harness.map, inputs);

    // The panes cannot disagree on WHICH layers are shown: the same flags that
    // hide a layer on the base map hide it here.
    for (const id of ['red_vial_oficial', 'caminos_huecos', 'puntos_interes'] as const) {
      for (const layer of LAYER_RENDER_REGISTRY[id].mlLayers) {
        expect(harness.setLayoutProperty).toHaveBeenCalledWith(layer.id, 'visibility', 'none');
      }
    }
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
    expect(overlay.setLayoutProperty).toHaveBeenCalledWith(
      'map2d-roads-label',
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
      'map2d-roads-label',
      'text-opacity',
      0.2375
    );

    controller.dispose();

    expect(baseOff).toHaveBeenCalledWith('move', expect.any(Function));
    expect(baseOff).toHaveBeenCalledWith('resize', expect.any(Function));
    expect(overlay.off).toHaveBeenCalledWith('load', expect.any(Function));
    expect(overlay.remove).toHaveBeenCalledTimes(1);
  });
});
