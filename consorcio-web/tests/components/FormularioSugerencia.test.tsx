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
    create: vi.fn(),
  },
  API_URL: 'http://localhost:8000',
}));

// Mock useWaterways to avoid QueryClient requirement from useQuery
vi.mock('../../src/hooks/useWaterways', () => ({
  useWaterways: vi.fn(() => ({ waterways: [], isLoading: false, error: null })),
}));

vi.mock('../../src/components/suggestion-form/SuggestionGeometrySection', () => ({
  SuggestionGeometrySection: () => <div>geometry-section</div>,
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
      <MantineProvider env="test">
        <FormularioSugerenciaContent />
      </MantineProvider>
    </QueryClientProvider>
  );
};

const verifiedContactState = {
  contactoVerificado: true,
  userEmail: 'vecino@example.com',
  userName: 'Vecino',
  loading: false,
  loginWithGoogle: vi.fn(),
  logout: vi.fn(),
};

describe('FormularioSugerencia', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Nuevo shape del rate-limit (5/24h rolling, source-of-truth = base):
    // `reset_seconds` reemplaza al viejo `reset_hours`. El response del
    // create ya no devuelve `remaining_today` — el frontend decremento
    // local y el cupo se refleja en `checkLimit` posterior.
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

  describe('Verification State Handling', () => {
    it('renders blocked step state when contact is not verified', () => {
      useContactVerificationMock.mockReturnValue({
        contactoVerificado: false,
        userEmail: null,
        userName: null,
        loading: false,
        loginWithGoogle: vi.fn(),
        logout: vi.fn(),
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
        loading: false,
        loginWithGoogle: vi.fn(),
        logout: vi.fn(),
      });
      vi.mocked(sugerenciasApi.checkLimit).mockResolvedValue({ remaining, limit: 5, reset_seconds: 86400 });

      renderForm();

      const submitButton = screen.getByRole('button', { name: /enviar sugerencia/i });
      expect(submitButton).toBeInTheDocument();
      expect(submitButton).not.toBeDisabled();
    });
  });

  describe('Submission Success Flows', () => {
    it('submits verified suggestion and shows success screen', async () => {
      useContactVerificationMock.mockReturnValue(verifiedContactState);

      const user = userEvent.setup();
      renderForm();

      await user.type(screen.getByLabelText(/titulo de la sugerencia/i), 'Mejorar drenaje principal');
      await user.type(
        screen.getByPlaceholderText(/Explica tu sugerencia con el mayor detalle posible/i),
        'Propongo limpiar y ensanchar el drenaje antes de la temporada de lluvias'
      );
      await user.click(screen.getByRole('button', { name: /enviar sugerencia/i }));

      await waitFor(() => {
        expect(sugerenciasApi.create).toHaveBeenCalled();
        expect(screen.getByRole('status')).toHaveTextContent(/Gracias por tu sugerencia/i);
      });
    });

    it('announces submission progress while the suggestion is being sent', async () => {
      useContactVerificationMock.mockReturnValue(verifiedContactState);
      let resolveCreate!: (value: { id: string; titulo: string }) => void;
      vi.mocked(sugerenciasApi.create).mockReturnValue(
        new Promise((resolve) => {
          resolveCreate = resolve as never;
        }) as never
      );

      const user = userEvent.setup();
      renderForm();

      await user.type(screen.getByLabelText(/titulo de la sugerencia/i), 'Mejorar drenaje principal');
      await user.type(
        screen.getByPlaceholderText(/Explica tu sugerencia con el mayor detalle posible/i),
        'Propongo limpiar y ensanchar el drenaje antes de la temporada de lluvias'
      );
      await user.click(screen.getByRole('button', { name: /enviar sugerencia/i }));

      expect(screen.getByRole('status')).toHaveTextContent(/enviando sugerencia/i);

      resolveCreate({ id: 'sug-1', titulo: 'Mejorar drenaje principal' });
      await screen.findByText(/Gracias por tu sugerencia/i);
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
        loading: false,
        loginWithGoogle: vi.fn(),
        logout: vi.fn(),
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
        expect(sugerenciasApi.create).toHaveBeenCalled();
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
          loading: false,
          loginWithGoogle: vi.fn(),
          logout: vi.fn(),
        };
      });
      vi.mocked(sugerenciasApi.checkLimit).mockResolvedValue({ remaining: 0, limit: 5, reset_seconds: 86400 });

      renderForm();

      await waitFor(() => {
        expect(screen.getByText(/Llegaste al limite de 5 sugerencias cada 24 horas/i)).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /enviar sugerencia/i })).toBeDisabled();
      });
    });

    it.each([
      { remaining: 0, resetSeconds: 86400, name: 'no remaining, 24 hour reset' },
      { remaining: 0, resetSeconds: 43200, name: 'no remaining, 12 hour reset' },
      { remaining: 0, resetSeconds: 3600, name: 'no remaining, 1 hour reset' },
    ])('shows limit message with reset info ($name)', async ({ remaining, resetSeconds }) => {
      useContactVerificationMock.mockImplementation(({ onVerified }) => {
        queueMicrotask(() => {
          void onVerified?.();
        });
        return {
          contactoVerificado: true,
          userEmail: 'vecino@example.com',
          userName: 'Vecino',
          loading: false,
          loginWithGoogle: vi.fn(),
          logout: vi.fn(),
        };
      });
      vi.mocked(sugerenciasApi.checkLimit).mockResolvedValue({
        remaining,
        limit: 5,
        reset_seconds: resetSeconds,
      });

      renderForm();

      await waitFor(() => {
        expect(screen.getByText(/Llegaste al limite de 5 sugerencias cada 24 horas/i)).toBeInTheDocument();
        const submitButton = screen.getByRole('button', { name: /enviar sugerencia/i });
        expect(submitButton).toBeDisabled();
      });
    });

    it('marks remaining as zero when API returns limit message', async () => {
      useContactVerificationMock.mockReturnValue({
        contactoVerificado: true,
        userEmail: 'vecino@example.com',
        userName: 'Vecino',
        loading: false,
        loginWithGoogle: vi.fn(),
        logout: vi.fn(),
      });
      vi.mocked(sugerenciasApi.create).mockRejectedValue(new Error('limite diario alcanzado'));

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
        expect(screen.getByText(/Llegaste al limite de 5 sugerencias cada 24 horas/i)).toBeInTheDocument();
      });
    });
  });

  describe('Error Handling', () => {
    it('shows error notification on submission failure', async () => {
      useContactVerificationMock.mockReturnValue({
        contactoVerificado: true,
        userEmail: 'vecino@example.com',
        userName: 'Vecino',
        loading: false,
        loginWithGoogle: vi.fn(),
        logout: vi.fn(),
      });
      vi.mocked(sugerenciasApi.create).mockRejectedValue(new Error('Server error'));

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
        loading: false,
        loginWithGoogle: vi.fn(),
        logout: vi.fn(),
      });
      vi.mocked(sugerenciasApi.create).mockRejectedValue(new Error(error));

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
