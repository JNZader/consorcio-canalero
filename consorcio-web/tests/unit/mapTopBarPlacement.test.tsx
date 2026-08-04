/**
 * mapTopBarPlacement.test.tsx — portrait rework.
 *
 * The base-layer controls used to have TWO homes at once: a floating
 * `.mapTopBar` over the canvas, and (potentially) `LayerControlsPanel`'s own
 * "Base" section. On a 360px-wide phone that bar wrapped to ~149px of chrome
 * over a 500px canvas — a fifth of the map spent on a control the layers Drawer
 * could host for free.
 *
 * The bar is now DESKTOP-ONLY, gated on the very same `useMapWorkspaceDesktop()`
 * that `MapWorkspace` uses for sidebar-vs-Drawer, and the mobile branch hands
 * the identical `baseControls` to `LayerControlsPanel` instead. The invariant
 * this file defends is "exactly one base-layer control, at either breakpoint" —
 * a duplicate would be two segmented controls fighting over one piece of state.
 */

import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * MapLibre needs a real WebGL context, which happy-dom does not have. Only the
 * surface `useMapInitialization` touches is stubbed — this file asserts on the
 * React tree around the canvas, never on the map itself.
 */
vi.mock('maplibre-gl', () => {
  class MapMock {
    on() {}
    off() {}
    once() {}
    remove() {}
    addControl() {}
    removeControl() {}
    getCanvas() {
      return { style: {} };
    }
    isStyleLoaded() {
      return false;
    }
    getStyle() {
      return { layers: [] };
    }
    getSource() {
      return undefined;
    }
    getLayer() {
      return undefined;
    }
    setStyle() {}
    resize() {}
  }
  const maplibregl = {
    Map: MapMock,
    NavigationControl: class {},
    ScaleControl: class {},
    FullscreenControl: class {},
    Popup: class {
      setLngLat() {
        return this;
      }
      setHTML() {
        return this;
      }
      addTo() {
        return this;
      }
      remove() {}
    },
    addProtocol: () => {},
    removeProtocol: () => {},
  };
  return { default: maplibregl, ...maplibregl };
});

import MapaMapLibre from '../../src/components/MapaMapLibre';
import { MAP_DESKTOP_MEDIA_QUERY } from '../../src/components/map2d/MapWorkspace';

const BASE_CONTROL_LABEL = 'Seleccionar capa base';

/** A simulated phone: below BOTH the 48em desktop gate and the 62em sheet gate. */
const MOBILE = { width: 360, height: 800 };
/** A simulated laptop: above both. */
const DESKTOP = { width: 1280, height: 800 };

const PX_PER_EM = 16;

/**
 * Evaluate a media query against a simulated viewport.
 *
 * REL-004 — this used to be a blanket `matches: isDesktop`, one answer for every
 * query, on the (wrong) assumption that this tree asks exactly one. It asks TWO:
 * `MapWorkspace` asks `MAP_DESKTOP_MEDIA_QUERY`, and `MapUiPanels` asks
 * `(max-width: 62em)` to choose floating cards vs the bottom sheet. Those two
 * move in OPPOSITE directions with viewport width, so a single blanket answer
 * inverted the second one every time: the "desktop" run rendered desktop chrome
 * with mobile sheets, the "mobile" run rendered mobile chrome with floating
 * cards. Both trees are hybrids that exist at no real viewport. Answering per
 * query from one simulated viewport is what makes the tree coherent — and a
 * third query added later gets a coherent answer too, instead of a coin flip.
 *
 * Supports only the features this tree actually asks for (`min/max-width`,
 * `min/max-height` in `em` or `px`, plus Mantine's `prefers-color-scheme`);
 * anything else THROWS instead of silently defaulting, because a silent default
 * is the very bug being fixed. The throw already earned its keep: it surfaced
 * the `prefers-color-scheme` probe that a blanket mock had been answering
 * `true` (i.e. dark) without anyone noticing.
 */
function matchesQuery(query: string, viewport: { width: number; height: number }): boolean {
  return query
    .split(' and ')
    .map((part) => part.trim().replace(/^\(/, '').replace(/\)$/, ''))
    .every((feature) => {
      const [name, rawValue] = feature.split(':').map((chunk) => chunk.trim());
      const value = Number.parseFloat(rawValue) * (rawValue.endsWith('px') ? 1 : PX_PER_EM);
      switch (name) {
        // Not a viewport feature and not this file's subject: `MantineProvider`
        // asks it on mount to pick the color scheme. Pinned to light (the app
        // default) rather than routed through the throw below.
        case 'prefers-color-scheme':
          return false;
        case 'min-width':
          return viewport.width >= value;
        case 'max-width':
          return viewport.width <= value;
        case 'min-height':
          return viewport.height >= value;
        case 'max-height':
          return viewport.height <= value;
        default:
          throw new Error(`matchesQuery: unsupported media feature «${feature}»`);
      }
    });
}

function mockViewport(viewport: { width: number; height: number }) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: matchesQuery(query, viewport),
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

function renderMap(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MantineProvider env="test">{ui}</MantineProvider>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  // The map hooks fetch public assets; every rejection is already logged and
  // degraded by the hooks themselves (see `useCanales` / `useWaterways`).
  vi.spyOn(console, 'error').mockImplementation(() => undefined);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('base-layer controls placement (portrait rework)', () => {
  it('asks for the SHARED desktop query, not a private copy', () => {
    mockViewport(DESKTOP);
    renderMap(<MapaMapLibre />);

    const queries = vi.mocked(window.matchMedia).mock.calls.map(([query]) => query);
    expect(queries).toContain(MAP_DESKTOP_MEDIA_QUERY);
  });

  it('desktop: renders the floating top bar and flags the grid row', () => {
    mockViewport(DESKTOP);
    renderMap(<MapaMapLibre />);

    expect(screen.getByTestId('map-top-bar')).toBeInTheDocument();
    expect(screen.getByTestId('map-workspace')).toHaveAttribute('data-topbar', 'true');
  });

  it('desktop: EXACTLY ONE base-layer control on screen', () => {
    mockViewport(DESKTOP);
    renderMap(<MapaMapLibre />);

    // The sidebar is expanded and its `controls` tree is mounted, so a
    // `LayerControlsPanel` that also received `baseLayer` would show up here.
    expect(screen.getByTestId('map-controls-tree')).toBeInTheDocument();
    expect(screen.getAllByLabelText(BASE_CONTROL_LABEL)).toHaveLength(1);
  });

  it('mobile: NO floating top bar — the grid row collapses', () => {
    mockViewport(MOBILE);
    renderMap(<MapaMapLibre />);

    expect(screen.queryByTestId('map-top-bar')).not.toBeInTheDocument();
    expect(screen.getByTestId('map-workspace')).toHaveAttribute('data-topbar', 'false');
  });

  it('mobile: the base-layer control lives in the Drawer instead', () => {
    mockViewport(MOBILE);
    renderMap(<MapaMapLibre />);

    // Nothing is dropped — it MOVED. Closed Drawer → controls not mounted yet.
    expect(screen.queryByLabelText(BASE_CONTROL_LABEL)).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId('map-workspace-burger'));

    const tree = screen.getByTestId('map-controls-tree');
    expect(tree).toBeInTheDocument();
    const controls = screen.getAllByLabelText(BASE_CONTROL_LABEL);
    expect(controls).toHaveLength(1);
    expect(tree).toContainElement(controls[0]);
  });
});
