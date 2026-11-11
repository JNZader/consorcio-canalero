import { MantineProvider } from '@mantine/core';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }));

// geeFloodAnalysis imports apiFetch from ./core — mock that module.
vi.mock('../../src/lib/api/core', () => ({
  apiFetch: apiFetchMock,
  GEE_TIMEOUT: 1000,
  API_URL: 'http://test',
  API_PREFIX: '/api/v2',
  DEFAULT_TIMEOUT: 1000,
}));

vi.mock('../../src/lib/notifications', () => ({
  showError: vi.fn(),
  showInfo: vi.fn(),
  showSuccess: vi.fn(),
}));

import { showError, showSuccess } from '../../src/lib/notifications';
import { ImageExplorerFloodAnalysis } from '../../src/components/admin/images/ImageExplorerFloodAnalysis';

function wrapper({ children }: { children: ReactNode }) {
  return <MantineProvider env="test">{children}</MantineProvider>;
}

const floodTile = {
  tile_url: 'https://earthengine.googleapis.com/v1/projects/x/maps/flood/tiles/{z}/{x}/{y}',
  target_date: '2024-01-10',
  sensor: 'Sentinel-2',
  visualization: 'inundacion',
  visualization_description: 'Inundación',
  collection: 'COPERNICUS/S2_SR_HARMONIZED',
  images_count: 1,
  dates_available: ['2024-01-10'],
};

const normalTile = {
  ...floodTile,
  tile_url: 'https://earthengine.googleapis.com/v1/projects/x/maps/normal/tiles/{z}/{x}/{y}',
  target_date: '2024-01-20',
  visualization: 'rgb',
  visualization_description: 'RGB',
};

/** SAR-only tile: dispara el fallback de Sentinel-1 para la referencia. */
const sarTile = {
  ...floodTile,
  tile_url: 'https://earthengine.googleapis.com/v1/projects/x/maps/sar/tiles/{z}/{x}/{y}',
  target_date: '2024-01-10',
  visualization: 'vv_flood',
  visualization_description: 'Detección de agua',
  sensor: 'Sentinel-1',
  collection: 'COPERNICUS/S1_GRD',
};

function sarOnlyJobCompleted(id: string) {
  return {
    id,
    tipo: 'flood',
    estado: 'completed',
    resultado: { method: 'sar_only', sar: sarTile },
  };
}

/** Promesa controlable desde el test: decide cuándo (y si) resuelve un fetch. */
function createDeferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

/** Igual que fetch real: la señal abortada rechaza la petición en vuelo. */
function fetchDeferredOnAbort<T>(
  deferred: { promise: Promise<T>; reject: (reason?: unknown) => void },
  signal?: AbortSignal
): Promise<T> {
  signal?.addEventListener('abort', () => {
    deferred.reject(new DOMException('Aborted', 'AbortError'));
  });
  return deferred.promise;
}

async function fillDatesAndRun(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText(/Fecha de crecida/i), '2024-01-10');
  await user.type(screen.getByLabelText(/Fecha sin agua/i), '2024-01-20');
  await user.click(screen.getByRole('button', { name: /^Detectar inundación$/i }));
}

