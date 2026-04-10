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
    createPublic: vi.fn(),
  },
}));

vi.mock('../../src/lib/logger', () => ({
  logger: { error: vi.fn() },
}));

describe('useSuggestionFormState', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(sugerenciasApi.checkLimit).mockResolvedValue({ remaining: 2, limit: 3, reset_hours: 24 });
    vi.mocked(sugerenciasApi.createPublic).mockResolvedValue({
      id: 'sug-1',
      message: 'ok',
      remaining_today: 1,
    });
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
      expect(sugerenciasApi.checkLimit).toHaveBeenCalledWith('vecino@example.com');
      expect(result.current.remainingToday).toBe(2);
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

    expect(sugerenciasApi.createPublic).toHaveBeenCalled();
    expect(reset).toHaveBeenCalled();
    expect(result.current.enviado).toBe(true);

    act(() => {
      result.current.resetSuccess();
    });
    expect(resetVerificacion).toHaveBeenCalled();
  });

  it('blocks submit when daily limit is exhausted', async () => {
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

    expect(sugerenciasApi.createPublic).toHaveBeenCalledTimes(1);

    vi.mocked(sugerenciasApi.createPublic).mockRejectedValueOnce(new Error('limite diario alcanzado'));

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
  });
});
