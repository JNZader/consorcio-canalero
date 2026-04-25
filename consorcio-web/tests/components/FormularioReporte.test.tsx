import { MantineProvider } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { FormularioContenido } from '../../src/components/FormularioReporte';
import { publicApi } from '../../src/lib/api';

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
        Usar mi ubicacion GPS
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
  },
}));

vi.mock('../../src/lib/logger', () => ({
  logger: {
    error: vi.fn(),
  },
}));

const renderForm = () =>
  render(
    <MantineProvider>
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
      metodoVerificacion: 'google',
      loading: false,
      magicLinkSent: false,
      magicLinkEmail: null,
      setMetodoVerificacion: vi.fn(),
      loginWithGoogle: vi.fn(),
      sendMagicLink: vi.fn(),
      logout: vi.fn(),
    });
  });

  describe('Form State Transitions', () => {
    it('disables submit button before coordinates are selected', async () => {
      const user = userEvent.setup();
      renderForm();

      await user.click(screen.getByRole('button', { name: /select-type/i }));
      await user.type(
        screen.getByLabelText(/descripcion/i),
        'Canal desbordado por lluvias intensas en el sector norte'
      );

      const submitButton = screen.getByRole('button', { name: /enviar reporte/i });
      expect(submitButton).toBeDisabled();
    });

    it('enables submit button only after coordinates are set', async () => {
      const user = userEvent.setup();
      renderForm();

      await user.click(screen.getByRole('button', { name: /select-type/i }));
      await user.type(
        screen.getByLabelText(/descripcion/i),
        'Canal desbordado por lluvias intensas en el sector norte'
      );

      const submitButton = screen.getByRole('button', { name: /enviar reporte/i });
      expect(submitButton).toBeDisabled();

      await user.click(screen.getByRole('button', { name: /ingresar coordenadas manualmente/i }));
      await user.click(screen.getByRole('button', { name: /set-coordinates/i }));
      expect(submitButton).not.toBeDisabled();
    });

    it('enables submit after selecting coordinates and submits report', async () => {
      const user = userEvent.setup();
      renderForm();

      await user.click(screen.getByRole('button', { name: /select-type/i }));
      await user.type(
        screen.getByLabelText(/descripcion/i),
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
        screen.getByLabelText(/descripcion/i),
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

      await user.click(screen.getByRole('button', { name: /usar mi ubicacion gps/i }));

      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({ title: 'Error', color: 'red' })
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
      await user.click(screen.getByRole('button', { name: /usar mi ubicacion gps/i }));

      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({ color: 'red' })
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
        metodoVerificacion: 'google',
        loading: false,
        magicLinkSent: false,
        magicLinkEmail: null,
        setMetodoVerificacion: vi.fn(),
        loginWithGoogle: vi.fn(),
        sendMagicLink: vi.fn(),
        logout: vi.fn(),
      });

      renderForm();

      expect(screen.getByText(/Nuevo Reporte/i)).toBeInTheDocument();
    });

    it('blocks submit button when contact not verified', () => {
      useContactVerificationMock.mockReturnValue({
        contactoVerificado: false,
        userEmail: null,
        userName: null,
        metodoVerificacion: 'google',
        loading: false,
        magicLinkSent: false,
        magicLinkEmail: null,
        setMetodoVerificacion: vi.fn(),
        loginWithGoogle: vi.fn(),
        sendMagicLink: vi.fn(),
        logout: vi.fn(),
      });

      renderForm();
      expect(screen.queryByRole('button', { name: /enviar reporte/i })).not.toBeInTheDocument();
    });

    it('renders blocked form state before verification', () => {
      useContactVerificationMock.mockReturnValue({
        contactoVerificado: false,
        userEmail: null,
        userName: null,
        metodoVerificacion: 'google',
        loading: false,
        magicLinkSent: false,
        magicLinkEmail: null,
        setMetodoVerificacion: vi.fn(),
        loginWithGoogle: vi.fn(),
        sendMagicLink: vi.fn(),
        logout: vi.fn(),
      });

      renderForm();

      expect(screen.getAllByText(/tipo de problema/i).length).toBeGreaterThan(0);
      expect(screen.queryByRole('button', { name: /enviar reporte/i })).not.toBeInTheDocument();
    });
  });

  describe('Photo Upload Handling', () => {
    it('handles photo upload failure gracefully', async () => {
      const user = userEvent.setup();
      vi.mocked(publicApi.uploadPhoto).mockRejectedValue(new Error('upload failed'));

      renderForm();

      await user.click(screen.getByRole('button', { name: /select-type/i }));
      await user.type(
        screen.getByLabelText(/descripcion/i),
        'Canal desbordado por lluvias intensas en el sector norte'
      );
      await user.click(screen.getByRole('button', { name: /ingresar coordenadas manualmente/i }));
      await user.click(screen.getByRole('button', { name: /set-coordinates/i }));
      await user.click(screen.getByRole('button', { name: /attach-photo/i }));
      await user.click(screen.getByRole('button', { name: /enviar reporte/i }));

      expect(publicApi.uploadPhoto).toHaveBeenCalledTimes(1);
      expect(publicApi.createReport).toHaveBeenCalledWith(
        expect.objectContaining({
          foto_url: undefined,
        })
      );
      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({ color: 'yellow' })
      );
    });

    it('submits report even when photo upload fails', async () => {
      vi.mocked(publicApi.uploadPhoto).mockRejectedValue(new Error('upload failed'));

      const user = userEvent.setup();
      renderForm();

      await user.click(screen.getByRole('button', { name: /select-type/i }));
      await user.type(
        screen.getByLabelText(/descripcion/i),
        'Canal desbordado por lluvias intensas en el sector norte'
      );
      await user.click(screen.getByRole('button', { name: /ingresar coordenadas manualmente/i }));
      await user.click(screen.getByRole('button', { name: /set-coordinates/i }));
      await user.click(screen.getByRole('button', { name: /attach-photo/i }));
      await user.click(screen.getByRole('button', { name: /enviar reporte/i }));

      expect(publicApi.uploadPhoto).toHaveBeenCalledTimes(1);
      expect(publicApi.createReport).toHaveBeenCalledWith(
        expect.objectContaining({
          foto_url: undefined,
        })
      );
      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({ title: 'Aviso', color: 'yellow' })
      );
    });

    it('shows warning notification when photo upload fails', async () => {
      vi.mocked(publicApi.uploadPhoto).mockRejectedValue(new Error('Network error'));

      const user = userEvent.setup();
      renderForm();

      await user.click(screen.getByRole('button', { name: /select-type/i }));
      await user.type(screen.getByLabelText(/descripcion/i), 'Test description');
      await user.click(screen.getByRole('button', { name: /ingresar coordenadas manualmente/i }));
      await user.click(screen.getByRole('button', { name: /set-coordinates/i }));
      await user.click(screen.getByRole('button', { name: /attach-photo/i }));
      await user.click(screen.getByRole('button', { name: /enviar reporte/i }));

      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({ color: 'yellow' })
      );
    });
  });
});