describe('ImageExplorerFloodAnalysis', () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    vi.mocked(showSuccess).mockClear();
  });

  it('submits flood analysis, polls, and pushes comparison sides', async () => {
    const onSetLeft = vi.fn();
    const onSetRight = vi.fn();
    const user = userEvent.setup();

    apiFetchMock
      .mockResolvedValueOnce({
        id: '11111111-1111-1111-1111-111111111111',
        tipo: 'flood',
        estado: 'pending',
      })
      .mockResolvedValueOnce({
        id: '11111111-1111-1111-1111-111111111111',
        tipo: 'flood',
        estado: 'completed',
        resultado: {
          method: 'fusion',
          comparison: {
            normal_rgb: normalTile,
            flood_detection: floodTile,
          },
        },
      });

    render(
      <ImageExplorerFloodAnalysis onSetLeftImage={onSetLeft} onSetRightImage={onSetRight} />,
      { wrapper }
    );

    await user.type(screen.getByLabelText(/Fecha de crecida/i), '2024-01-10');
    await user.type(screen.getByLabelText(/Fecha sin agua/i), '2024-01-20');

    await user.click(screen.getByRole('button', { name: /^Detectar inundación$/i }));

    await waitFor(() => {
      expect(onSetLeft).toHaveBeenCalled();
      expect(onSetRight).toHaveBeenCalled();
    });

    expect(apiFetchMock.mock.calls[0][0]).toBe('/geo/gee/analysis');
    expect(apiFetchMock.mock.calls[0][1]).toMatchObject({ method: 'POST' });
    const body = JSON.parse(apiFetchMock.mock.calls[0][1].body as string);
    expect(body).toEqual({
      tipo: 'flood',
      parametros: {
        start_date: '2024-01-10',
        end_date: '2024-01-20',
        method: 'fusion',
      },
    });

    expect(onSetLeft.mock.calls[0][0].target_date).toBe('2024-01-20');
    expect(onSetRight.mock.calls[0][0].visualization).toBe('inundacion');
  });

  it('prefills dates from event shortcuts', () => {
    render(
      <ImageExplorerFloodAnalysis
        onSetLeftImage={vi.fn()}
        onSetRightImage={vi.fn()}
        initialFloodDate="2015-03-14"
        initialNormalDate="2015-03-20"
      />,
      { wrapper }
    );
    expect(screen.getByLabelText(/Fecha de crecida/i)).toHaveValue('2015-03-14');
    expect(screen.getByLabelText(/Fecha sin agua/i)).toHaveValue('2015-03-20');
  });

  it('blocks when reference is not after flood date', async () => {
    const user = userEvent.setup();
    render(
      <ImageExplorerFloodAnalysis onSetLeftImage={vi.fn()} onSetRightImage={vi.fn()} />,
      { wrapper }
    );

    await user.type(screen.getByLabelText(/Fecha de crecida/i), '2024-01-10');
    await user.type(screen.getByLabelText(/Fecha sin agua/i), '2024-01-10');

    expect(screen.getByRole('alert')).toHaveTextContent(/1 día/i);
    expect(screen.getByRole('button', { name: /^Detectar inundación$/i })).toBeDisabled();
    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it('cancelar con el fallback de Sentinel-1 en vuelo no aplica tiles ni toast de éxito', async () => {
    const onSetLeft = vi.fn();
    const onSetRight = vi.fn();
    const user = userEvent.setup();
    const sentinel1 = createDeferred<Record<string, unknown>>();

    apiFetchMock
      .mockResolvedValueOnce({ id: 'job-1', tipo: 'flood', estado: 'pending' })
      .mockResolvedValueOnce(sarOnlyJobCompleted('job-1'))
      .mockImplementationOnce((_url: string, options: { signal?: AbortSignal }) =>
        fetchDeferredOnAbort(sentinel1, options.signal)
      );

    render(<ImageExplorerFloodAnalysis onSetLeftImage={onSetLeft} onSetRightImage={onSetRight} />, {
      wrapper,
    });

    await fillDatesAndRun(user);
    // Esperar a que el fallback de Sentinel-1 quede en vuelo (3er llamado a apiFetch).
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledTimes(3));

    await user.click(screen.getByRole('button', { name: /Cancelar/i }));

    // Procesar el rechazo AbortError del fetch abortado.
    await act(async () => {
      await sentinel1.promise.catch(() => {});
    });

    expect(onSetLeft).not.toHaveBeenCalled();
    expect(onSetRight).not.toHaveBeenCalled();
    expect(showSuccess).not.toHaveBeenCalled();
    expect(screen.getByText('Cancelado.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Cancelar/i })).toBeNull();
  });

  it('descarta el run si el poll resuelve tarde tras una cancelación', async () => {
    const onSetLeft = vi.fn();
    const onSetRight = vi.fn();
    const user = userEvent.setup();
    const latePoll = createDeferred<Record<string, unknown>>();

    apiFetchMock
      .mockResolvedValueOnce({ id: 'job-1', tipo: 'flood', estado: 'pending' })
      .mockImplementationOnce(() => latePoll.promise);

    render(<ImageExplorerFloodAnalysis onSetLeftImage={onSetLeft} onSetRightImage={onSetRight} />, {
      wrapper,
    });

    await fillDatesAndRun(user);
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledTimes(2));

    await user.click(screen.getByRole('button', { name: /Cancelar/i }));
    expect(screen.getByText('Cancelado.')).toBeInTheDocument();

    // Carrera real: la respuesta del poll ya estaba en vuelo cuando se canceló.
    await act(async () => {
      latePoll.resolve(sarOnlyJobCompleted('job-1'));
      await latePoll.promise;
    });

    expect(screen.getByText('Cancelado.')).toBeInTheDocument();
    expect(onSetLeft).not.toHaveBeenCalled();
    expect(onSetRight).not.toHaveBeenCalled();
    expect(showSuccess).not.toHaveBeenCalled();
  });

  it('un submit que resuelve tras cancelar no revive el run', async () => {
    const onSetLeft = vi.fn();
    const onSetRight = vi.fn();
    const user = userEvent.setup();
    const lateSubmit = createDeferred<Record<string, unknown>>();

    apiFetchMock.mockImplementationOnce(() => lateSubmit.promise);

    render(<ImageExplorerFloodAnalysis onSetLeftImage={onSetLeft} onSetRightImage={onSetRight} />, {
      wrapper,
    });

    await fillDatesAndRun(user);
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledTimes(1));

    await user.click(screen.getByRole('button', { name: /Cancelar/i }));
    expect(screen.getByText('Cancelado.')).toBeInTheDocument();

    // El POST ya estaba en vuelo cuando se canceló: sin guard, su resolución
    // tardía re-ponía 'polling'/'Analizando…' sobre el estado cancelado.
    await act(async () => {
      lateSubmit.resolve({ id: 'job-1', tipo: 'flood', estado: 'pending' });
      await lateSubmit.promise;
    });

    expect(screen.getByText('Cancelado.')).toBeInTheDocument();
    expect(screen.queryByText('Analizando…')).toBeNull();
    expect(screen.queryByRole('button', { name: /Cancelar/i })).toBeNull();
    expect(onSetLeft).not.toHaveBeenCalled();
    expect(onSetRight).not.toHaveBeenCalled();
  });

  it('un rechazo no-AbortError de un run suplantado no pisa la cancelación', async () => {
    const onSetLeft = vi.fn();
    const onSetRight = vi.fn();
    const user = userEvent.setup();
    const latePoll = createDeferred<Record<string, unknown>>();

    apiFetchMock
      .mockResolvedValueOnce({ id: 'job-1', tipo: 'flood', estado: 'pending' })
      .mockImplementationOnce(() => latePoll.promise);

    render(<ImageExplorerFloodAnalysis onSetLeftImage={onSetLeft} onSetRightImage={onSetRight} />, {
      wrapper,
    });

    await fillDatesAndRun(user);
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledTimes(2));

    await user.click(screen.getByRole('button', { name: /Cancelar/i }));
    expect(screen.getByText('Cancelado.')).toBeInTheDocument();

    // Sin el guard en el catch exterior, un error de red tardío de un run ya
    // cancelado disparaba setState('failed') + toast sobre el estado cancelado.
    await act(async () => {
      latePoll.reject(new Error('boom de red'));
      await latePoll.promise.catch(() => {});
    });

    expect(screen.getByText('Cancelado.')).toBeInTheDocument();
    expect(screen.queryByText(/Detección fallida/i)).toBeNull();
    expect(showError).not.toHaveBeenCalled();
  });

  it('un run suplantado que resuelve tarde no pisa el estado del run nuevo', async () => {
    const onSetLeft = vi.fn();
    const onSetRight = vi.fn();
    const onPairReady = vi.fn();
    const user = userEvent.setup();
    const run1Fallback = createDeferred<Record<string, unknown>>();
    const run2Poll = createDeferred<Record<string, unknown>>();

    apiFetchMock
      .mockResolvedValueOnce({ id: 'job-1', tipo: 'flood', estado: 'pending' })
      .mockResolvedValueOnce(sarOnlyJobCompleted('job-1'))
      .mockImplementationOnce(() => run1Fallback.promise)
      .mockResolvedValueOnce({ id: 'job-2', tipo: 'flood', estado: 'pending' })
      .mockImplementationOnce(() => run2Poll.promise);

    render(
      <ImageExplorerFloodAnalysis
        onSetLeftImage={onSetLeft}
        onSetRightImage={onSetRight}
        onPairReady={onPairReady}
      />,
      { wrapper }
    );

    await fillDatesAndRun(user);
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledTimes(3));

    // Cancelar habilita un nuevo run mientras el fallback del run 1 sigue en vuelo.
    await user.click(screen.getByRole('button', { name: /Cancelar/i }));
    await user.click(screen.getByRole('button', { name: /^Detectar inundación$/i }));
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledTimes(5));
    expect(screen.getByRole('button', { name: /Analizando…/i })).toBeInTheDocument();

    // El fallback del run 1 resuelve tarde: no debe aplicar tiles ni completar.
    await act(async () => {
      run1Fallback.resolve(normalTile);
      await run1Fallback.promise;
    });

    expect(onSetLeft).not.toHaveBeenCalled();
    expect(onSetRight).not.toHaveBeenCalled();
    expect(showSuccess).not.toHaveBeenCalled();
    expect(onPairReady).not.toHaveBeenCalled();
    // El run 2 sigue en polling: el run 1 no le pisó el estado.
    expect(screen.getByRole('button', { name: /Analizando…/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Cancelar/i })).toBeInTheDocument();
  });

  it('desmontar con el fallback de Sentinel-1 en vuelo no aplica tiles', async () => {
    const onSetLeft = vi.fn();
    const onSetRight = vi.fn();
    const user = userEvent.setup();
    const sentinel1 = createDeferred<Record<string, unknown>>();

    apiFetchMock
      .mockResolvedValueOnce({ id: 'job-1', tipo: 'flood', estado: 'pending' })
      .mockResolvedValueOnce(sarOnlyJobCompleted('job-1'))
      .mockImplementationOnce((_url: string, options: { signal?: AbortSignal }) =>
        fetchDeferredOnAbort(sentinel1, options.signal)
      );

    const { unmount } = render(
      <ImageExplorerFloodAnalysis onSetLeftImage={onSetLeft} onSetRightImage={onSetRight} />,
      { wrapper }
    );

    await fillDatesAndRun(user);
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledTimes(3));

    unmount();

    // El cleanup desmonta → abort → el fetch rechaza AbortError.
    await act(async () => {
      await sentinel1.promise.catch(() => {});
    });

    expect(onSetLeft).not.toHaveBeenCalled();
    expect(onSetRight).not.toHaveBeenCalled();
    expect(showSuccess).not.toHaveBeenCalled();
  });

  it('re-attach al último análisis re-pollea el mismo job sin POSTear uno nuevo', async () => {
    const onSetLeft = vi.fn();
    const onSetRight = vi.fn();
    const user = userEvent.setup();

    const jobCompleted = {
      id: 'job-1',
      tipo: 'flood',
      estado: 'completed',
      resultado: {
        method: 'fusion',
        comparison: {
          normal_rgb: normalTile,
          flood_detection: floodTile,
        },
      },
    };

    // POST (job nuevo) + GET que completa + GET del re-attach al MISMO id.
    apiFetchMock
      .mockResolvedValueOnce({ id: 'job-1', tipo: 'flood', estado: 'pending' })
      .mockResolvedValueOnce(jobCompleted)
      .mockResolvedValueOnce(jobCompleted);

    render(<ImageExplorerFloodAnalysis onSetLeftImage={onSetLeft} onSetRightImage={onSetRight} />, {
      wrapper,
    });

    await fillDatesAndRun(user);
    await waitFor(() => {
      expect(onSetLeft).toHaveBeenCalledTimes(1);
      expect(onSetRight).toHaveBeenCalledTimes(1);
    });

    // Tras el run completado, el reintento responsable re-atachea el poll.
    await user.click(screen.getByRole('button', { name: /Revisar último análisis/i }));

    await waitFor(() => {
      expect(onSetLeft).toHaveBeenCalledTimes(2);
      expect(onSetRight).toHaveBeenCalledTimes(2);
    });

    // Un solo POST en toda la sesión: el re-attach sólo hizo GETs del último id.
    const postCalls = apiFetchMock.mock.calls.filter((call) => call[1]?.method === 'POST');
    expect(postCalls).toHaveLength(1);
    expect(apiFetchMock.mock.calls[1][0]).toBe('/geo/gee/analysis/job-1');
    expect(apiFetchMock.mock.calls[2][0]).toBe('/geo/gee/analysis/job-1');
  });

  it('el re-attach no se ofrece durante el polling y sí tras cancelar', async () => {
    const user = userEvent.setup();

    // POST + poll eterno: deja el run en polling hasta que se cancele.
    apiFetchMock
      .mockResolvedValueOnce({ id: 'job-1', tipo: 'flood', estado: 'pending' })
      .mockImplementationOnce(() => new Promise(() => {}));

    render(<ImageExplorerFloodAnalysis onSetLeftImage={vi.fn()} onSetRightImage={vi.fn()} />, {
      wrapper,
    });

    await fillDatesAndRun(user);
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledTimes(2));

    // Sin polls paralelos: durante el polling no hay botón de re-attach.
    expect(screen.queryByRole('button', { name: /Revisar último análisis/i })).toBeNull();

    // Cancelar deja el job vivo en el servidor: el re-attach recupera el handle.
    await user.click(screen.getByRole('button', { name: /Cancelar/i }));
    expect(screen.getByRole('button', { name: /Revisar último análisis/i })).toBeInTheDocument();
  });
});
