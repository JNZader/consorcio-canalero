// @ts-nocheck
import { MantineProvider } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { FormularioContenido } from '../../src/components/FormularioReporte';
import { publicApi } from '../../src/lib/api';

const useContactVerificationMock = vi.fn();

vi.mock('leaflet', () => ({
  default: {
    Icon: class {
      constructor(_opts: unknown) {}
    },
  },
}));

vi.mock('react-leaflet', () => ({
  MapContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TileLayer: () => <div>tile-layer</div>,
  Marker: () => <div>marker</div>,
  useMapEvents: () => ({}),
}));

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

  it('enables submit after selecting coordinates and submits report', async () => {
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

    await user.click(submitButton);

    expect(publicApi.createReport).toHaveBeenCalled();
  });

  it('shows geolocation unsupported warning when browser API is unavailable', async () => {
    const user = userEvent.setup();
    vi.stubGlobal('navigator', {});
    renderForm();

    await user.click(screen.getByRole('button', { name: /usar mi ubicacion gps/i }));

    expect(notifications.show).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Error', color: 'red' })
    );
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
});
