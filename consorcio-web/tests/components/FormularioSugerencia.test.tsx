import { MantineProvider } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
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
  API_URL: 'http://localhost:8000',
}));

// Mock useWaterways to avoid QueryClient requirement from useQuery
vi.mock('../../src/hooks/useWaterways', () => ({
  useWaterways: vi.fn(() => ({ waterways: [], isLoading: false, error: null })),
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

const createTestQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });

const renderForm = () => {
  const queryClient = createTestQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider>
        <FormularioSugerenciaContent />
      </MantineProvider>
    </QueryClientProvider>
  );
};

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

  describe('Verification State Handling', () => {
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

    it.each([
      { remaining: 1, canSubmit: true, name: 'one suggestion remaining' },
      { remaining: 2, canSubmit: true, name: 'two suggestions remaining' },
      { remaining: 3, canSubmit: true, name: 'at limit but still enabled' },
    ])('handles verification state with $name (remaining=$remaining)', ({ remaining }) => {
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
      vi.mocked(sugerenciasApi.checkLimit).mockResolvedValue({ remaining, limit: 3, reset_hours: 24 });

      renderForm();

      const submitButton = screen.getByRole('button', { name: /enviar sugerencia/i });
      expect(submitButton).toBeInTheDocument();
      expect(submitButton).not.toBeDisabled();
    });
  });

  describe('Submission Success Flows', () => {
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

    it.each([
      { title: 'Idea corta', description: 'Mejorar canales' },
      { title: 'Mejora de infraestructura hidraulica', description: 'Propongo un plan integral de mejora de la infraestructura' },
      { title: 'Plan de mantenimiento', description: 'Se debería establecer un cronograma regular de limpieza y mantenimiento de los canales principales para evitar desbordamientos' },
    ])('submits suggestion with various text lengths', async ({ title, description }) => {
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

      await user.type(screen.getByLabelText(/titulo de la sugerencia/i), title);
      await user.type(
        screen.getByPlaceholderText(/Explica tu sugerencia con el mayor detalle posible/i),
        description
      );
      await user.click(screen.getByRole('button', { name: /enviar sugerencia/i }));

      await waitFor(() => {
        expect(sugerenciasApi.createPublic).toHaveBeenCalled();
      });
    });
  });

  describe('Daily Limit Handling', () => {
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

    it.each([
      { remaining: 0, resetHours: 24, name: 'no remaining, 24 hour reset' },
      { remaining: 0, resetHours: 12, name: 'no remaining, 12 hour reset' },
      { remaining: 0, resetHours: 1, name: 'no remaining, 1 hour reset' },
    ])('shows limit message with reset info ($name)', async ({ remaining, resetHours }) => {
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
      vi.mocked(sugerenciasApi.checkLimit).mockResolvedValue({ remaining, limit: 3, reset_hours: resetHours });

      renderForm();

      await waitFor(() => {
        expect(screen.getByText(/Has alcanzado el limite de sugerencias por hoy/i)).toBeInTheDocument();
        const submitButton = screen.getByRole('button', { name: /enviar sugerencia/i });
        expect(submitButton).toBeDisabled();
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

  describe('Error Handling', () => {
    it('shows error notification on submission failure', async () => {
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
      vi.mocked(sugerenciasApi.createPublic).mockRejectedValue(new Error('Server error'));

      const user = userEvent.setup();
      renderForm();

      await user.type(screen.getByLabelText(/titulo de la sugerencia/i), 'Test title');
      await user.type(
        screen.getByPlaceholderText(/Explica tu sugerencia con el mayor detalle posible/i),
        'Test description'
      );
      await user.click(screen.getByRole('button', { name: /enviar sugerencia/i }));

      await waitFor(() => {
        expect(notifications.show).toHaveBeenCalledWith(
          expect.objectContaining({ color: 'red' })
        );
      });
    });

    it.each([
      { error: 'Network error', title: 'network failure' },
      { error: 'limite diario alcanzado', title: 'daily limit exceeded' },
      { error: 'Invalid input', title: 'validation error' },
    ])('handles error "$title" gracefully', async ({ error }) => {
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
      vi.mocked(sugerenciasApi.createPublic).mockRejectedValue(new Error(error));

      const user = userEvent.setup();
      renderForm();

      await user.type(screen.getByLabelText(/titulo de la sugerencia/i), 'Test title');
      await user.type(
        screen.getByPlaceholderText(/Explica tu sugerencia con el mayor detalle posible/i),
        'Test description'
      );
      await user.click(screen.getByRole('button', { name: /enviar sugerencia/i }));

      await waitFor(() => {
        expect(notifications.show).toHaveBeenCalled();
      });
    });
  });
});
