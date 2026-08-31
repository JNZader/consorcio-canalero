/**
 * Analysis tools behind login (owner's rule, 2026-08).
 *
 * The three ficha ENTRY POINTS — "Dibujar polígono", "Canal" and the sticky
 * "Selección múltiple" toggle — are for logged-in users only. Everything else the
 * map offers stays public: navigation, zoom, compass, fullscreen, DESCARGAR,
 * MEDIR (named explicitly by the owner), CAPAS, and the ficha itself on a parcel
 * click.
 *
 * Two invariants this file defends, and they pull in opposite directions:
 *   1. anonymous → the three buttons are ABSENT FROM THE DOM (not disabled: the
 *      owner wants them not to be SEEN), while medir/descargar/capas survive;
 *   2. the ctrl+clic gesture keeps accumulating parcels WITHOUT a session — the
 *      toggle is a shortcut for the gesture, so hiding the button must not hide
 *      the capability.
 *
 * This is a render gate, NOT an authz boundary: the ficha endpoints stay public
 * behind their own caps. Nothing here should ever grow into a token check.
 */

import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, renderHook, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

/** Same MapLibre stub as `mapTopBarPlacement.test.tsx`: happy-dom has no WebGL. */
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

vi.mock('../../src/hooks/useHazardUrlState', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../src/hooks/useHazardUrlState')>();
  return {
    ...actual,
    useHazardUrlState: () => ({
      basin: null,
      hazard: false,
      precipMonth: 'anual',
      resetToDefaults: vi.fn(),
      riskClasses: ['Bajo', 'Medio', 'Alto', 'Crítico'],
      setBasin: vi.fn(),
      setHazard: vi.fn(),
      setPrecipMonth: vi.fn(),
      setRiskClasses: vi.fn(),
    }),
  };
});

import MapaMapLibre from '../../src/components/MapaMapLibre';
import { useAnalysisToolsGate } from '../../src/components/map2d/useAnalysisToolsGate';
import {
  FICHA_PARCELAS_SETTLE_MS,
  useFichaInteraction,
} from '../../src/components/map2d/useFichaInteraction';
import type { ParcelaResuelta } from '../../src/components/map2d/useMapInteractionEffects';
import { useAuthStore } from '../../src/stores/authStore';

const DESKTOP = { width: 1280, height: 800 };
const PX_PER_EM = 16;

