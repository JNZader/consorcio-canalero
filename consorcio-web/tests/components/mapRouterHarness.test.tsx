/**
 * Contract lock for the shared unit-test router harness.
 *
 * `src/hooks/useHazardUrlState.ts` calls `useNavigate()` and
 * `useSearch({ from: '/mapa' })` UNCONDITIONALLY. Any suite that renders a tree
 * reaching that hook without a `RouterProvider` dies with
 * `Cannot read properties of null (reading 'stores')`. The shared manual mock
 * `__mocks__/@tanstack/react-router.ts` is the harness that prevents it, and
 * this file is its detector:
 *
 *   1. the mock's exported shape still matches how `src/` calls the router
 *      (proved by driving the real `useHazardUrlState` through it, not by
 *      asserting on the mock's own literals);
 *   2. the two map entry points — `MapaMapLibre` and `MapaContent` — still
 *      render under the harness, so the hazard viewer can be wired into them
 *      without taking every map suite down with it.
 *
 * If the router API usage in `src/` drifts (a different hook, a `getRouteApi`
 * route API, a search shape the mock does not model), test 1 fails HERE instead
 * of failing as an opaque null-context crash spread over every map suite.
 */

import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, renderHook, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

// Uses the shared manual mock: `__mocks__/@tanstack/react-router.ts`.
// No factory on purpose — that is what selects the `__mocks__` file.
vi.mock('@tanstack/react-router');

/**
 * The comparison divider lives in the DESKTOP layout: `MapaMapLibreView`
 * renders the canvas and its floating overlays inside `{isDesktop && …}`.
 * happy-dom reports a mobile media query, so without this the assertion below
 * would be vacuous — it would pass whether or not the view switched.
 */
vi.mock('../../src/components/map2d/MapWorkspace', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../src/components/map2d/MapWorkspace')>()),
  useMapWorkspaceDesktop: () => true,
}));

/** Same MapLibre stub as `mapAnalysisToolsLoginGate.test.tsx`: happy-dom has no WebGL. */
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

// `MapaContent` reads dashboard stats; keep the query off the network while
// preserving the rest of the `query` module (e.g. `queryKeys`).
const { mockDashboardStats } = vi.hoisted(() => ({
  mockDashboardStats: vi.fn(),
}));
vi.mock('../../src/lib/query', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../src/lib/query')>();
  return {
    ...actual,
    useDashboardStats: mockDashboardStats,
  };
});

import MapaMapLibre from '../../src/components/MapaMapLibre';
import { MapaContent } from '../../src/components/MapaPage';
import {
  HAZARD_DEFAULT_PRECIP_MONTH,
  HAZARD_RISK_CLASSES,
  useHazardUrlState,
} from '../../src/hooks/useHazardUrlState';

function renderUnderHarness(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MantineProvider env="test">{ui}</MantineProvider>
    </QueryClientProvider>
  );
}

describe('shared router test harness (__mocks__/@tanstack/react-router)', () => {
  it('satisfies the router API the hazard URL hook actually calls', () => {
    // Drives the REAL hook: it calls `useNavigate()` + `useSearch({ from: '/mapa' })`.
    // Without the harness this throws `reading 'stores'`.
    const { result } = renderHook(() => useHazardUrlState());

    // Default-search behavior, i.e. the mock returns an object the parser can read.
    expect(result.current.hazard).toBe(false);
    expect(result.current.basin).toBeNull();
    expect(result.current.riskClasses).toEqual([...HAZARD_RISK_CLASSES]);
    expect(result.current.precipMonth).toBe(HAZARD_DEFAULT_PRECIP_MONTH);
    // The setters exist and are callable — `useNavigate()` returned a function.
    expect(() => result.current.setHazard(true)).not.toThrow();
  });

  it('renders MapaMapLibre under the shared router mock', () => {
    renderUnderHarness(<MapaMapLibre />);
    expect(screen.getByTestId('map-workspace')).toBeInTheDocument();
  });

  it('renders MapaContent under the shared router mock', () => {
    mockDashboardStats.mockReturnValue({ stats: null, isLoading: true });
    renderUnderHarness(<MapaContent />);
    expect(screen.getByRole('heading', { name: /Mapa Interactivo/i })).toBeInTheDocument();
  });
});

/**
 * Entering the map shows the visitor's chosen image (or the base map), never a
 * comparison they did not just ask for. A saved pair is RESTORED into state; it
 * must not switch the view — the `Base | Imagen | Comparar` selector is one
 * click away. Regression: the comparison auto-flip effect fired on the async
 * backend restore and overrode the chosen image.
 */
describe('view mode when entering the map', () => {
  const COMPARISON_KEY = 'consorcio_image_comparison';
  const SELECTED_IMAGE_KEY = 'consorcio_selected_image';

  // A fresh `selected_at` on purpose: a stale tile sends the listener to the
  // backend to refresh it, which is not what these cases are about.
  // The host is pinned to Earth Engine because `isValidSelectedImage` rejects
  // any other one — a rejected fixture would make this suite vacuous.
  const image = {
    tile_url: 'https://earthengine.googleapis.com/v1/projects/test/tiles/{z}/{x}/{y}',
    target_date: '2026-03-01',
    sensor: 'Sentinel-2',
    visualization: 'true_color',
    visualization_description: 'Natural color',
    collection: 'sentinel-2',
    images_count: 3,
    selected_at: new Date().toISOString(),
  };

  const savedPair = JSON.stringify({ enabled: true, left: image, right: image });

  afterEach(() => {
    vi.mocked(localStorage.getItem).mockReset();
    vi.mocked(localStorage.setItem).mockReset();
    vi.mocked(localStorage.removeItem).mockReset();
  });

  it('does not switch to comparison just because a saved pair was restored', () => {
    // `tests/setup.ts` replaces `window.localStorage` with a vitest mock, so the
    // restore has to be driven THROUGH the mock: a real `setItem` stores
    // nothing, the listener finds no pair, and this assertion would pass
    // whether or not the view switched.
    vi.mocked(localStorage.getItem).mockImplementation((key) =>
      key === COMPARISON_KEY ? savedPair : null
    );

    renderUnderHarness(<MapaMapLibre />);

    expect(screen.queryByTestId('map-comparison-divider')).not.toBeInTheDocument();
  });

  it('keeps the chosen image when a saved pair is restored too', () => {
    vi.mocked(localStorage.getItem).mockImplementation((key) => {
      if (key === SELECTED_IMAGE_KEY) return JSON.stringify(image);
      if (key === COMPARISON_KEY) return savedPair;
      return null;
    });

    renderUnderHarness(<MapaMapLibre />);

    expect(screen.queryByTestId('map-comparison-divider')).not.toBeInTheDocument();
  });
});
