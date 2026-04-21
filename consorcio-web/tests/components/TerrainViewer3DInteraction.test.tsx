/**
 * TerrainViewer3DInteraction.test.tsx
 *
 * Phase 5 (Batch F) of `pilar-verde-y-canales-3d` — wires the 3D viewer's
 * click handler + the shared 2D `<InfoPanel>` overlay into the terrain
 * chrome. Strict mirror of the 2D `useMapInteractionEffects` blueprint
 * (ref: `components/map2d/useMapInteractionEffects.ts`).
 *
 * Contract asserted by these tests:
 *   1. Click handler registers on `map.on('click', ...)` after the map is
 *      ready and `queryRenderedFeatures` is invoked with a `±5px` bbox
 *      (NOT a single point) and a `layers` array filtered to existing
 *      layers.
 *   2. Clickable-layers list includes at least one canal + one BPA layer
 *      id — mirror of the 2D precedence ordering.
 *   3. When `selectedFeatures` is non-empty, `<InfoPanel>` mounts with the
 *      stacked sections (one per feature) and sits above the chrome (the
 *      shared `.infoPanel` CSS class enforces `position: absolute; z-index:
 *      1000`, so we simply assert the component is reachable in the DOM).
 *   4. Feature-type routing:
 *        - BPA (has `años_bpa`) → `<BpaCard>` branch.
 *        - Canal (has `estado === "relevado"` / `"propuesto"`) →
 *          `<CanalCard>` branch.
 *        - Generic (e.g. a catastro feature with `nro_cuenta` only and no
 *          BPA match) → whitelisted property-dump branch.
 *   5. Clicking the close button clears `selectedFeatures` and the panel
 *      UNMOUNTS (not just hidden).
 *
 * `queryRenderedFeatures` is NOT spied on via a `vi.fn()` mock of the
 * MapLibre module at the test bootstrap because the viewer's click handler
 * is registered inside a `useEffect` that only runs after the map's `load`
 * event. The MapStub below fires `load` synchronously and captures the
 * installed click handler so the test can invoke it with a synthetic
 * MouseEvent point and inspect the `queryRenderedFeatures` spy args.
 */

import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { Feature } from 'geojson';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

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
// MapLibre stub — captures the click handler + exposes a spy for
// `queryRenderedFeatures` so the test can drive both contract assertions:
//   - bbox shape passed to `queryRenderedFeatures`
//   - layers list passed to `queryRenderedFeatures`
// `on('load', cb)` fires synchronously so the viewer's `ready` flag flips.
// ---------------------------------------------------------------------------

type ClickHandler = (event: {
  point: { x: number; y: number };
  lngLat: { lng: number; lat: number };
}) => void;

interface MapStubState {
  clickHandler: ClickHandler | null;
  queryRenderedFeaturesSpy: ReturnType<typeof vi.fn>;
  nextQueryResult: Feature[];
  existingLayerIds: Set<string>;
}

let mapStubState: MapStubState = {
  clickHandler: null,
  queryRenderedFeaturesSpy: vi.fn(),
  nextQueryResult: [],
  existingLayerIds: new Set(),
};

