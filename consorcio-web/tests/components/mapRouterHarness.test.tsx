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
import { describe, expect, it, vi } from 'vitest';

// Uses the shared manual mock: `__mocks__/@tanstack/react-router.ts`.
// No factory on purpose — that is what selects the `__mocks__` file.
vi.mock('@tanstack/react-router');

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
