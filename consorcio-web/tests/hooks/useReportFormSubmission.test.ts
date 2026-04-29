import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { notifications } from '@mantine/notifications';
import { useReportFormSubmission } from '../../src/components/report-form/useReportFormSubmission';
import { publicApi } from '../../src/lib/api';

vi.mock('@mantine/notifications', () => ({
  notifications: { show: vi.fn() },
}));

vi.mock('../../src/lib/api', () => ({
  publicApi: {
    createReport: vi.fn(),
    uploadPhoto: vi.fn(),
  },
}));

vi.mock('../../src/lib/logger', () => ({
  logger: { error: vi.fn() },
}));

const baseRateLimitProps = {
  // El hook ahora exige tres props extra para el rate-limit: el cupo
  // restante (null = no consultado), un callback de éxito (decremento
  // local en el form) y uno de "límite alcanzado" (refleja 429).
  remainingToday: 5 as number | null,
  onSubmitSuccess: vi.fn(),
  onLimitReached: vi.fn(),
};

describe('useReportFormSubmission', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(publicApi.createReport).mockResolvedValue({ id: 'rep-1', message: 'ok' });
    baseRateLimitProps.onSubmitSuccess = vi.fn();
    baseRateLimitProps.onLimitReached = vi.fn();
  });

  it('blocks submission when verification is missing', async () => {
    const announce = vi.fn();

    const { result } = renderHook(() =>
      useReportFormSubmission({
        contactoVerificado: false,
        userEmail: null,
        userName: null,
        ubicacion: { lat: -32.6, lng: -62.7 },
        announce,
        form: { values: { tipo: '', descripcion: '', foto: null }, reset: vi.fn() },
        setEnviando: vi.fn(),
        setUbicacion: vi.fn(),
        setFotoPreview: vi.fn(),
        ...baseRateLimitProps,
      })
    );

    await act(async () => {
      await result.current({ tipo: 'desborde', descripcion: 'descripcion valida', foto: null });
    });

    expect(publicApi.createReport).not.toHaveBeenCalled();
    expect(notifications.show).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Identidad no verificada', color: 'orange' })
    );
  });

  it('blocks submission when daily limit is exhausted', async () => {
    const announce = vi.fn();

    const { result } = renderHook(() =>
      useReportFormSubmission({
        contactoVerificado: true,
        userEmail: 'vecino@example.com',
        userName: 'Vecino',
        ubicacion: { lat: -32.6, lng: -62.7 },
        announce,
        form: { values: { tipo: '', descripcion: '', foto: null }, reset: vi.fn() },
        setEnviando: vi.fn(),
        setUbicacion: vi.fn(),
        setFotoPreview: vi.fn(),
        ...baseRateLimitProps,
        remainingToday: 0,
      })
    );

    await act(async () => {
      await result.current({ tipo: 'desborde', descripcion: 'descripcion valida', foto: null });
    });

    // Frontend gate antes de pegarle al backend — evita un 429
    // garantizado y rinde mejor UX cuando el badge ya muestra 0.
    expect(publicApi.createReport).not.toHaveBeenCalled();
    expect(notifications.show).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Limite alcanzado', color: 'orange' })
    );
  });

  it('submits and resets state when report is valid', async () => {
    const announce = vi.fn();
    const reset = vi.fn();
    const setEnviando = vi.fn();
    const setUbicacion = vi.fn();
    const setFotoPreview = vi.fn();
    const onSubmitSuccess = vi.fn();

    const { result } = renderHook(() =>
      useReportFormSubmission({
        contactoVerificado: true,
        userEmail: 'vecino@example.com',
        userName: 'Vecino',
        ubicacion: { lat: -32.6, lng: -62.7 },
        announce,
        form: { values: { tipo: '', descripcion: '', foto: null }, reset },
        setEnviando,
        setUbicacion,
        setFotoPreview,
        ...baseRateLimitProps,
        onSubmitSuccess,
      })
    );

    await act(async () => {
      await result.current({ tipo: 'desborde', descripcion: 'descripcion valida', foto: null });
    });

    // El payload ya NO lleva `contacto_email` — el backend lo
    // autollena desde el JWT. Sólo manda lo que el ciudadano controla
    // en el form.
    expect(publicApi.createReport).toHaveBeenCalledWith(
      expect.objectContaining({
        tipo: 'desborde',
        latitud: -32.6,
        longitud: -62.7,
      })
    );
    expect(reset).toHaveBeenCalled();
    expect(setUbicacion).toHaveBeenCalledWith(null);
    expect(setFotoPreview).toHaveBeenCalledWith(null);
    expect(setEnviando).toHaveBeenCalledWith(true);
    expect(setEnviando).toHaveBeenLastCalledWith(false);
    expect(onSubmitSuccess).toHaveBeenCalled();
  });
});
