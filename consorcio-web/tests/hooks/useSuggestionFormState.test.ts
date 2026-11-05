import { notifications } from '@mantine/notifications';
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useSuggestionFormState } from '../../src/components/suggestion-form/useSuggestionFormState';
import { sugerenciasApi } from '../../src/lib/api';
import { SUGGESTION_DRAFT_KEY, saveSuggestionDraft } from '../../src/lib/formDrafts';
import { QueryError } from '../../src/lib/queryError';

vi.mock('@mantine/notifications', () => ({
  notifications: { show: vi.fn() },
}));

vi.mock('../../src/lib/api', () => ({
  sugerenciasApi: {
    checkLimit: vi.fn(),
    create: vi.fn(),
  },
}));

vi.mock('../../src/lib/logger', () => ({
  logger: { error: vi.fn() },
}));

describe('useSuggestionFormState', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // checkLimit ahora pega contra `/sugerencias/rate-limit` (auth) y
    // devuelve `{remaining, limit, reset_seconds}` — el campo
    // `reset_hours` legacy ya no existe.
    vi.mocked(sugerenciasApi.checkLimit).mockResolvedValue({
      remaining: 4,
      limit: 5,
      reset_seconds: 86400,
    });
    vi.mocked(sugerenciasApi.create).mockResolvedValue({
      id: 'sug-1',
      titulo: 'Titulo',
      descripcion: 'Descripcion',
      estado: 'pendiente',
      tipo: 'ciudadana',
      prioridad: 'normal',
      created_at: '2026-04-29T00:00:00Z',
      updated_at: '2026-04-29T00:00:00Z',
    } as never);
  });

  it('checks rate limit when pending flag is enabled', async () => {
    const onRateLimitChecked = vi.fn();
    const { result } = renderHook(() =>
      useSuggestionFormState({
        contactoVerificado: true,
        userEmail: 'vecino@example.com',
        userName: 'Vecino',
        logout: vi.fn(),
        form: { reset: vi.fn() },
        pendingRateLimitCheck: true,
        onRateLimitChecked,
      })
    );

    await waitFor(() => {
      // Sin args — el endpoint identifica al usuario por el JWT, no
      // por email, así que el cliente no necesita pasar nada.
      expect(sugerenciasApi.checkLimit).toHaveBeenCalledWith();
      expect(result.current.remainingToday).toBe(4);
    });
    expect(onRateLimitChecked).toHaveBeenCalled();
  });

  it('submits a suggestion and resets form state', async () => {
    const reset = vi.fn();

    const { result } = renderHook(() =>
      useSuggestionFormState({
        contactoVerificado: true,
        userEmail: 'vecino@example.com',
        userName: 'Vecino',
        logout: vi.fn(),
        form: { reset },
      })
    );

    await act(async () => {
      await result.current.handleSubmit({
        titulo: 'Titulo',
        descripcion: 'Descripcion amplia',
        categoria: 'ambiental',
      });
    });

    expect(sugerenciasApi.create).toHaveBeenCalled();
    expect(reset).toHaveBeenCalled();
    expect(result.current.enviado).toBe(true);

    // `resetSuccess` solo baja la pantalla de exito: la verificacion ya no
    // tiene estado propio que resetear (B2-2.5 retiro el selector de metodo).
    act(() => {
      result.current.resetSuccess();
    });
    expect(result.current.enviado).toBe(false);
  });

  it('shows the error notification when create fails (e.g. 429 limit)', async () => {
    vi.mocked(sugerenciasApi.create).mockRejectedValueOnce(
      new Error('429 Llegaste al límite de 5 envíos cada 24 horas.')
    );

    const { result } = renderHook(() =>
      useSuggestionFormState({
        contactoVerificado: true,
        userEmail: 'vecino@example.com',
        userName: 'Vecino',
        logout: vi.fn(),
        form: { reset: vi.fn() },
      })
    );

    await act(async () => {
      await result.current.handleSubmit({
        titulo: 'Titulo',
        descripcion: 'Descripcion amplia',
        categoria: 'ambiental',
      });
    });

    expect(notifications.show).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Error', color: 'alerta' })
    );
    // El hook reflejó el 429 forzando remaining=0 para que el botón
    // se deshabilite localmente en vez de seguir pegándole al server.
    expect(result.current.remainingToday).toBe(0);
  });

  it('keeps the draft and does not reset when the POST is offline', async () => {
    sessionStorage.clear();
    vi.mocked(sugerenciasApi.create).mockRejectedValueOnce(
      new QueryError('API Error: 503', 503, '/sugerencias')
    );
    const reset = vi.fn();
    const onOfflineFailure = vi.fn();
    const announce = vi.fn();

    const { result } = renderHook(() =>
      useSuggestionFormState({
        contactoVerificado: true,
        userEmail: 'vecino@example.com',
        userName: 'Vecino',
        logout: vi.fn(),
        form: { reset },
        onOfflineFailure,
        announce,
      })
    );

    await act(async () => {
      await result.current.handleSubmit({
        titulo: 'Titulo',
        descripcion: 'Descripcion amplia',
        categoria: 'ambiental',
      });
    });

    expect(onOfflineFailure).toHaveBeenCalledTimes(1);
    expect(reset).not.toHaveBeenCalled();
    expect(result.current.enviado).toBe(false);
    expect(announce).toHaveBeenCalledWith(expect.stringMatching(/sin conexión/i), 'assertive');
    expect(JSON.parse(sessionStorage.getItem(SUGGESTION_DRAFT_KEY) ?? 'null')).toMatchObject({
      titulo: 'Titulo',
      descripcion: 'Descripcion amplia',
      categoria: 'ambiental',
    });
    expect(notifications.show).not.toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Error' })
    );
  });

  it('ignores a second submit while the first POST is in flight', async () => {
    let release: (value: unknown) => void = () => {};
    vi.mocked(sugerenciasApi.create).mockImplementation(
      () =>
        new Promise((resolve) => {
          release = resolve;
        })
    );
    const values = {
      titulo: 'Titulo',
      descripcion: 'Descripcion amplia',
      categoria: 'ambiental',
    };

    const { result } = renderHook(() =>
      useSuggestionFormState({
        contactoVerificado: true,
        userEmail: 'vecino@example.com',
        userName: 'Vecino',
        logout: vi.fn(),
        form: { reset: vi.fn() },
      })
    );

    await act(async () => {
      const first = result.current.handleSubmit(values);
      const second = result.current.handleSubmit(values);
      expect(sugerenciasApi.create).toHaveBeenCalledTimes(1);
      release({ id: 'sug-1' });
      await first;
      await second;
    });

    expect(sugerenciasApi.create).toHaveBeenCalledTimes(1);
  });
});

describe('saveSuggestionDraft', () => {
  it('drops the geometry when sessionStorage rejects the full draft', () => {
    sessionStorage.clear();
    const setItem = vi.spyOn(sessionStorage, 'setItem');
    setItem.mockImplementationOnce(() => {
      throw new Error('quota');
    });

    saveSuggestionDraft({
      titulo: 'Titulo',
      descripcion: 'Descripcion',
      categoria: 'otro',
      geometry: { type: 'FeatureCollection', features: [] },
    });

    expect(JSON.parse(sessionStorage.getItem(SUGGESTION_DRAFT_KEY) ?? 'null')).toEqual({
      titulo: 'Titulo',
      descripcion: 'Descripcion',
      categoria: 'otro',
    });
    setItem.mockRestore();
  });
});
