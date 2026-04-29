import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { notifications } from '@mantine/notifications';
import { sugerenciasApi } from '../../src/lib/api';
import { useSuggestionFormState } from '../../src/components/suggestion-form/useSuggestionFormState';

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
        resetVerificacion: vi.fn(),
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
    const resetVerificacion = vi.fn();

    const { result } = renderHook(() =>
      useSuggestionFormState({
        contactoVerificado: true,
        userEmail: 'vecino@example.com',
        userName: 'Vecino',
        resetVerificacion,
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

    act(() => {
      result.current.resetSuccess();
    });
    expect(resetVerificacion).toHaveBeenCalled();
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
        resetVerificacion: vi.fn(),
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
      expect.objectContaining({ title: 'Error', color: 'red' })
    );
    // El hook reflejó el 429 forzando remaining=0 para que el botón
    // se deshabilite localmente en vez de seguir pegándole al server.
    expect(result.current.remainingToday).toBe(0);
  });
});
