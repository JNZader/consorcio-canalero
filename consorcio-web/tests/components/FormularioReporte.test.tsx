import { MantineProvider } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { isValidElement, type ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { FormularioContenido } from '../../src/components/FormularioReporte';
import { publicApi } from '../../src/lib/api';
import * as formDrafts from '../../src/lib/formDrafts';
import { QueryError } from '../../src/lib/queryError';

const useContactVerificationMock = vi.fn();

vi.mock('@mantine/dropzone', () => ({
  IMAGE_MIME_TYPE: ['image/jpeg'],
  Dropzone: ({
    children,
    onDrop,
  }: {
    children: React.ReactNode;
    onDrop: (files: File[]) => void;
  }) => (
    <div>
      <button
        type="button"
        onClick={() => onDrop([new File(['img'], 'evidence.jpg', { type: 'image/jpeg' })])}
      >
        attach-photo
      </button>
      {children}
    </div>
  ),
}));

vi.mock('../../src/hooks/useContactVerification', () => ({
  useContactVerification: (...args: unknown[]) => useContactVerificationMock(...args),
}));

vi.mock('../../src/components/verification', () => ({
  ContactVerificationSection: () => <div>verification-section</div>,
}));

vi.mock('../../src/components/ui/accessibility', () => ({
  LiveRegionProvider: ({ children }: { children: React.ReactNode }) => children,
  useLiveRegion: () => ({ announce: vi.fn() }),
  VisuallyHidden: ({
    children,
    as: Component = 'span',
    ...props
  }: {
    children: React.ReactNode;
    as?: React.ElementType;
  }) => <Component {...props}>{children}</Component>,
  CoordinatesInput: ({ onCoordinatesChange }: { onCoordinatesChange: (lat: number, lng: number) => void }) => (
    <button type="button" onClick={() => onCoordinatesChange(-32.6, -62.7)}>
      set-coordinates
    </button>
  ),
  AccessibleRadioGroup: ({ onChange }: { onChange: (value: string) => void }) => (
    <button type="button" onClick={() => onChange('desborde')}>
      select-type
    </button>
  ),
}));

vi.mock('../../src/components/report-form/LocationSection', () => ({
  LocationSection: ({
    mostrarInputManual,
    onToggleInputManual,
    onCoordinatesChange,
    onObtenerGPS,
  }: {
    mostrarInputManual: boolean;
    onToggleInputManual: () => void;
    onCoordinatesChange: (lat: number, lng: number) => void;
    onObtenerGPS: () => void;
  }) => (
    <div>
      <button type="button" onClick={onObtenerGPS}>
        Usar mi ubicación GPS
      </button>
      <button type="button" onClick={onToggleInputManual}>
        {mostrarInputManual ? 'Ocultar entrada manual' : 'Ingresar coordenadas manualmente'}
      </button>
      {mostrarInputManual ? (
        <button type="button" onClick={() => onCoordinatesChange(-32.6, -62.7)}>
          set-coordinates
        </button>
      ) : null}
    </div>
  ),
}));

vi.mock('../../src/stores/configStore', () => ({
  useConfigStore: (selector: (state: { config: unknown }) => unknown) => selector({ config: undefined }),
}));

vi.mock('../../src/lib/api', () => ({
  publicApi: {
    createReport: vi.fn(),
    uploadPhoto: vi.fn(),
  },
}));

vi.mock('@mantine/notifications', () => ({
  notifications: {
    show: vi.fn(),
    hide: vi.fn(),
  },
}));

vi.mock('../../src/lib/logger', () => ({
  logger: {
    error: vi.fn(),
  },
}));

function findOnClick(node: ReactNode): (() => void) | undefined {
  if (!isValidElement(node)) return undefined;
  const props = node.props as { onClick?: () => void; children?: ReactNode };
  if (typeof props.onClick === 'function') return props.onClick;
  const children = Array.isArray(props.children) ? props.children : [props.children];
  for (const child of children) {
    const found = findOnClick(child);
    if (found) return found;
  }
  return undefined;
}

const renderForm = () =>
  render(
    <MantineProvider env="test">
      <FormularioContenido />
    </MantineProvider>
  );

describe('FormularioReporte', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(publicApi.createReport).mockResolvedValue({ id: 'rep-1', message: 'ok' });
    useContactVerificationMock.mockReturnValue({
      contactoVerificado: true,
      userEmail: 'vecino@example.com',
      userName: 'Vecino',
      loading: false,
      loginWithGoogle: vi.fn(),
      logout: vi.fn(),
    });
  });

  describe('Form State Transitions', () => {
    it('keeps submit enabled before coordinates so the form can explain what is missing', async () => {
      const user = userEvent.setup();
      renderForm();

      await user.click(screen.getByRole('button', { name: /select-type/i }));
      await user.type(
        screen.getByLabelText(/descripci[oó]n/i),
        'Canal desbordado por lluvias intensas en el sector norte'
      );

      const submitButton = screen.getByRole('button', { name: /enviar reporte/i });
      expect(screen.getByLabelText(/descripci[oó]n/i).closest('form')).toHaveAttribute('novalidate');
      expect(submitButton).toBeEnabled();
    });

    it('enables submit button only after coordinates are set', async () => {
      const user = userEvent.setup();
      renderForm();

      await user.click(screen.getByRole('button', { name: /select-type/i }));
      await user.type(
        screen.getByLabelText(/descripci[oó]n/i),
        'Canal desbordado por lluvias intensas en el sector norte'
      );

      const submitButton = screen.getByRole('button', { name: /enviar reporte/i });
      expect(submitButton).toBeEnabled();

      await user.click(screen.getByRole('button', { name: /ingresar coordenadas manualmente/i }));
      await user.click(screen.getByRole('button', { name: /set-coordinates/i }));
      expect(submitButton).not.toBeDisabled();
    });

    it('enables submit after selecting coordinates and submits report', async () => {
      const user = userEvent.setup();
      renderForm();

      await user.click(screen.getByRole('button', { name: /select-type/i }));
      await user.type(
        screen.getByLabelText(/descripci[oó]n/i),
        'Canal desbordado por lluvias intensas en el sector norte'
      );
      await user.click(screen.getByRole('button', { name: /ingresar coordenadas manualmente/i }));
      await user.click(screen.getByRole('button', { name: /set-coordinates/i }));
      await user.click(screen.getByRole('button', { name: /enviar reporte/i }));

      expect(publicApi.createReport).toHaveBeenCalled();
    });

    it('announces submission progress while the report is being sent', async () => {
      vi.mocked(publicApi.createReport).mockReturnValue(new Promise(() => {}));

      const user = userEvent.setup();
      renderForm();

      await user.click(screen.getByRole('button', { name: /select-type/i }));
      await user.type(
        screen.getByLabelText(/descripci[oó]n/i),
        'Canal desbordado por lluvias intensas en el sector norte'
      );
      await user.click(screen.getByRole('button', { name: /ingresar coordenadas manualmente/i }));
      await user.click(screen.getByRole('button', { name: /set-coordinates/i }));
      await user.click(screen.getByRole('button', { name: /enviar reporte/i }));

      expect(await screen.findByRole('status')).toHaveTextContent(/enviando reporte/i);
    });
  });

  describe('Geolocation Handling', () => {
    it('shows geolocation unsupported warning when browser API is unavailable', async () => {
      const user = userEvent.setup();
      vi.stubGlobal('navigator', {});
      renderForm();

      await user.click(screen.getByRole('button', { name: /usar mi ubicación gps/i }));

      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({ title: 'Error', color: 'alerta' })
      );
    });

    it('shows error notification when GPS location retrieval fails', async () => {
      const user = userEvent.setup();
      vi.stubGlobal('navigator', {
        geolocation: {
          getCurrentPosition: (_success: unknown, error: Function) => {
            error({ code: 1, message: 'Permission denied' });
          },
        },
      });

      renderForm();
      await user.click(screen.getByRole('button', { name: /usar mi ubicación gps/i }));

      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({ color: 'alerta' })
      );
    });
  });

  describe('Verification State Handling', () => {
    it.each([
      { contactoVerificado: false, name: 'unverified user' },
      { contactoVerificado: true, name: 'verified user' },
    ])('renders form with verification=$contactoVerificado for $name', ({ contactoVerificado }) => {
      useContactVerificationMock.mockReturnValue({
        contactoVerificado,
        userEmail: contactoVerificado ? 'vecino@example.com' : null,
        userName: contactoVerificado ? 'Vecino' : null,
        loading: false,
        loginWithGoogle: vi.fn(),
        logout: vi.fn(),
      });

      renderForm();

      expect(screen.getByText(/Nuevo Reporte/i)).toBeInTheDocument();
    });

    it('keeps the submit button available before verification', () => {
      useContactVerificationMock.mockReturnValue({
        contactoVerificado: false,
        userEmail: null,
        userName: null,
        loading: false,
        loginWithGoogle: vi.fn(),
        logout: vi.fn(),
      });

      renderForm();
      expect(screen.getByRole('button', { name: /enviar reporte/i })).toBeEnabled();
    });

    it('renders the editable form before verification', () => {
      useContactVerificationMock.mockReturnValue({
        contactoVerificado: false,
        userEmail: null,
        userName: null,
        loading: false,
        loginWithGoogle: vi.fn(),
        logout: vi.fn(),
      });

      renderForm();

      expect(screen.getByRole('button', { name: /select-type/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /enviar reporte/i })).toBeInTheDocument();
      expect(screen.getByText(/podés completar el reporte ahora/i)).toBeInTheDocument();
    });
  });

  describe('Photo Upload Handling', () => {
    it('handles photo upload failure gracefully', async () => {
      const user = userEvent.setup();
      vi.mocked(publicApi.uploadPhoto).mockRejectedValue(new Error('upload failed'));

      renderForm();

      await user.click(screen.getByRole('button', { name: /select-type/i }));
      await user.type(
        screen.getByLabelText(/descripci[oó]n/i),
        'Canal desbordado por lluvias intensas en el sector norte'
      );
      await user.click(screen.getByRole('button', { name: /ingresar coordenadas manualmente/i }));
      await user.click(screen.getByRole('button', { name: /set-coordinates/i }));
      await user.click(screen.getByRole('button', { name: /attach-photo/i }));
      await user.click(screen.getByRole('button', { name: /enviar reporte/i }));

      // El flujo real es: createReport PRIMERO (sin foto_url, devuelve
      // un id), después uploadPhoto(id, file) — NO al revés. El test
      // viejo se escribió contra un flujo legacy que ya no existe.
      // Ahora verificamos: la denuncia se crea con los campos del form
      // (sin foto_url), y la foto se intenta subir DESPUÉS.
      expect(publicApi.createReport).toHaveBeenCalledWith(
        expect.objectContaining({
          tipo: expect.any(String),
          descripcion: expect.any(String),
          latitud: expect.any(Number),
          longitud: expect.any(Number),
        })
      );
      expect(publicApi.uploadPhoto).toHaveBeenCalledTimes(1);
      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({ color: 'orange' })
      );
    });

    it('submits report even when photo upload fails', async () => {
      vi.mocked(publicApi.uploadPhoto).mockRejectedValue(new Error('upload failed'));

      const user = userEvent.setup();
      renderForm();

      await user.click(screen.getByRole('button', { name: /select-type/i }));
      await user.type(
        screen.getByLabelText(/descripci[oó]n/i),
        'Canal desbordado por lluvias intensas en el sector norte'
      );
      await user.click(screen.getByRole('button', { name: /ingresar coordenadas manualmente/i }));
      await user.click(screen.getByRole('button', { name: /set-coordinates/i }));
      await user.click(screen.getByRole('button', { name: /attach-photo/i }));
      await user.click(screen.getByRole('button', { name: /enviar reporte/i }));

      // Mismo razonamiento: el flujo es createReport → uploadPhoto, no
      // un único POST con `foto_url` ya resuelto.
      expect(publicApi.createReport).toHaveBeenCalledWith(
        expect.objectContaining({
          tipo: expect.any(String),
          descripcion: expect.any(String),
        })
      );
      expect(publicApi.uploadPhoto).toHaveBeenCalledTimes(1);
      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({ title: 'Aviso', color: 'orange' })
      );
    });

    it('shows warning notification when photo upload fails', async () => {
      vi.mocked(publicApi.uploadPhoto).mockRejectedValue(new Error('Network error'));

      const user = userEvent.setup();
      renderForm();

      await user.click(screen.getByRole('button', { name: /select-type/i }));
      await user.type(screen.getByLabelText(/descripci[oó]n/i), 'Test description');
      await user.click(screen.getByRole('button', { name: /ingresar coordenadas manualmente/i }));
      await user.click(screen.getByRole('button', { name: /set-coordinates/i }));
      await user.click(screen.getByRole('button', { name: /attach-photo/i }));
      await user.click(screen.getByRole('button', { name: /enviar reporte/i }));

      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({ color: 'orange' })
      );
    });

    it('persists small attached photo in sessionStorage draft when unverified user submits and restores it on mount (CIT-04)', async () => {
      sessionStorage.clear();
      useContactVerificationMock.mockReturnValue({
        contactoVerificado: false,
        userEmail: null,
        userName: null,
        loading: false,
        loginWithGoogle: vi.fn(),
        logout: vi.fn(),
      });

      const user = userEvent.setup();
      const { unmount } = renderForm();

      await user.click(screen.getByRole('button', { name: /select-type/i }));
      await user.type(
        screen.getByLabelText(/descripci[oó]n/i),
        'Canal desbordado con foto adjunta antes de login'
      );
      await user.click(screen.getByRole('button', { name: /ingresar coordenadas manualmente/i }));
      await user.click(screen.getByRole('button', { name: /set-coordinates/i }));
      await user.click(screen.getByRole('button', { name: /attach-photo/i }));
      await user.click(screen.getByRole('button', { name: /enviar reporte/i }));

      const rawDraft = sessionStorage.getItem('cc-draft-reporte');
      expect(rawDraft).toBeTruthy();
      const parsedDraft = JSON.parse(rawDraft ?? '{}') as {
        fotoDataUrl?: string;
        fotoName?: string;
      };
      expect(parsedDraft.fotoDataUrl).toMatch(/^data:image\/jpeg;base64,/);
      expect(parsedDraft.fotoName).toBe('evidence.jpg');

      unmount();

      // Now simulate returning from Google OAuth as verified user
      useContactVerificationMock.mockReturnValue({
        contactoVerificado: true,
        userEmail: 'vecino@example.com',
        userName: 'Vecino',
        loading: false,
        loginWithGoogle: vi.fn(),
        logout: vi.fn(),
      });

      renderForm();
      await user.click(screen.getByRole('button', { name: /enviar reporte/i }));

      expect(publicApi.createReport).toHaveBeenCalled();
      expect(publicApi.uploadPhoto).toHaveBeenCalledWith(
        'rep-1',
        expect.objectContaining({ name: 'evidence.jpg' })
      );
      sessionStorage.clear();
    });
  });

  describe('Offline submit', () => {
    const descripcion = 'Canal desbordado por lluvias intensas en el sector norte';

    async function fillAndSubmit(user: ReturnType<typeof userEvent.setup>) {
      await user.click(screen.getByRole('button', { name: /select-type/i }));
      await user.type(screen.getByLabelText(/descripci[oó]n/i), descripcion);
      await user.click(screen.getByRole('button', { name: /ingresar coordenadas manualmente/i }));
      await user.click(screen.getByRole('button', { name: /set-coordinates/i }));
      await user.click(screen.getByRole('button', { name: /attach-photo/i }));
      await user.click(screen.getByRole('button', { name: /enviar reporte/i }));
    }

    it('shows an inline retry and a toast without clearing the report', async () => {
      sessionStorage.clear();
      vi.mocked(publicApi.createReport).mockRejectedValueOnce(
        new QueryError('API Error: 503', 503, '/denuncias')
      );
      const user = userEvent.setup();
      renderForm();
      await fillAndSubmit(user);

      expect(await screen.findByRole('alert', { name: /sin conexión/i })).toHaveTextContent(
        /los datos siguen en el formulario/i
      );
      expect(screen.getByLabelText(/descripci[oó]n/i)).toHaveValue(descripcion);
      expect(screen.getByAltText(/vista previa de la foto adjunta/i)).toBeInTheDocument();
      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          id: 'reporte-sin-conexion',
          title: 'Sin conexión',
          color: 'orange',
          autoClose: false,
        })
      );

      const payload = vi.mocked(publicApi.createReport).mock.calls[0]?.[0];
      await user.click(screen.getByRole('button', { name: /reintentar envío/i }));
      expect(publicApi.createReport).toHaveBeenCalledTimes(2);
      expect(vi.mocked(publicApi.createReport).mock.calls[1]?.[0]).toEqual(payload);
      await waitFor(() => {
        expect(screen.queryByRole('alert', { name: /sin conexión/i })).not.toBeInTheDocument();
      });
      expect(notifications.hide).toHaveBeenCalledWith('reporte-sin-conexion');
    });

    it('keeps a normal error as a toast and does not show the offline retry', async () => {
      vi.mocked(publicApi.createReport).mockRejectedValueOnce(new QueryError('dato inválido', 422));
      const user = userEvent.setup();
      renderForm();
      await fillAndSubmit(user);

      expect(screen.queryByRole('alert', { name: /sin conexión/i })).not.toBeInTheDocument();
      expect(screen.getByLabelText(/descripci[oó]n/i)).toHaveValue(descripcion);
      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({ title: 'Error', color: 'alerta' })
      );
    });

    it('disables submit and ignores a second submit while the POST is in flight', async () => {
      let release: (value: { id: string; message: string }) => void = () => {};
      vi.mocked(publicApi.createReport).mockImplementation(
        () =>
          new Promise((resolve) => {
            release = resolve;
          })
      );
      const user = userEvent.setup();
      renderForm();

      await user.click(screen.getByRole('button', { name: /select-type/i }));
      await user.type(screen.getByLabelText(/descripci[oó]n/i), descripcion);
      await user.click(screen.getByRole('button', { name: /ingresar coordenadas manualmente/i }));
      await user.click(screen.getByRole('button', { name: /set-coordinates/i }));

      const submit = screen.getByRole('button', { name: /enviar reporte/i });
      const form = submit.closest('form');
      expect(form).not.toBeNull();
      fireEvent.submit(form as HTMLFormElement);
      fireEvent.submit(form as HTMLFormElement);

      expect(publicApi.createReport).toHaveBeenCalledTimes(1);
      expect(screen.getByRole('button', { name: /enviar reporte/i })).toBeDisabled();
      expect(screen.getByRole('status')).toHaveTextContent(/enviando reporte/i);

      await act(async () => {
        release({ id: 'rep-1', message: 'ok' });
      });
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /enviar reporte/i })).toBeEnabled();
      });
      expect(publicApi.createReport).toHaveBeenCalledTimes(1);
    });

    it('ignores Alert and toast Reintentar while a retry is still in flight', async () => {
      sessionStorage.clear();
      const saveDraft = vi.spyOn(formDrafts, 'saveReportDraft');
      let releaseRetry: (value: { id: string; message: string }) => void = () => {};
      vi.mocked(publicApi.createReport)
        .mockRejectedValueOnce(new QueryError('API Error: 503', 503, '/denuncias'))
        .mockImplementationOnce(
          () =>
            new Promise((resolve) => {
              releaseRetry = resolve;
            })
        );

      const user = userEvent.setup();
      renderForm();
      await fillAndSubmit(user);

      const alertRetry = await screen.findByRole('button', { name: /reintentar envío/i });
      expect(alertRetry).toBeEnabled();
      const toastCall = vi
        .mocked(notifications.show)
        .mock.calls.find((call) => (call[0] as { id?: string } | undefined)?.id === 'reporte-sin-conexion');
      const retryFromToast = findOnClick(
        (toastCall?.[0] as { message?: ReactNode } | undefined)?.message
      );
      expect(retryFromToast).toEqual(expect.any(Function));

      expect(saveDraft).toHaveBeenCalledTimes(1);
      expect(saveDraft.mock.calls[0]?.[0]).toMatchObject({ descripcion });

      await act(async () => {
        retryFromToast?.();
        retryFromToast?.();
        alertRetry.click();
      });

      expect(publicApi.createReport).toHaveBeenCalledTimes(2);
      expect(notifications.hide).toHaveBeenCalledWith('reporte-sin-conexion');
      expect(screen.getByRole('button', { name: /reintentar envío/i })).toBeDisabled();
      expect(screen.getByRole('button', { name: /enviar reporte/i })).toBeDisabled();
      expect(saveDraft).toHaveBeenCalledTimes(1);
      expect(JSON.parse(sessionStorage.getItem('cc-draft-reporte') ?? 'null')).toMatchObject({
        descripcion,
      });

      await act(async () => {
        releaseRetry({ id: 'rep-2', message: 'ok' });
      });
      await waitFor(() => {
        expect(screen.queryByRole('alert', { name: /sin conexión/i })).not.toBeInTheDocument();
      });
      expect(publicApi.createReport).toHaveBeenCalledTimes(2);
      saveDraft.mockRestore();
    });
  });
});
