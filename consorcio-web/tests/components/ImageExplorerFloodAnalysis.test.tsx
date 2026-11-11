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
import { QueryError } from '../../src/lib/queryError';
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

/** Tile S1 que devuelve el fallback para el lado normal (2024-01-20). */
const sentinel1NormalTile = {
  ...sarTile,
  tile_url: 'https://earthengine.googleapis.com/v1/projects/x/maps/s1-normal/tiles/{z}/{x}/{y}',
  target_date: '2024-01-20',
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

  it('blocks same-day reference for fusion', async () => {
    const user = userEvent.setup();
    render(
      <ImageExplorerFloodAnalysis onSetLeftImage={vi.fn()} onSetRightImage={vi.fn()} />,
      { wrapper }
    );

    await user.type(screen.getByLabelText(/Fecha de crecida/i), '2024-01-10');
    await user.type(screen.getByLabelText(/Fecha sin agua/i), '2024-01-10');

    expect(screen.getByRole('alert')).toHaveTextContent(/1 día/i);
    // La regla de span vive SOLO en la Alert (#714): el hint del input es neutro.
    expect(screen.queryByText('Tiene que ser al menos 1 día después de la crecida')).toBeNull();
    expect(screen.getByText('Formato AAAA-MM-DD')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Detectar inundación$/i })).toBeDisabled();
    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it('same-day reference only blocks fusion: sar_only enables the run', async () => {
    const user = userEvent.setup();
    render(
      <ImageExplorerFloodAnalysis onSetLeftImage={vi.fn()} onSetRightImage={vi.fn()} />,
      { wrapper }
    );

    await user.type(screen.getByLabelText(/Fecha de crecida/i), '2024-01-10');
    await user.type(screen.getByLabelText(/Fecha sin agua/i), '2024-01-10');
    await user.selectOptions(screen.getByRole('combobox'), 'sar_only');

    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.getByRole('button', { name: /^Detectar inundación$/i })).toBeEnabled();

    // Volver a fusion con las mismas fechas reactiva el gate (regla por método).
    await user.selectOptions(screen.getByRole('combobox'), 'fusion');
    expect(screen.getByRole('alert')).toHaveTextContent(/1 día/i);
    expect(screen.getByRole('button', { name: /^Detectar inundación$/i })).toBeDisabled();
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
  it('comparación con sólo tile de crecida dispara el fallback S1 y completa el par (#710)', async () => {
    const onSetLeft = vi.fn();
    const onSetRight = vi.fn();
    const onPairReady = vi.fn();
    const user = userEvent.setup();

    apiFetchMock
      .mockResolvedValueOnce({ id: 'job-1', tipo: 'flood', estado: 'pending' })
      .mockResolvedValueOnce({
        id: 'job-1',
        tipo: 'flood',
        estado: 'completed',
        resultado: {
          method: 'fusion',
          comparison: { flood_detection: floodTile },
        },
      })
      .mockResolvedValueOnce(sentinel1NormalTile);

    render(
      <ImageExplorerFloodAnalysis
        onSetLeftImage={onSetLeft}
        onSetRightImage={onSetRight}
        onPairReady={onPairReady}
      />,
      { wrapper }
    );

    await fillDatesAndRun(user);

    await waitFor(() => {
      expect(onSetLeft).toHaveBeenCalled();
      expect(onSetRight).toHaveBeenCalled();
    });

    // Tercer fetch: fallback S1 de la referencia para la fecha sin agua.
    expect(apiFetchMock.mock.calls[2][0]).toMatch(/\/geo\/gee\/images\/sentinel1/);
    expect(apiFetchMock.mock.calls[2][0]).toContain('target_date=2024-01-20');
    expect(onSetLeft.mock.calls[0][0].target_date).toBe('2024-01-20');
    expect(onSetRight.mock.calls[0][0].visualization).toBe('inundacion');
    expect(showSuccess).toHaveBeenCalledWith(
      'Detección lista',
      'Par listo. Usá Abrir en mapa en la bandeja.'
    );
    expect(onPairReady).toHaveBeenCalled();
  });

  it('comparación con sólo tile de crecida y fallback S1 fallido queda parcial explícito (#710)', async () => {
    const onSetLeft = vi.fn();
    const onSetRight = vi.fn();
    const onPairReady = vi.fn();
    const user = userEvent.setup();

    apiFetchMock
      .mockResolvedValueOnce({ id: 'job-1', tipo: 'flood', estado: 'pending' })
      .mockResolvedValueOnce({
        id: 'job-1',
        tipo: 'flood',
        estado: 'completed',
        resultado: {
          method: 'fusion',
          comparison: { flood_detection: floodTile },
        },
      })
      .mockRejectedValueOnce(new Error('S1 no disponible'));

    render(
      <ImageExplorerFloodAnalysis
        onSetLeftImage={onSetLeft}
        onSetRightImage={onSetRight}
        onPairReady={onPairReady}
      />,
      { wrapper }
    );

    await fillDatesAndRun(user);

    await waitFor(() => expect(onSetRight).toHaveBeenCalled());

    expect(onSetLeft).not.toHaveBeenCalled();
    expect(showSuccess).not.toHaveBeenCalled();
    expect(onPairReady).not.toHaveBeenCalled();
    expect(screen.getByText(/Comparación incompleta/i)).toBeInTheDocument();
  });

  it('comparación con sólo referencia aplica el Antes y no toca el lado derecho (#710)', async () => {
    const onSetLeft = vi.fn();
    const onSetRight = vi.fn();
    const onPairReady = vi.fn();
    const user = userEvent.setup();

    apiFetchMock
      .mockResolvedValueOnce({ id: 'job-1', tipo: 'flood', estado: 'pending' })
      .mockResolvedValueOnce({
        id: 'job-1',
        tipo: 'flood',
        estado: 'completed',
        resultado: {
          method: 'fusion',
          comparison: { normal_rgb: normalTile },
        },
      });

    render(
      <ImageExplorerFloodAnalysis
        onSetLeftImage={onSetLeft}
        onSetRightImage={onSetRight}
        onPairReady={onPairReady}
      />,
      { wrapper }
    );

    await fillDatesAndRun(user);

    await waitFor(() => expect(onSetLeft).toHaveBeenCalled());

    expect(onSetLeft.mock.calls[0][0].target_date).toBe('2024-01-20');
    // El slider derecho conserva su tile anterior: nunca se pisa con un par incompleto.
    expect(onSetRight).not.toHaveBeenCalled();
    expect(showSuccess).not.toHaveBeenCalled();
    expect(onPairReady).not.toHaveBeenCalled();
    expect(screen.getByText(/Comparación incompleta/i)).toBeInTheDocument();
  });
});

