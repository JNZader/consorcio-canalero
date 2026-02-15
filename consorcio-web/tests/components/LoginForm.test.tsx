/**
 * Tests de integracion para LoginForm.
 * Cubre validacion, submit en modos login/register, y cambio de modo.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { LoginFormContent } from '../../src/components/LoginForm';
import { MantineProvider } from '@mantine/core';

// Mock del modulo auth
vi.mock('../../src/lib/auth', () => ({
  signInWithEmail: vi.fn(),
  signUpWithEmail: vi.fn(),
  signInWithGoogle: vi.fn(),
}));

// Mock de notifications
vi.mock('@mantine/notifications', () => ({
  notifications: {
    show: vi.fn(),
  },
}));

// Mock de window.location
const mockLocation = { href: '' };
Object.defineProperty(window, 'location', {
  value: mockLocation,
  writable: true,
});

import { signInWithEmail, signUpWithEmail, signInWithGoogle } from '../../src/lib/auth';
import { notifications } from '@mantine/notifications';

// Wrapper con MantineProvider
const renderWithMantine = (component: React.ReactNode) => {
  return render(<MantineProvider>{component}</MantineProvider>);
};

describe('LoginForm', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockLocation.href = '';
  });

  describe('render', () => {
    it('should render login form by default', () => {
      renderWithMantine(<LoginFormContent />);

      expect(screen.getByRole('heading', { name: 'Iniciar Sesion' })).toBeInTheDocument();
      expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/contrasena/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /iniciar sesion/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /google/i })).toBeInTheDocument();
    });

    it('should show register link', () => {
      renderWithMantine(<LoginFormContent />);

      expect(screen.getByText(/no tienes cuenta/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /registrate/i })).toBeInTheDocument();
    });

    it('should show branding', () => {
      renderWithMantine(<LoginFormContent />);

      expect(screen.getByText('Consorcio Canalero')).toBeInTheDocument();
      expect(screen.getByText(/10 de mayo/i)).toBeInTheDocument();
    });
  });

  describe('mode switching', () => {
    it('should switch to register mode when clicking Registrate', async () => {
      const user = userEvent.setup();
      renderWithMantine(<LoginFormContent />);

      await user.click(screen.getByRole('button', { name: /registrate/i }));

      expect(screen.getByRole('heading', { name: 'Crear Cuenta' })).toBeInTheDocument();
      expect(screen.getByLabelText(/nombre/i)).toBeInTheDocument();
      expect(screen.getByPlaceholderText(/repite tu contrasena/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /crear cuenta/i })).toBeInTheDocument();
    });

    it('should switch back to login mode', async () => {
      const user = userEvent.setup();
      renderWithMantine(<LoginFormContent />);

      // Switch to register
      await user.click(screen.getByRole('button', { name: /registrate/i }));
      expect(screen.getByRole('heading', { name: 'Crear Cuenta' })).toBeInTheDocument();

      // Switch back to login
      await user.click(screen.getByRole('button', { name: /inicia sesion/i }));
      expect(screen.getByRole('heading', { name: 'Iniciar Sesion' })).toBeInTheDocument();
    });

    it('should reset form when switching modes', async () => {
      const user = userEvent.setup();
      renderWithMantine(<LoginFormContent />);

      // Fill in email
      const emailInput = screen.getByLabelText(/email/i);
      await user.type(emailInput, 'test@example.com');
      expect(emailInput).toHaveValue('test@example.com');

      // Switch to register
      await user.click(screen.getByRole('button', { name: /registrate/i }));

      // Email should be cleared
      expect(screen.getByLabelText(/email/i)).toHaveValue('');
    });
  });

  describe('validation', () => {
    it('should show error for invalid email', async () => {
      const user = userEvent.setup();
      renderWithMantine(<LoginFormContent />);

      await user.type(screen.getByLabelText(/email/i), 'invalid-email');
      await user.type(screen.getByLabelText(/contrasena/i), 'password123');
      await user.click(screen.getByRole('button', { name: /iniciar sesion/i }));

      expect(await screen.findByText(/email invalido/i)).toBeInTheDocument();
    });

    it('should show error for short password', async () => {
      const user = userEvent.setup();
      renderWithMantine(<LoginFormContent />);

      await user.type(screen.getByLabelText(/email/i), 'test@example.com');
      await user.type(screen.getByLabelText(/contrasena/i), '12345');
      await user.click(screen.getByRole('button', { name: /iniciar sesion/i }));

      expect(await screen.findByText(/al menos 8 caracteres/i)).toBeInTheDocument();
    });

    it('should show error for password mismatch in register mode', async () => {
      const user = userEvent.setup();
      renderWithMantine(<LoginFormContent />);

      // Switch to register
      await user.click(screen.getByRole('button', { name: /registrate/i }));

      await user.type(screen.getByLabelText(/nombre/i), 'Test User');
      await user.type(screen.getByLabelText(/email/i), 'test@example.com');
      await user.type(screen.getByPlaceholderText('Tu contrasena'), 'password123');
      await user.type(screen.getByPlaceholderText(/repite tu contrasena/i), 'different123');
      await user.click(screen.getByRole('button', { name: /crear cuenta/i }));

      expect(await screen.findByText(/no coinciden/i)).toBeInTheDocument();
    });

    it('should show error for short name in register mode', async () => {
      const user = userEvent.setup();
      renderWithMantine(<LoginFormContent />);

      // Switch to register
      await user.click(screen.getByRole('button', { name: /registrate/i }));

      await user.type(screen.getByLabelText(/nombre/i), 'A');
      await user.type(screen.getByLabelText(/email/i), 'test@example.com');
      await user.type(screen.getByPlaceholderText('Tu contrasena'), 'password123');
      await user.type(screen.getByPlaceholderText(/repite tu contrasena/i), 'password123');
      await user.click(screen.getByRole('button', { name: /crear cuenta/i }));

      expect(await screen.findByText(/ingresa tu nombre/i)).toBeInTheDocument();
    });
  });

  describe('login submission', () => {
    it('should call signInWithEmail on valid login', async () => {
      vi.mocked(signInWithEmail).mockResolvedValue({ success: true });
      const user = userEvent.setup();
      renderWithMantine(<LoginFormContent />);

      await user.type(screen.getByLabelText(/email/i), 'test@example.com');
      await user.type(screen.getByLabelText(/contrasena/i), 'password123');
      await user.click(screen.getByRole('button', { name: /iniciar sesion/i }));

      await waitFor(() => {
        expect(signInWithEmail).toHaveBeenCalledWith('test@example.com', 'password123');
      });
    });

    it('should redirect to dashboard on successful login', async () => {
      vi.mocked(signInWithEmail).mockResolvedValue({ success: true });
      const user = userEvent.setup();
      renderWithMantine(<LoginFormContent />);

      await user.type(screen.getByLabelText(/email/i), 'test@example.com');
      await user.type(screen.getByLabelText(/contrasena/i), 'password123');
      await user.click(screen.getByRole('button', { name: /iniciar sesion/i }));

      await waitFor(() => {
        expect(mockLocation.href).toBe('/admin');
      });
    });

    it('should show notification on successful login', async () => {
      vi.mocked(signInWithEmail).mockResolvedValue({ success: true });
      const user = userEvent.setup();
      renderWithMantine(<LoginFormContent />);

      await user.type(screen.getByLabelText(/email/i), 'test@example.com');
      await user.type(screen.getByLabelText(/contrasena/i), 'password123');
      await user.click(screen.getByRole('button', { name: /iniciar sesion/i }));

      await waitFor(() => {
        expect(notifications.show).toHaveBeenCalledWith(
          expect.objectContaining({
            title: 'Bienvenido',
            color: 'green',
          })
        );
      });
    });

    it('should show error notification on failed login', async () => {
      vi.mocked(signInWithEmail).mockResolvedValue({
        success: false,
        error: 'Email o contrasena incorrectos',
      });
      const user = userEvent.setup();
      renderWithMantine(<LoginFormContent />);

      await user.type(screen.getByLabelText(/email/i), 'test@example.com');
      await user.type(screen.getByLabelText(/contrasena/i), 'wrongpassword');
      await user.click(screen.getByRole('button', { name: /iniciar sesion/i }));

      await waitFor(() => {
        expect(notifications.show).toHaveBeenCalledWith(
          expect.objectContaining({
            title: 'Error al iniciar sesion',
            color: 'red',
          })
        );
      });
    });
  });

  describe('register submission', () => {
    it('should call signUpWithEmail on valid registration', async () => {
      vi.mocked(signUpWithEmail).mockResolvedValue({ success: true });
      const user = userEvent.setup();
      renderWithMantine(<LoginFormContent />);

      await user.click(screen.getByRole('button', { name: /registrate/i }));

      await user.type(screen.getByLabelText(/nombre/i), 'Test User');
      await user.type(screen.getByLabelText(/email/i), 'test@example.com');
      await user.type(screen.getByPlaceholderText('Tu contrasena'), 'password123');
      await user.type(screen.getByPlaceholderText(/repite tu contrasena/i), 'password123');
      await user.click(screen.getByRole('button', { name: /crear cuenta/i }));

      await waitFor(() => {
        expect(signUpWithEmail).toHaveBeenCalledWith('test@example.com', 'password123', 'Test User');
      });
    });

    it('should show email confirmation message when needed', async () => {
      vi.mocked(signUpWithEmail).mockResolvedValue({
        success: true,
        needsEmailConfirmation: true,
      });
      const user = userEvent.setup();
      renderWithMantine(<LoginFormContent />);

      await user.click(screen.getByRole('button', { name: /registrate/i }));

      await user.type(screen.getByLabelText(/nombre/i), 'Test User');
      await user.type(screen.getByLabelText(/email/i), 'test@example.com');
      await user.type(screen.getByPlaceholderText('Tu contrasena'), 'password123');
      await user.type(screen.getByPlaceholderText(/repite tu contrasena/i), 'password123');
      await user.click(screen.getByRole('button', { name: /crear cuenta/i }));

      await waitFor(() => {
        expect(screen.getByText(/confirma tu email/i)).toBeInTheDocument();
      });
    });

    it('should switch to login mode on successful registration without email confirmation', async () => {
      vi.mocked(signUpWithEmail).mockResolvedValue({
        success: true,
        needsEmailConfirmation: false,
      });
      const user = userEvent.setup();
      renderWithMantine(<LoginFormContent />);

      await user.click(screen.getByRole('button', { name: /registrate/i }));

      await user.type(screen.getByLabelText(/nombre/i), 'Test User');
      await user.type(screen.getByLabelText(/email/i), 'test@example.com');
      await user.type(screen.getByPlaceholderText('Tu contrasena'), 'password123');
      await user.type(screen.getByPlaceholderText(/repite tu contrasena/i), 'password123');
      await user.click(screen.getByRole('button', { name: /crear cuenta/i }));

      await waitFor(() => {
        expect(screen.getByRole('heading', { name: 'Iniciar Sesion' })).toBeInTheDocument();
      });
    });
  });

  describe('Google OAuth', () => {
    it('should call signInWithGoogle when clicking Google button', async () => {
      vi.mocked(signInWithGoogle).mockResolvedValue({ success: true });
      const user = userEvent.setup();
      renderWithMantine(<LoginFormContent />);

      await user.click(screen.getByRole('button', { name: /google/i }));

      await waitFor(() => {
        expect(signInWithGoogle).toHaveBeenCalled();
      });
    });

    it('should show error on Google login failure', async () => {
      vi.mocked(signInWithGoogle).mockResolvedValue({
        success: false,
        error: 'No se pudo conectar con Google',
      });
      const user = userEvent.setup();
      renderWithMantine(<LoginFormContent />);

      await user.click(screen.getByRole('button', { name: /google/i }));

      await waitFor(() => {
        expect(notifications.show).toHaveBeenCalledWith(
          expect.objectContaining({
            title: 'Error con Google',
            color: 'red',
          })
        );
      });
    });
  });

  describe('loading state', () => {
    it('should disable form during submission', async () => {
      // Make the login take some time
      vi.mocked(signInWithEmail).mockImplementation(
        () => new Promise((resolve) => setTimeout(() => resolve({ success: true }), 100))
      );
      const user = userEvent.setup();
      renderWithMantine(<LoginFormContent />);

      await user.type(screen.getByLabelText(/email/i), 'test@example.com');
      await user.type(screen.getByLabelText(/contrasena/i), 'password123');

      const submitButton = screen.getByRole('button', { name: /iniciar sesion/i });
      await user.click(submitButton);

      // Button should be in loading state
      expect(submitButton).toHaveAttribute('data-loading', 'true');
    });
  });
});
