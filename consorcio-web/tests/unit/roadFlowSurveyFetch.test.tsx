/**
 * roadFlowSurveyFetch.test.tsx — flujo-caminos S4, fix-forward DISC-5.
 *
 * The "Relevar" button used to die in silence. `TramoSurveySheet` mounted on
 * the segment DETAIL, so a failed GET produced no sheet at all: no spinner, no
 * error, no retry — and the selected `tramoRef` stayed set, so tapping the same
 * row again wrote the same state, changed nothing and (with `retry: false`)
 * never re-issued the read either.
 *
 * This suite pins the hook side of the fix against a REAL `QueryClient` with
 * the api module stubbed: the read is observable while it is in flight, its
 * failure is observable with an exit, and asking for the SAME segment a second
 * time re-issues it.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useRoadFlowWiring } from '../../src/components/map2d/useRoadFlowWiring';
import { fetchTramoRelevamiento } from '../../src/lib/api/relevamiento';
import type { TramoRelevamientoDetalle } from '../../src/lib/api/relevamiento';

vi.mock('../../src/lib/api/relevamiento', async () => {
  const actual = await vi.importActual<typeof import('../../src/lib/api/relevamiento')>(
    '../../src/lib/api/relevamiento'
  );
  return {
    ...actual,
    fetchTramoRelevamiento: vi.fn(),
    fetchCobertura: vi.fn(),
    registrarRelevamiento: vi.fn(),
  };
});

vi.mock('../../src/hooks/useAuth', () => ({
  useAuth: () => ({ isStaff: true }),
}));

const TRAMO = 'RV-0001';

const DETALLE: TramoRelevamientoDetalle = {
  tramo_ref: TRAMO,
  vigente: null,
  historial: [],
  candidata: null,
};

function wrapper(client: QueryClient) {
  return function Wrapper({ children }: { readonly children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

function renderWiring(client: QueryClient) {
  return renderHook(
    () =>
      useRoadFlowWiring({
        // No map in this suite: the survey read does not touch it, and the
        // gesture hook is a no-op without one.
        mapRef: { current: null },
        mapReady: false,
        // The layer is OFF so the crossings/coverage reads stay idle — this is
        // about the segment read only.
        active: false,
        geoLayers: [],
        onDeactivate: () => {},
      }),
    { wrapper: wrapper(client) }
  );
}

let client: QueryClient;

beforeEach(() => {
  client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
});

afterEach(() => {
  client.clear();
  vi.clearAllMocks();
});

describe('la lectura del tramo es observable de punta a punta', () => {
  it('una lectura fallida deja el error a la vista, con el tramo todavía seleccionado', async () => {
    vi.mocked(fetchTramoRelevamiento).mockRejectedValue(new Error('502 Bad Gateway'));

    const { result } = renderWiring(client);
    act(() => result.current.onSurveyTramo(TRAMO));

    await waitFor(() => expect(result.current.tramoError).not.toBeNull());

    // The ref is what mounts the sheet: it MUST survive the failure, or the
    // operator gets the silent button back.
    expect(result.current.tramoRef).toBe(TRAMO);
    expect(result.current.tramoDetalle).toBeNull();
    expect(result.current.tramoError?.message).toBe('502 Bad Gateway');
  });

  it('"Reintentar" vuelve a pedir el mismo tramo y lo resuelve', async () => {
    vi.mocked(fetchTramoRelevamiento).mockRejectedValueOnce(new Error('502 Bad Gateway'));

    const { result } = renderWiring(client);
    act(() => result.current.onSurveyTramo(TRAMO));
    await waitFor(() => expect(result.current.tramoError).not.toBeNull());

    vi.mocked(fetchTramoRelevamiento).mockResolvedValue(DETALLE);
    act(() => result.current.onRetryTramoSurvey());

    await waitFor(() => expect(result.current.tramoDetalle).toEqual(DETALLE));
    expect(result.current.tramoError).toBeNull();
    expect(fetchTramoRelevamiento).toHaveBeenCalledTimes(2);
  });

  it('tocar OTRA VEZ la misma fila re-dispara la lectura (no queda un tramoRef zombi)', async () => {
    vi.mocked(fetchTramoRelevamiento).mockRejectedValueOnce(new Error('502 Bad Gateway'));

    const { result } = renderWiring(client);
    act(() => result.current.onSurveyTramo(TRAMO));
    await waitFor(() => expect(result.current.tramoError).not.toBeNull());

    // Same ref: writing the state again would be a no-op, so the hook has to
    // refetch instead. This is the assertion that fails if that branch goes.
    vi.mocked(fetchTramoRelevamiento).mockResolvedValue(DETALLE);
    act(() => result.current.onSurveyTramo(TRAMO));

    await waitFor(() => expect(result.current.tramoDetalle).toEqual(DETALLE));
    expect(fetchTramoRelevamiento).toHaveBeenCalledTimes(2);
  });

  it('cerrar la hoja suelta el tramo: no queda ninguna selección colgada', async () => {
    vi.mocked(fetchTramoRelevamiento).mockRejectedValue(new Error('502 Bad Gateway'));

    const { result } = renderWiring(client);
    act(() => result.current.onSurveyTramo(TRAMO));
    await waitFor(() => expect(result.current.tramoError).not.toBeNull());

    act(() => result.current.onCloseTramoSurvey());
    expect(result.current.tramoRef).toBeNull();
  });
});