vi.mock('maplibre-gl', () => {
  class MapStub {
    constructor() {
      // nothing — mapStubState persists across constructors for the suite
    }
    on(event: string, handler: unknown) {
      if (event === 'load' && typeof handler === 'function') {
        (handler as () => void)();
      }
      if (event === 'click' && typeof handler === 'function') {
        mapStubState.clickHandler = handler as ClickHandler;
      }
    }
    off(event: string, handler: unknown) {
      if (event === 'click' && mapStubState.clickHandler === handler) {
        mapStubState.clickHandler = null;
      }
    }
    once() {}
    addControl() {}
    remove() {
      mapStubState.clickHandler = null;
    }
    isStyleLoaded() {
      return true;
    }
    getLayer(id: string) {
      return mapStubState.existingLayerIds.has(id) ? ({ id } as unknown) : undefined;
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
    queryRenderedFeatures(
      bbox: unknown,
      options: { layers?: string[] } | undefined,
    ): Feature[] {
      mapStubState.queryRenderedFeaturesSpy(bbox, options);
      return mapStubState.nextQueryResult;
    }
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

function resetMapStub() {
  mapStubState = {
    clickHandler: null,
    queryRenderedFeaturesSpy: vi.fn(),
    nextQueryResult: [],
    existingLayerIds: new Set([
      // The viewer's `buildClickableLayers3D()` should return layer ids that
      // exist on the map. For the bbox/layers assertions we simulate the
      // canales + BPA fills being present so they survive the
      // `map.getLayer(id)` filter inside the handler.
      'pilar_verde_bpa_historico-fill',
      'canales-propuestos-line',
      'canales-relevados-line',
    ]),
  };
}

function openLayerPanel() {
  // Chrome renders the toggles+legends panels inside a collapsible
  // `{showLayerPanel && ...}` block. The click handler + InfoPanel overlay
  // live in the outer Paper so they do NOT require the panel to be open —
  // but opening it is useful for the z-index visual assertion.
  const btn = screen.getByRole('button', { name: /Ver capas y overlays 3D/i });
  return userEvent.click(btn);
}

// ---------------------------------------------------------------------------
// Suite
// ---------------------------------------------------------------------------

describe('TerrainViewer3D — click handler + InfoPanel overlay (Phase 5)', () => {
  beforeEach(() => {
    useCanalesMock.mockReset();
    usePilarVerdeMock.mockReset();
    resetMapStub();

    useCanalesMock.mockReturnValue({
      relevados: null,
      propuestas: null,
      index: null,
      isLoading: false,
      isError: false,
    });
    usePilarVerdeMock.mockReturnValue({
      data: null,
      loading: false,
      error: null,
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  // -------------------------------------------------------------------------
  // 5.1 — bbox + layers contract on queryRenderedFeatures
  // -------------------------------------------------------------------------

  it('calls queryRenderedFeatures with a ±5px bbox (NOT single point) and a filtered layers list', async () => {
    const { default: TerrainViewer3D } = await import(
      '../../src/components/terrain/TerrainViewer3D'
    );

    renderViewer(<TerrainViewer3D demLayerId="dem-uuid" />);

    expect(mapStubState.clickHandler).toBeTypeOf('function');

    await act(async () => {
      mapStubState.clickHandler?.({
        point: { x: 100, y: 200 },
        lngLat: { lng: -63.1, lat: -32.1 },
      });
    });

    expect(mapStubState.queryRenderedFeaturesSpy).toHaveBeenCalledTimes(1);
    const [bboxArg, optionsArg] = mapStubState.queryRenderedFeaturesSpy.mock.calls[0];

    // bbox is an array of two points [x-5, y-5] and [x+5, y+5] (NOT a
    // single {x,y} point).
    expect(Array.isArray(bboxArg)).toBe(true);
    expect(bboxArg).toEqual([
      [95, 195],
      [105, 205],
    ]);

    // layers list filtered by existing ids — the three we seeded in
    // `existingLayerIds` MUST appear; any id passed to buildClickableLayers3D
    // but not present in the map must be stripped.
    expect(optionsArg).toBeTruthy();
    expect(Array.isArray(optionsArg.layers)).toBe(true);
    expect(optionsArg.layers).toEqual(
      expect.arrayContaining([
        'pilar_verde_bpa_historico-fill',
        'canales-propuestos-line',
        'canales-relevados-line',
      ]),
    );
    // And NO id we marked as missing leaks through — we did NOT seed
    // `soil-fill`, `catastro-fill`, or `roads-line`, so they must not be in
    // the array.
    expect(optionsArg.layers).not.toContain('soil-fill');
    expect(optionsArg.layers).not.toContain('catastro-fill');
    expect(optionsArg.layers).not.toContain('roads-line');
  });

  // -------------------------------------------------------------------------
  // 5.3 — InfoPanel renders when selectedFeatures is non-empty
  // -------------------------------------------------------------------------

  it('renders <InfoPanel> overlay with z-index ≥ 1000 when selectedFeatures is non-empty', async () => {
    const bpaFeature: Feature = {
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [0, 0] },
      properties: {
        años_bpa: 3,
        años_lista: ['2023', '2024', '2025'],
        bpa_activa_2025: true,
        nro_cuenta: '99-01-1234567/8',
        n_explotacion_ultima: 'Estancia Test',
      },
    };
    mapStubState.nextQueryResult = [bpaFeature];

    const { default: TerrainViewer3D } = await import(
      '../../src/components/terrain/TerrainViewer3D'
    );

    renderViewer(<TerrainViewer3D demLayerId="dem-uuid" />);

    await act(async () => {
      mapStubState.clickHandler?.({
        point: { x: 50, y: 50 },
        lngLat: { lng: 0, lat: 0 },
      });
    });

    // The shared 2D `<InfoPanel>` renders one `[data-testid="info-panel-feature-section"]`
    // per feature, under the title "Informacion".
    expect(screen.getByText('Informacion')).toBeTruthy();
    expect(
      screen.getAllByTestId('info-panel-feature-section').length,
    ).toBeGreaterThan(0);

    // The panel uses the shared CSS module class `.infoPanel` which carries
    // `position: absolute; z-index: 1000; ...`. We cannot probe computed
    // styles under JSDOM reliably, but we CAN assert the element carries the
    // module-hashed class that encodes those rules. The class name starts
    // with `_infoPanel_` in CSS Modules hash output; that prefix is the
    // stable marker CSS Modules always emits.
    const panel = screen.getByText('Informacion').closest('[class*="infoPanel"]');
    expect(panel).not.toBeNull();
  });

  // -------------------------------------------------------------------------
  // 5.5a — BPA feature routes to BpaCard branch inside InfoPanel
  // -------------------------------------------------------------------------

  it('renders <BpaCard> when the clicked feature carries años_bpa (BPA branch)', async () => {
    const bpaFeature: Feature = {
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [0, 0] },
      properties: {
        años_bpa: 5,
        años_lista: ['2020', '2021', '2022', '2023', '2024'],
        bpa_activa_2025: true,
        nro_cuenta: '99-01-2222222/2',
      },
    };
    mapStubState.nextQueryResult = [bpaFeature];

    const { default: TerrainViewer3D } = await import(
      '../../src/components/terrain/TerrainViewer3D'
    );

    renderViewer(<TerrainViewer3D demLayerId="dem-uuid" />);

    await act(async () => {
      mapStubState.clickHandler?.({
        point: { x: 10, y: 10 },
        lngLat: { lng: 0, lat: 0 },
      });
    });

    // BpaCard sets `data-testid="bpa-card"` on its root Paper (shared 2D
    // component — see `components/map2d/BpaCard.tsx`). If that testId
    // changes, this assertion needs to follow.
    expect(screen.getByTestId('bpa-card')).toBeTruthy();
  });

  // -------------------------------------------------------------------------
  // 5.5b — Canal feature routes to CanalCard branch
  // -------------------------------------------------------------------------

  it('renders <CanalCard> when the clicked feature has estado="relevado"', async () => {
    const canalFeature: Feature = {
      type: 'Feature',
      geometry: { type: 'LineString', coordinates: [[0, 0], [1, 1]] },
      properties: {
        estado: 'relevado',
        nombre: 'Canal Test',
        codigo: 'CT-1',
        longitud_m: 1500,
        source_style: 'readec',
      },
    };
    mapStubState.nextQueryResult = [canalFeature];

    const { default: TerrainViewer3D } = await import(
      '../../src/components/terrain/TerrainViewer3D'
    );

    renderViewer(<TerrainViewer3D demLayerId="dem-uuid" />);

    await act(async () => {
      mapStubState.clickHandler?.({
        point: { x: 10, y: 10 },
        lngLat: { lng: 0, lat: 0 },
      });
    });

    // CanalCard sets `data-testid="canal-card"` — see
    // `components/map2d/CanalCard.tsx`.
    expect(screen.getByTestId('canal-card')).toBeTruthy();
  });

  // -------------------------------------------------------------------------
  // 5.5c — Generic feature falls back to the whitelist property dump
  // -------------------------------------------------------------------------

  it('renders whitelisted properties when feature has no BPA/Canal signal', async () => {
    const catastroFeature: Feature = {
      type: 'Feature',
      geometry: { type: 'Polygon', coordinates: [] },
      properties: {
        // No `años_bpa`, no `estado === relevado/propuesto` → fallback to
        // the generic whitelist branch. We intentionally include a
        // whitelisted field (`nro_cuenta`) so the branch renders
        // something visible.
        nro_cuenta: '99-01-9999999/9',
      },
    };
    // Attach a `layer.id` so `getDisplayableProperties(layer.id, props)`
    // can consult the whitelist registered for `map2d-catastro-fill`.
    (catastroFeature as Feature & { layer?: { id: string } }).layer = {
      id: 'map2d-catastro-fill',
    };
    mapStubState.nextQueryResult = [catastroFeature];

    const { default: TerrainViewer3D } = await import(
      '../../src/components/terrain/TerrainViewer3D'
    );

    renderViewer(<TerrainViewer3D demLayerId="dem-uuid" />);

    await act(async () => {
      mapStubState.clickHandler?.({
        point: { x: 10, y: 10 },
        lngLat: { lng: 0, lat: 0 },
      });
    });

    // Generic branch renders one `<Stack>` with `data-testid="info-panel-feature-section"`.
    // Neither BpaCard nor CanalCard should be in the DOM.
    expect(screen.getByTestId('info-panel-feature-section')).toBeTruthy();
    expect(screen.queryByTestId('bpa-card')).toBeNull();
    expect(screen.queryByTestId('canal-card')).toBeNull();
  });

  // -------------------------------------------------------------------------
  // 5.6 — closing InfoPanel clears selectedFeatures
  // -------------------------------------------------------------------------

  it('unmounts <InfoPanel> when the user closes it', async () => {
    const bpaFeature: Feature = {
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [0, 0] },
      properties: {
        años_bpa: 1,
        años_lista: ['2025'],
        bpa_activa_2025: true,
      },
    };
    mapStubState.nextQueryResult = [bpaFeature];

    const { default: TerrainViewer3D } = await import(
      '../../src/components/terrain/TerrainViewer3D'
    );

    renderViewer(<TerrainViewer3D demLayerId="dem-uuid" />);

    await act(async () => {
      mapStubState.clickHandler?.({
        point: { x: 30, y: 30 },
        lngLat: { lng: 0, lat: 0 },
      });
    });

    expect(screen.getByText('Informacion')).toBeTruthy();

    const closeBtn = screen.getByRole('button', {
      name: /Cerrar panel de informacion/i,
    });
    await userEvent.click(closeBtn);

    expect(screen.queryByText('Informacion')).toBeNull();
  });

  // -------------------------------------------------------------------------
  // Opening the layer panel still works alongside InfoPanel (regression guard)
  // -------------------------------------------------------------------------

  it('keeps the chrome toggles button functional when InfoPanel is open', async () => {
    const canalFeature: Feature = {
      type: 'Feature',
      geometry: { type: 'LineString', coordinates: [[0, 0], [1, 1]] },
      properties: { estado: 'propuesto', nombre: 'X' },
    };
    mapStubState.nextQueryResult = [canalFeature];

    const { default: TerrainViewer3D } = await import(
      '../../src/components/terrain/TerrainViewer3D'
    );

    renderViewer(<TerrainViewer3D demLayerId="dem-uuid" />);

    await act(async () => {
      mapStubState.clickHandler?.({
        point: { x: 10, y: 10 },
        lngLat: { lng: 0, lat: 0 },
      });
    });

    expect(screen.getByTestId('canal-card')).toBeTruthy();
    // Panel can still be opened — button coexists with InfoPanel overlay.
    await openLayerPanel();
    // No assertion on specific panel content — the test succeeds if the
    // toggle click doesn't throw, proving the two overlays don't interfere.
  });
});
