import { notifications } from '@mantine/notifications';
import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useReportFormSubmission } from '../../src/components/report-form/useReportFormSubmission';
import { publicApi } from '../../src/lib/api';
import { QueryError } from '../../src/lib/queryError';

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
    expect(JSON.parse(sessionStorage.getItem('cc-draft-reporte') ?? '{}')).toMatchObject({
      tipo: 'desborde',
      descripcion: 'descripcion valida',
      lat: -32.6,
      lng: -62.7,
    });
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
      expect.objectContaining({ title: 'Límite alcanzado', color: 'orange' })
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

  it('keeps the form and asks for a retry when the service worker returns 503', async () => {
    vi.mocked(publicApi.createReport).mockRejectedValue(
      new QueryError('API Error: 503', 503, '/denuncias')
    );
    const announce = vi.fn();
    const reset = vi.fn();
    const setUbicacion = vi.fn();
    const setFotoPreview = vi.fn();
    const onOfflineFailure = vi.fn();
    const onSubmitSuccess = vi.fn();
    sessionStorage.clear();

    const { result } = renderHook(() =>
      useReportFormSubmission({
        contactoVerificado: true,
        userEmail: 'vecino@example.com',
        userName: 'Vecino',
        ubicacion: { lat: -32.6, lng: -62.7 },
        announce,
        form: {
          values: { tipo: 'desborde', descripcion: 'descripcion valida', foto: null },
          reset,
        },
        setEnviando: vi.fn(),
        setUbicacion,
        setFotoPreview,
        ...baseRateLimitProps,
        onSubmitSuccess,
        onOfflineFailure,
      })
    );

    await act(async () => {
      await result.current({
        tipo: 'desborde',
        descripcion: 'Canal tapado cerca del puente',
        foto: null,
      });
    });

    expect(reset).not.toHaveBeenCalled();
    expect(setUbicacion).not.toHaveBeenCalled();
    expect(setFotoPreview).not.toHaveBeenCalled();
    expect(onSubmitSuccess).not.toHaveBeenCalled();
    expect(onOfflineFailure).toHaveBeenCalledTimes(1);
    expect(notifications.show).not.toHaveBeenCalled();
    expect(announce).toHaveBeenCalledWith(
      expect.stringContaining('siguen en el formulario'),
      'assertive'
    );
    expect(JSON.parse(sessionStorage.getItem('cc-draft-reporte') ?? '{}')).toMatchObject({
      tipo: 'desborde',
      descripcion: 'Canal tapado cerca del puente',
      lat: -32.6,
      lng: -62.7,
    });
  });

  it('does not keep the offline state for a normal server error', async () => {
    vi.mocked(publicApi.createReport).mockRejectedValue(new QueryError('dato inválido', 422));
    const onOfflineFailure = vi.fn();
    const onOtherFailure = vi.fn();
    const reset = vi.fn();

    const { result } = renderHook(() =>
      useReportFormSubmission({
        contactoVerificado: true,
        userEmail: 'vecino@example.com',
        userName: 'Vecino',
        ubicacion: { lat: -32.6, lng: -62.7 },
        announce: vi.fn(),
        form: { values: { tipo: '', descripcion: '', foto: null }, reset },
        setEnviando: vi.fn(),
        setUbicacion: vi.fn(),
        setFotoPreview: vi.fn(),
        ...baseRateLimitProps,
        onOfflineFailure,
        onOtherFailure,
      })
    );

    await act(async () => {
      await result.current({ tipo: 'desborde', descripcion: 'descripcion valida', foto: null });
    });

    expect(onOfflineFailure).not.toHaveBeenCalled();
    expect(onOtherFailure).toHaveBeenCalledTimes(1);
    expect(reset).not.toHaveBeenCalled();
    expect(notifications.show).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Error', color: 'alerta' })
    );
  });

  it('ignores a second call while the first submission is still in flight', async () => {
    let release: (value: { id: string; message: string }) => void = () => {};
    vi.mocked(publicApi.createReport).mockImplementation(
      () =>
        new Promise((resolve) => {
          release = resolve;
        })
    );
    const setEnviando = vi.fn();
    const onAttemptStart = vi.fn();
    const payload = { tipo: 'desborde', descripcion: 'descripcion valida', foto: null };

    const { result } = renderHook(() =>
      useReportFormSubmission({
        contactoVerificado: true,
        userEmail: 'vecino@example.com',
        userName: 'Vecino',
        ubicacion: { lat: -32.6, lng: -62.7 },
        announce: vi.fn(),
        form: { values: payload, reset: vi.fn() },
        setEnviando,
        setUbicacion: vi.fn(),
        setFotoPreview: vi.fn(),
        ...baseRateLimitProps,
        onAttemptStart,
      })
    );

    let first: Promise<void> = Promise.resolve();
    await act(async () => {
      first = result.current(payload);
      await result.current(payload);
    });

    expect(publicApi.createReport).toHaveBeenCalledTimes(1);
    expect(onAttemptStart).toHaveBeenCalledTimes(1);
    expect(setEnviando.mock.calls.filter(([value]) => value === true)).toHaveLength(1);
    expect(setEnviando).not.toHaveBeenCalledWith(false);

    await act(async () => {
      release({ id: 'rep-1', message: 'ok' });
      await first;
    });

    expect(publicApi.createReport).toHaveBeenCalledTimes(1);
    expect(setEnviando).toHaveBeenLastCalledWith(false);
  });

  it('writes the offline draft once and only then accepts another submit', async () => {
    let rejectCreate: (error: unknown) => void = () => {};
    vi.mocked(publicApi.createReport).mockImplementation(
      () =>
        new Promise((_resolve, reject) => {
          rejectCreate = reject;
        })
    );
    const onOfflineFailure = vi.fn();
    const setEnviando = vi.fn();
    const payload = {
      tipo: 'desborde',
      descripcion: 'Canal tapado cerca del puente',
      foto: null,
    };
    sessionStorage.clear();

    const { result } = renderHook(() =>
      useReportFormSubmission({
        contactoVerificado: true,
        userEmail: 'vecino@example.com',
        userName: 'Vecino',
        ubicacion: { lat: -32.6, lng: -62.7 },
        announce: vi.fn(),
        form: { values: payload, reset: vi.fn() },
        setEnviando,
        setUbicacion: vi.fn(),
        setFotoPreview: vi.fn(),
        ...baseRateLimitProps,
        onOfflineFailure,
      })
    );

    let first: Promise<void> = Promise.resolve();
    await act(async () => {
      first = result.current(payload);
      await result.current(payload);
    });

    expect(publicApi.createReport).toHaveBeenCalledTimes(1);
    expect(onOfflineFailure).not.toHaveBeenCalled();
    expect(sessionStorage.getItem('cc-draft-reporte')).toBeNull();

    await act(async () => {
      rejectCreate(new QueryError('API Error: 503', 503, '/denuncias'));
      await first;
    });

    expect(onOfflineFailure).toHaveBeenCalledTimes(1);
    expect(JSON.parse(sessionStorage.getItem('cc-draft-reporte') ?? '{}')).toMatchObject({
      tipo: 'desborde',
      descripcion: 'Canal tapado cerca del puente',
      lat: -32.6,
      lng: -62.7,
    });
    expect(setEnviando).toHaveBeenLastCalledWith(false);

    vi.mocked(publicApi.createReport).mockResolvedValue({ id: 'rep-2', message: 'ok' });
    await act(async () => {
      await result.current(payload);
    });
    expect(publicApi.createReport).toHaveBeenCalledTimes(2);
  });
});
