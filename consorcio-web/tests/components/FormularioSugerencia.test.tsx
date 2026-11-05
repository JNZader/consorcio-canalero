import { MantineProvider } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { isValidElement, type ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { FormularioSugerenciaContent } from '../../src/components/FormularioSugerencia';
import { sugerenciasApi } from '../../src/lib/api';
import { SUGGESTION_DRAFT_KEY } from '../../src/lib/formDrafts';
import { QueryError } from '../../src/lib/queryError';
import formStyles from '../../src/styles/components/form.module.css';

const useContactVerificationMock = vi.fn();

vi.mock('../../src/hooks/useContactVerification', () => ({
  useContactVerification: (...args: unknown[]) => useContactVerificationMock(...args),
}));

vi.mock('../../src/components/verification', () => ({
  ContactVerificationSection: ({
    onLoginWithGoogle,
  }: {
    onLoginWithGoogle?: () => void;
  }) => (
    <div>
      <div>verification-section</div>
      <button type="button" onClick={() => onLoginWithGoogle?.()}>
        Continuar con Google
      </button>
    </div>
  ),
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
    hide: vi.fn(),
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
    it('keeps the suggestion form editable before verification', () => {
      useContactVerificationMock.mockReturnValue({
        contactoVerificado: false,
        userEmail: null,
        userName: null,
        loading: false,
        loginWithGoogle: vi.fn(),
        logout: vi.fn(),
      });

      renderForm();

      expect(screen.getByText(/verificá tu identidad para enviar/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /enviar sugerencia/i })).toBeEnabled();
      expect(screen.getByRole('button', { name: /enviar sugerencia/i })).toHaveClass('touch-target-min');
      expect(screen.getByRole('button', { name: /enviar sugerencia/i }).parentElement).toHaveClass(
        formStyles.submitBar
      );
      expect(screen.getByText(/guardamos el texto y el trazo del mapa/i)).toBeInTheDocument();
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

      await user.type(screen.getByLabelText(/t[ií]tulo de la sugerencia/i), 'Mejorar drenaje principal');
      await user.type(
        screen.getByPlaceholderText(/Explicá tu sugerencia con el mayor detalle posible/i),
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

      await user.type(screen.getByLabelText(/t[ií]tulo de la sugerencia/i), 'Mejorar drenaje principal');
      await user.type(
        screen.getByPlaceholderText(/Explicá tu sugerencia con el mayor detalle posible/i),
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

      await user.type(screen.getByLabelText(/t[ií]tulo de la sugerencia/i), title);
      await user.type(
        screen.getByPlaceholderText(/Explicá tu sugerencia con el mayor detalle posible/i),
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
        expect(screen.getByText(/llegaste al l[ií]mite de 5 sugerencias cada 24 horas/i)).toBeInTheDocument();
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
        expect(screen.getByText(/llegaste al l[ií]mite de 5 sugerencias cada 24 horas/i)).toBeInTheDocument();
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

      await user.type(screen.getByLabelText(/t[ií]tulo de la sugerencia/i), 'Mejorar drenaje principal');
      await user.type(
        screen.getByPlaceholderText(/Explicá tu sugerencia con el mayor detalle posible/i),
        'Propongo limpiar y ensanchar el drenaje antes de la temporada de lluvias'
      );
      await user.click(screen.getByRole('button', { name: /enviar sugerencia/i }));

      await waitFor(() => {
        expect(notifications.show).toHaveBeenCalledWith(
          expect.objectContaining({ title: 'Error', color: 'alerta' })
        );
        expect(screen.getByText(/llegaste al l[ií]mite de 5 sugerencias cada 24 horas/i)).toBeInTheDocument();
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

      await user.type(screen.getByLabelText(/t[ií]tulo de la sugerencia/i), 'Test title');
      await user.type(
        screen.getByPlaceholderText(/Explicá tu sugerencia con el mayor detalle posible/i),
        'Test description'
      );
      await user.click(screen.getByRole('button', { name: /enviar sugerencia/i }));

      await waitFor(() => {
        expect(notifications.show).toHaveBeenCalledWith(
          expect.objectContaining({ color: 'alerta' })
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

      await user.type(screen.getByLabelText(/t[ií]tulo de la sugerencia/i), 'Test title');
      await user.type(
        screen.getByPlaceholderText(/Explicá tu sugerencia con el mayor detalle posible/i),
        'Test description'
      );
      await user.click(screen.getByRole('button', { name: /enviar sugerencia/i }));

      await waitFor(() => {
        expect(notifications.show).toHaveBeenCalled();
      });
    });
  });

  describe('Category-Driven Map Visibility (CIT-03)', () => {
    it('hides the canal map behind an optional toggle when selecting an administrative category', async () => {
      useContactVerificationMock.mockReturnValue(verifiedContactState);

      const user = userEvent.setup();
      renderForm();

      // Default category: map is shown
      expect(screen.getByText('geometry-section')).toBeInTheDocument();

      await user.click(screen.getByPlaceholderText(/seleccioná una categoría/i));
      await user.click(await screen.findByText(/temas administrativos/i));

      expect(screen.queryByText('geometry-section')).not.toBeInTheDocument();
      const toggleBtn = screen.getByRole('button', {
        name: /agregar ubicación en el mapa \(opcional\)/i,
      });
      expect(toggleBtn).toBeInTheDocument();

      await user.click(toggleBtn);
      expect(screen.getByText('geometry-section')).toBeInTheDocument();
    });
  });

  describe('Mobile parity with the report form', () => {
    const titulo = 'Mejorar drenaje principal';
    const descripcion = 'Propongo limpiar y ensanchar el drenaje antes de la temporada de lluvias';

    async function fill(user: ReturnType<typeof userEvent.setup>) {
      await user.type(screen.getByLabelText(/t[ií]tulo de la sugerencia/i), titulo);
      await user.type(
        screen.getByPlaceholderText(/Explicá tu sugerencia con el mayor detalle posible/i),
        descripcion
      );
    }

    it('saves the draft before Google login and leaves an empty form alone', async () => {
      sessionStorage.clear();
      const loginWithGoogle = vi.fn();
      useContactVerificationMock.mockReturnValue({
        contactoVerificado: false,
        userEmail: null,
        userName: null,
        loading: false,
        loginWithGoogle,
        logout: vi.fn(),
      });

      const user = userEvent.setup();
      const { unmount } = renderForm();
      await user.click(screen.getByRole('button', { name: /continuar con google/i }));
      expect(loginWithGoogle).toHaveBeenCalledTimes(1);
      expect(sessionStorage.getItem(SUGGESTION_DRAFT_KEY)).toBeNull();

      await fill(user);
      await user.click(screen.getByRole('button', { name: /continuar con google/i }));
      expect(loginWithGoogle).toHaveBeenCalledTimes(2);
      expect(JSON.parse(sessionStorage.getItem(SUGGESTION_DRAFT_KEY) ?? 'null')).toMatchObject({
        titulo,
        descripcion,
      });
      unmount();
    });

    it('shows an inline retry and a toast without clearing the suggestion', async () => {
      sessionStorage.clear();
      useContactVerificationMock.mockReturnValue(verifiedContactState);
      vi.mocked(sugerenciasApi.create).mockRejectedValueOnce(
        new QueryError('API Error: 503', 503, '/sugerencias')
      );

      const user = userEvent.setup();
      renderForm();
      await fill(user);
      await user.click(screen.getByRole('button', { name: /enviar sugerencia/i }));

      expect(await screen.findByRole('alert', { name: /sin conexión/i })).toHaveTextContent(
        /los datos siguen en el formulario/i
      );
      expect(screen.getByLabelText(/t[ií]tulo de la sugerencia/i)).toHaveValue(titulo);
      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          id: 'sugerencia-sin-conexion',
          title: 'Sin conexión',
          color: 'orange',
          autoClose: false,
        })
      );

      await user.click(screen.getByRole('button', { name: /reintentar envío/i }));
      expect(sugerenciasApi.create).toHaveBeenCalledTimes(2);
      await waitFor(() => {
        expect(screen.queryByRole('alert', { name: /sin conexión/i })).not.toBeInTheDocument();
      });
      expect(notifications.hide).toHaveBeenCalledWith('sugerencia-sin-conexion');
    });

    it('keeps a normal error as a toast and does not show the offline retry', async () => {
      useContactVerificationMock.mockReturnValue(verifiedContactState);
      vi.mocked(sugerenciasApi.create).mockRejectedValueOnce(new QueryError('dato inválido', 422));

      const user = userEvent.setup();
      renderForm();
      await fill(user);
      await user.click(screen.getByRole('button', { name: /enviar sugerencia/i }));

      await waitFor(() => {
        expect(notifications.show).toHaveBeenCalledWith(
          expect.objectContaining({ title: 'Error', color: 'alerta' })
        );
      });
      expect(screen.queryByRole('alert', { name: /sin conexión/i })).not.toBeInTheDocument();
      expect(screen.getByLabelText(/t[ií]tulo de la sugerencia/i)).toHaveValue(titulo);
    });

    it('ignores a second submit and a toast retry while the POST is in flight', async () => {
      sessionStorage.clear();
      useContactVerificationMock.mockReturnValue(verifiedContactState);
      let releaseRetry: (value: { id: string }) => void = () => {};
      vi.mocked(sugerenciasApi.create)
        .mockRejectedValueOnce(new QueryError('API Error: 503', 503, '/sugerencias'))
        .mockImplementationOnce(
          () =>
            new Promise((resolve) => {
              releaseRetry = resolve;
            })
        );

      const user = userEvent.setup();
      renderForm();
      await fill(user);
      await user.click(screen.getByRole('button', { name: /enviar sugerencia/i }));

      const alertRetry = await screen.findByRole('button', { name: /reintentar envío/i });
      const toastCall = vi
        .mocked(notifications.show)
        .mock.calls.find((call) => (call[0] as { id?: string } | undefined)?.id === 'sugerencia-sin-conexion');
      const retryFromToast = findOnClick(
        (toastCall?.[0] as { message?: ReactNode } | undefined)?.message
      );
      expect(retryFromToast).toEqual(expect.any(Function));

      await act(async () => {
        retryFromToast?.();
        retryFromToast?.();
        alertRetry.click();
      });

      expect(sugerenciasApi.create).toHaveBeenCalledTimes(2);
      expect(screen.getByRole('button', { name: /reintentar envío/i })).toBeDisabled();
      expect(screen.getByRole('button', { name: /enviar sugerencia/i })).toBeDisabled();

      await act(async () => {
        releaseRetry({ id: 'sug-2' });
      });
      await waitFor(() => {
        expect(screen.queryByRole('alert', { name: /sin conexión/i })).not.toBeInTheDocument();
      });
      expect(sugerenciasApi.create).toHaveBeenCalledTimes(2);
    });

    it('disables submit and ignores a second submit while the POST is in flight', async () => {
      useContactVerificationMock.mockReturnValue(verifiedContactState);
      let release: (value: { id: string }) => void = () => {};
      vi.mocked(sugerenciasApi.create).mockImplementation(
        () =>
          new Promise((resolve) => {
            release = resolve;
          })
      );

      const user = userEvent.setup();
      renderForm();
      await fill(user);

      const submit = screen.getByRole('button', { name: /enviar sugerencia/i });
      const form = submit.closest('form');
      expect(form).not.toBeNull();
      fireEvent.submit(form as HTMLFormElement);
      fireEvent.submit(form as HTMLFormElement);

      expect(sugerenciasApi.create).toHaveBeenCalledTimes(1);
      expect(screen.getByRole('button', { name: /enviar sugerencia/i })).toBeDisabled();

      await act(async () => {
        release({ id: 'sug-1' });
      });
      await screen.findByText(/Gracias por tu sugerencia/i);
      expect(sugerenciasApi.create).toHaveBeenCalledTimes(1);
    });
  });
});
