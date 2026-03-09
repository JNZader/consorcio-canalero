import { MantineProvider } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { FormularioSugerenciaContent } from '../../src/components/FormularioSugerencia';
import { sugerenciasApi } from '../../src/lib/api';

const useContactVerificationMock = vi.fn();

vi.mock('../../src/hooks/useContactVerification', () => ({
  useContactVerification: (...args: unknown[]) => useContactVerificationMock(...args),
}));

vi.mock('../../src/components/verification', () => ({
  ContactVerificationSection: () => <div>verification-section</div>,
}));

vi.mock('../../src/lib/api', () => ({
  sugerenciasApi: {
    checkLimit: vi.fn(),
    createPublic: vi.fn(),
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
      <FormularioSugerenciaContent />
    </MantineProvider>
  );

describe('FormularioSugerencia', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(sugerenciasApi.checkLimit).mockResolvedValue({ remaining: 2, limit: 3, reset_hours: 24 });
    vi.mocked(sugerenciasApi.createPublic).mockResolvedValue({
      id: 'sug-1',
      message: 'ok',
      remaining_today: 1,
    });
  });

  it('renders blocked step state when contact is not verified', () => {
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
      resetVerificacion: vi.fn(),
    });

    renderForm();

    expect(screen.getByText(/Verifica tu contacto primero/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /enviar sugerencia/i })).not.toBeInTheDocument();
  });

  it('submits verified suggestion and shows success screen', async () => {
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
      resetVerificacion: vi.fn(),
    });

    const user = userEvent.setup();
    renderForm();

    await user.type(screen.getByLabelText(/titulo de la sugerencia/i), 'Mejorar drenaje principal');
    await user.type(
      screen.getByPlaceholderText(/Explica tu sugerencia con el mayor detalle posible/i),
      'Propongo limpiar y ensanchar el drenaje antes de la temporada de lluvias'
    );
    await user.click(screen.getByRole('button', { name: /enviar sugerencia/i }));

    await waitFor(() => {
      expect(sugerenciasApi.createPublic).toHaveBeenCalled();
      expect(screen.getByText(/Gracias por tu sugerencia/i)).toBeInTheDocument();
    });
  });

  it('shows daily limit alert and disables submit when remaining is zero', async () => {
    useContactVerificationMock.mockImplementation(({ onVerified }) => {
      queueMicrotask(() => {
        void onVerified?.();
      });
      return {
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
        resetVerificacion: vi.fn(),
      };
    });
    vi.mocked(sugerenciasApi.checkLimit).mockResolvedValue({ remaining: 0, limit: 3, reset_hours: 24 });

    renderForm();

    await waitFor(() => {
      expect(screen.getByText(/Has alcanzado el limite de sugerencias por hoy/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /enviar sugerencia/i })).toBeDisabled();
    });
  });

  it('marks remaining as zero when API returns limit message', async () => {
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
      resetVerificacion: vi.fn(),
    });
    vi.mocked(sugerenciasApi.createPublic).mockRejectedValue(new Error('limite diario alcanzado'));

    const user = userEvent.setup();
    renderForm();

    await user.type(screen.getByLabelText(/titulo de la sugerencia/i), 'Mejorar drenaje principal');
    await user.type(
      screen.getByPlaceholderText(/Explica tu sugerencia con el mayor detalle posible/i),
      'Propongo limpiar y ensanchar el drenaje antes de la temporada de lluvias'
    );
    await user.click(screen.getByRole('button', { name: /enviar sugerencia/i }));

    await waitFor(() => {
      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({ title: 'Error', color: 'red' })
      );
      expect(screen.getByText(/Has alcanzado el limite de sugerencias por hoy/i)).toBeInTheDocument();
    });
  });
});
