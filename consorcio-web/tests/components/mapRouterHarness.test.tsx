/**
 * Regression guard for the unit-test harness router regression (H6).
 *
 * After the Rules-of-Hooks repair, `useHazardUrlState` calls
 * `getRouteApi('/mapa').useSearch()` / `useNavigate({ from: '/mapa' })`
 * unconditionally. Any test rendering `MapaMapLibre` / `MapaContent` without a
 * TanStack Router context threw `Cannot read properties of null (reading
 * 'stores')`. The shared `__mocks__/@tanstack/react-router.ts` mock gives those
 * components a stable router context, and this file locks that contract: the map
 * components MUST render under the test harness.
 */

import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import MapaMapLibre from '../../src/components/MapaMapLibre';
import { MapaContent } from '../../src/components/MapaPage';

// Uses the shared manual mock: `__mocks__/@tanstack/react-router.ts`.
vi.mock('@tanstack/react-router');

// happy-dom has no WebGL; stub MapLibre GL the same way the other map suites do.
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

// `MapaContent` reads dashboard stats; keep the query from hitting the network
// while preserving the rest of the `query` module (e.g. `queryKeys`).
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

function renderUnderHarness(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MantineProvider env="test">{ui}</MantineProvider>
    </QueryClientProvider>
  );
}

describe('map components render under the test router harness (H6 regression)', () => {
  it('MapaMapLibre renders the workspace under the shared router mock', () => {
    renderUnderHarness(<MapaMapLibre />);
    // `map-workspace` is mounted only after the router hooks resolve — proof the
    // unconditional `useSearch` / `useNavigate` no longer crash without a real
    // RouterProvider.
    expect(screen.getByTestId('map-workspace')).toBeInTheDocument();
  });

  it('MapaContent renders the page heading under the shared router mock', () => {
    mockDashboardStats.mockReturnValue({ stats: null, isLoading: true });
    renderUnderHarness(<MapaContent />);
    expect(
      screen.getByRole('heading', { name: /Mapa Interactivo/i })
    ).toBeInTheDocument();
  });
});