/** Per-query evaluation against one simulated viewport (see mapTopBarPlacement). */
function matchesQuery(query: string, viewport: { width: number; height: number }): boolean {
  return query
    .split(' and ')
    .map((part) => part.trim().replace(/^\(/, '').replace(/\)$/, ''))
    .every((feature) => {
      const [name, rawValue] = feature.split(':').map((chunk) => chunk.trim());
      const value = Number.parseFloat(rawValue) * (rawValue.endsWith('px') ? 1 : PX_PER_EM);
      switch (name) {
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

function renderMap() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MantineProvider env="test">
        <MapaMapLibre />
      </MantineProvider>
    </QueryClientProvider>
  );
}

/** The real store, driven directly — no module mock, so the criterion under test
 * is the production `useIsAuthenticated` (`user && !loading && initialized`). */
function setAuth(state: {
  user: { id: string; email: string } | null;
  initialized: boolean;
  loading?: boolean;
}) {
  useAuthStore.setState({
    user: state.user,
    loading: state.loading ?? false,
    initialized: state.initialized,
  });
}

const USER = { id: 'u1', email: 'socio@consorcio.test' };
const LOGGED_IN = { user: USER, initialized: true };
const ANONYMOUS = { user: null, initialized: true };
/**
 * The ONLY state that can actually flash, and the reason the criterion is three
 * terms and not `!!user`.
 *
 * `persist` restores `user` from `cc-auth-storage` (`authStore.ts:242-245`)
 * SYNCHRONOUSLY on the first render, while `initialized` is still false and
 * `loading` still true (`authStore.ts:54-62`) — the session has NOT been
 * confirmed against the backend yet and may well be a dead token. A gate reading
 * `!!user` alone would paint the three tools on that first frame and yank them
 * one tick later.
 */
const PERSIST_REHYDRATED = { user: USER, initialized: false, loading: true };

beforeEach(() => {
  mockViewport(DESKTOP);
  // The map hooks fetch public assets; rejections are already degraded there.
  vi.spyOn(console, 'error').mockImplementation(() => undefined);
});

afterEach(() => {
  setAuth(ANONYMOUS);
  vi.restoreAllMocks();
});

describe('map analysis tools — login gate', () => {
  it('anonymous: the three analysis buttons are ABSENT from the DOM', () => {
    setAuth(ANONYMOUS);
    renderMap();

    expect(screen.queryByLabelText('Dibujar polígono')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Seleccionar canal')).not.toBeInTheDocument();
    expect(screen.queryByTestId('ficha-multi-select-toggle')).not.toBeInTheDocument();
  });

  it('anonymous: medir, descargar and capas are untouched', () => {
    setAuth(ANONYMOUS);
    renderMap();

    expect(screen.getByLabelText('Medir')).toBeInTheDocument();
    expect(screen.getByLabelText('Exportar')).toBeInTheDocument();
    expect(screen.getByTestId('map-controls-tree')).toBeInTheDocument();
  });

  it('authenticated: the three analysis buttons are rendered', () => {
    setAuth(LOGGED_IN);
    renderMap();

    expect(screen.getByLabelText('Dibujar polígono')).toBeInTheDocument();
    expect(screen.getByLabelText('Seleccionar canal')).toBeInTheDocument();
    expect(screen.getByTestId('ficha-multi-select-toggle')).toBeInTheDocument();
  });

  it('a REHYDRATED-but-unconfirmed user does not paint the tools (anti-flash)', () => {
    // The regression this pins: a gate that read `!!user` would be green on an
    // anonymous visitor and still flash here, because `persist` hands us a
    // truthy user before the session is confirmed. Showing the tools first and
    // yanking them one tick later is a visible glitch AND a promise a dead token
    // cannot keep — hidden→shown is the only acceptable direction.
    setAuth(PERSIST_REHYDRATED);
    renderMap();

    expect(screen.queryByLabelText('Dibujar polígono')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Seleccionar canal')).not.toBeInTheDocument();
    expect(screen.queryByTestId('ficha-multi-select-toggle')).not.toBeInTheDocument();
  });
});

/* -------------------------------------------------------------------------- */
/*  Session lost mid-use                                                       */
/* -------------------------------------------------------------------------- */

function parcela(nomenclatura: string): ParcelaResuelta {
  return {
    nomenclatura,
    nroCuenta: '110123',
    props: {
      nomenclatura,
      nroCuenta: '110123',
      desigOficial: 'Lote 4',
      superficieHa: '25.4',
      departamento: 'General San Martín',
      pedania: 'Arroyo Algodón',
      tipoParcela: 'rural',
    },
  };
}

/** Mounts the coordinator and the gate together, exactly as `MapaMapLibre` does. */
function useGatedFicha() {
  const ficha = useFichaInteraction('idle', () => {});
  const toolProps = useAnalysisToolsGate({
    drawing: ficha.state.drawing,
    canalMode: ficha.state.canalMode,
    multiSelect: ficha.state.multiSelect,
    stopDraw: ficha.stopDraw,
    stopCanal: ficha.stopCanal,
    setMultiSelect: ficha.setMultiSelect,
    onToggleFichaDraw: () => {},
    onToggleFichaCanal: () => {},
    onToggleFichaMultiSelect: () => {},
  });
  return { ficha, toolProps };
}

describe('useAnalysisToolsGate — session lost mid-use', () => {
  it('logging out during a draw session leaves the mode clean', () => {
    setAuth(LOGGED_IN);
    const { result } = renderHook(() => useGatedFicha());

    act(() => result.current.ficha.startDraw());
    expect(result.current.ficha.state.drawing).toBe(true);
    expect(result.current.ficha.interactionMode).toBe('ficha-dibujo');

    act(() => setAuth(ANONYMOUS));

    // Same exit Escape performs (`stopDraw`): without it `DrawControl` stays
    // mounted owning map clicks with no visible button left to leave it.
    expect(result.current.ficha.state.drawing).toBe(false);
    expect(result.current.ficha.interactionMode).toBe('idle');
    expect(result.current.toolProps.onToggleFichaDraw).toBeUndefined();
  });

  it('logging out during canal mode and sticky multi-select clears both', () => {
    setAuth(LOGGED_IN);
    const { result } = renderHook(() => useGatedFicha());

    act(() => result.current.ficha.startCanal());
    act(() => result.current.ficha.setMultiSelect(true));
    expect(result.current.ficha.state.canalMode).toBe(true);
    expect(result.current.ficha.state.multiSelect).toBe(true);

    act(() => setAuth(ANONYMOUS));

    expect(result.current.ficha.state.canalMode).toBe(false);
    expect(result.current.ficha.state.multiSelect).toBe(false);
    expect(result.current.ficha.interactionMode).toBe('idle');
  });
});

/* -------------------------------------------------------------------------- */
/*  The gesture stays public                                                   */
/* -------------------------------------------------------------------------- */

describe('ctrl+clic accumulation — public on purpose', () => {
  // The multi-parcel REQUEST is debounced by `FICHA_PARCELAS_SETTLE_MS`, so an
  // assertion on `state.parcelas` alone cannot tell "the anonymous visitor gets
  // the real multi-parcel ficha" from "an array grew and no analysis ever ran".
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('produces the real tipo=parcelas ficha with NO session, toggle hidden', () => {
    setAuth(ANONYMOUS);
    const { result } = renderHook(() => useGatedFicha());

    // The button is gone…
    expect(result.current.toolProps.onToggleFichaMultiSelect).toBeUndefined();

    // …and the gesture still works: `additive` comes from the DOM modifier
    // (`useMapInteractionEffects`), never from the auth store.
    act(() => result.current.ficha.resolveParcela(parcela('13-06-01-0201'), true));
    act(() => result.current.ficha.resolveParcela(parcela('13-06-01-0202'), true));

    expect(result.current.ficha.state.parcelas).toEqual(['13-06-01-0201', '13-06-01-0202']);

    act(() => {
      vi.advanceTimersByTime(FICHA_PARCELAS_SETTLE_MS);
    });

    // The user-visible contract, end to end: the union is actually requested.
    expect(result.current.ficha.tipo).toBe('parcelas');
    expect(result.current.ficha.request).toEqual({
      tipo: 'parcelas',
      nomenclaturas: ['13-06-01-0201', '13-06-01-0202'],
    });
  });

  it('a plain click still resolves a single parcel with no session', () => {
    setAuth(ANONYMOUS);
    const { result } = renderHook(() => useGatedFicha());

    act(() => result.current.ficha.resolveParcela(parcela('13-06-01-0201')));

    // Not debounced (pre-T4 interaction), so the request is there immediately.
    expect(result.current.ficha.state.parcelas).toEqual(['13-06-01-0201']);
    expect(result.current.ficha.tipo).toBe('parcela');
    expect(result.current.ficha.request).toEqual({
      tipo: 'parcela',
      nomenclatura: '13-06-01-0201',
    });
  });
});