describe('ImageExplorerFloodAnalysis — superficie de errores (#712)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    vi.mocked(showSuccess).mockClear();
    vi.mocked(showError).mockClear();
  });

  it('job failed desconocido: copy humano en Alert/toast, traceback crudo solo truncado en statusLine', async () => {
    const onSetLeft = vi.fn();
    const onSetRight = vi.fn();
    const user = userEvent.setup();
    const rawError = [
      'SQLAlchemyError: could not connect to server',
      'Traceback (most recent call last):',
      '  File "/app/shared/storage.py", line 10, in connect',
      'https://earthengine.googleapis.com/v1/projects/canalero-x/maps/abc123/tiles/{z}/{x}/{y}',
    ].join('\n');

    apiFetchMock
      .mockResolvedValueOnce({ id: 'job-1', tipo: 'flood', estado: 'pending' })
      .mockResolvedValueOnce({ id: 'job-1', tipo: 'flood', estado: 'failed', error: rawError });

    render(<ImageExplorerFloodAnalysis onSetLeftImage={onSetLeft} onSetRightImage={onSetRight} />, {
      wrapper,
    });

    await fillDatesAndRun(user);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(/No pudimos completar la detección de inundación/i);
    // El Alert no muestra el error crudo: ni traceback ni paths ni URLs (#712).
    expect(alert).not.toHaveTextContent('SQLAlchemyError');
    expect(alert).not.toHaveTextContent('/app/shared/storage.py');
    expect(alert).not.toHaveTextContent('googleapis');

    // Toast humano, sin el detalle crudo.
    const [toastTitulo, toastDetalle] = vi.mocked(showError).mock.calls.at(-1) ?? [];
    expect(toastTitulo).toMatch(/No pudimos completar/i);
    expect(`${toastTitulo} ${toastDetalle}`).not.toContain('https://');

    // El crudo queda como statusLine secundario: una línea, truncado, sin la
    // cola con ids de proyecto.
    const statusLine = screen.getByText('SQLAlchemyError', { exact: false });
    expect(statusLine.textContent?.length).toBeLessThanOrEqual(140);
    expect(statusLine.textContent).not.toContain('\n');
    expect(statusLine.textContent).not.toContain('canalero-x');

    expect(showSuccess).not.toHaveBeenCalled();
    expect(onSetLeft).not.toHaveBeenCalled();
    expect(onSetRight).not.toHaveBeenCalled();
  });

  it('job failed con timeout GEE: copy corta y el traceback no aparece en ningún lado', async () => {
    const user = userEvent.setup();
    apiFetchMock
      .mockResolvedValueOnce({ id: 'job-1', tipo: 'flood', estado: 'pending' })
      .mockResolvedValueOnce({
        id: 'job-1',
        tipo: 'flood',
        estado: 'failed',
        error: 'SoftTimeLimitExceeded: maximum time limit\nTraceback (most recent call last):\n  File "/app/domains/geo/gee_tasks.py", line 182',
      });

    render(<ImageExplorerFloodAnalysis onSetLeftImage={vi.fn()} onSetRightImage={vi.fn()} />, {
      wrapper,
    });

    await fillDatesAndRun(user);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(/El análisis tardó demasiado/i);
    expect(document.body.textContent).not.toContain('Traceback');
    expect(document.body.textContent).not.toContain('SoftTimeLimitExceeded');
    expect(document.body.textContent).not.toContain('/app/domains/geo/gee_tasks.py');
  });

  it('job completed sin tiles mapea comparison_error: quota conocida, sin ids de proyecto', async () => {
    const onSetLeft = vi.fn();
    const onSetRight = vi.fn();
    const user = userEvent.setup();

    apiFetchMock
      .mockResolvedValueOnce({ id: 'job-1', tipo: 'flood', estado: 'pending' })
      .mockResolvedValueOnce({
        id: 'job-1',
        tipo: 'flood',
        estado: 'completed',
        resultado: {
          method: 'fusion',
          comparison_error: 'EEException: Quota exceeded for project canalero-prod',
        },
      });

    render(<ImageExplorerFloodAnalysis onSetLeftImage={onSetLeft} onSetRightImage={onSetRight} />, {
      wrapper,
    });

    await fillDatesAndRun(user);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(/límite de consultas al servidor de imágenes/i);
    expect(document.body.textContent).not.toContain('canalero-prod');
    expect(showSuccess).not.toHaveBeenCalled();
    expect(onSetLeft).not.toHaveBeenCalled();
    expect(onSetRight).not.toHaveBeenCalled();
  });

  it('job completed sin tiles ni comparison_error usa la copy de fallback', async () => {
    const user = userEvent.setup();
    apiFetchMock
      .mockResolvedValueOnce({ id: 'job-1', tipo: 'flood', estado: 'pending' })
      .mockResolvedValueOnce({
        id: 'job-1',
        tipo: 'flood',
        estado: 'completed',
        resultado: { method: 'fusion' },
      });

    render(<ImageExplorerFloodAnalysis onSetLeftImage={vi.fn()} onSetRightImage={vi.fn()} />, {
      wrapper,
    });

    await fillDatesAndRun(user);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(/No pudimos armar el par de imágenes/i);
    expect(alert).toHaveTextContent(/al menos 1 día después/i);
  });

  it('fallback S1 con 401: sesión expirada visible, sin éxito parcial ni tiles aplicados', async () => {
    const onSetLeft = vi.fn();
    const onSetRight = vi.fn();
    const user = userEvent.setup();

    apiFetchMock
      .mockResolvedValueOnce({ id: 'job-1', tipo: 'flood', estado: 'pending' })
      .mockResolvedValueOnce(sarOnlyJobCompleted('job-1'))
      .mockRejectedValueOnce(new QueryError('Not authenticated', 401));

    render(<ImageExplorerFloodAnalysis onSetLeftImage={onSetLeft} onSetRightImage={onSetRight} />, {
      wrapper,
    });

    await fillDatesAndRun(user);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(/Tu sesión expiró/i);
    expect(alert).toHaveTextContent(/Iniciá sesión de nuevo/i);
    expect(alert).not.toHaveTextContent('Not authenticated');

    const [toastTitulo, toastDetalle] = vi.mocked(showError).mock.calls.at(-1) ?? [];
    expect(toastTitulo).toMatch(/Tu sesión expiró/i);
    expect(toastDetalle).toMatch(/Iniciá sesión de nuevo/i);

    // No hay éxito parcial: el tile de crecida tampoco se aplica en silencio.
    expect(showSuccess).not.toHaveBeenCalled();
    expect(onSetLeft).not.toHaveBeenCalled();
    expect(onSetRight).not.toHaveBeenCalled();
    // El run quedó en failed: el botón vuelve a estar habilitado.
    expect(screen.getByRole('button', { name: /^Detectar inundación$/i })).toBeEnabled();
  });

  it('fallback S1 con la sesión muerta del core (Error plano) también se muestra como expirada', async () => {
    const user = userEvent.setup();
    apiFetchMock
      .mockResolvedValueOnce({ id: 'job-1', tipo: 'flood', estado: 'pending' })
      .mockResolvedValueOnce(sarOnlyJobCompleted('job-1'))
      .mockRejectedValueOnce(new Error('Tu sesión ha expirado. Por favor iniciá sesión nuevamente.'));

    render(<ImageExplorerFloodAnalysis onSetLeftImage={vi.fn()} onSetRightImage={vi.fn()} />, {
      wrapper,
    });

    await fillDatesAndRun(user);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(/Tu sesión expiró/i);
    expect(showSuccess).not.toHaveBeenCalled();
  });

  it('fallback S1 con timeout/5xx sigue degradado: solo tile de crecida y toast de éxito', async () => {
    const onSetLeft = vi.fn();
    const onSetRight = vi.fn();
    const user = userEvent.setup();

    apiFetchMock
      .mockResolvedValueOnce({ id: 'job-1', tipo: 'flood', estado: 'pending' })
      .mockResolvedValueOnce(sarOnlyJobCompleted('job-1'))
      .mockRejectedValueOnce(new Error('La solicitud excedió el tiempo límite (300s)'));

    render(<ImageExplorerFloodAnalysis onSetLeftImage={onSetLeft} onSetRightImage={onSetRight} />, {
      wrapper,
    });

    await fillDatesAndRun(user);

    await waitFor(() => {
      expect(onSetRight).toHaveBeenCalledWith(expect.objectContaining({ sensor: 'Sentinel-1' }));
    });
    expect(onSetLeft).not.toHaveBeenCalled();
    expect(showSuccess).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('alert')).toBeNull();
  });
});
