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
    describe('email validation', () => {
      it.each([
        ['invalid-email', true],
        ['test', true],
        ['test@', true],
        ['@example.com', true],
        ['test@example.com', false],
        ['user.name@example.co.uk', false],
        ['test+tag@example.com', false],
      ])('email "%s" should %s error', async (email, shouldError) => {
        vi.mocked(signInWithEmail).mockResolvedValue({ success: false });
        const user = userEvent.setup();
        renderWithMantine(<LoginFormContent />);

        await user.type(screen.getByLabelText(/email/i), email);
        await user.type(screen.getByLabelText(/contrasena/i), 'password123');
        await user.click(screen.getByRole('button', { name: /iniciar sesion/i }));

        if (shouldError) {
          expect(await screen.findByText(/email invalido/i)).toBeInTheDocument();
        } else {
          expect(screen.queryByText(/email invalido/i)).not.toBeInTheDocument();
        }
      });
    });

    describe('password length validation', () => {
      it.each([
        ['1234567', 7, true],     // 7 chars - should error
        ['12345678', 8, false],   // 8 chars - should pass
        ['123456789', 9, false],  // 9 chars - should pass
      ])('password with %d chars should %s error', async (password, length, shouldError) => {
        const user = userEvent.setup();
        renderWithMantine(<LoginFormContent />);

        await user.type(screen.getByLabelText(/email/i), 'test@example.com');
        await user.type(screen.getByLabelText(/contrasena/i), password);
        await user.click(screen.getByRole('button', { name: /iniciar sesion/i }));

        if (shouldError) {
          expect(await screen.findByText(/al menos 8 caracteres/i)).toBeInTheDocument();
        } else {
          expect(screen.queryByText(/al menos 8 caracteres/i)).not.toBeInTheDocument();
        }
      });
    });

    describe('password strength in register mode', () => {
      it.each([
        ['password', false, true],      // no numbers - should error
        ['password1', true, false],    // has number - should pass
        ['12345678', true, true],      // no letters - should error
        ['password1', true, false],    // has both - should pass
        ['Pass1', true, false],        // has both - should pass
      ])('password "%s" with numbers should %s error', async (password, hasNumber, shouldError) => {
        const user = userEvent.setup();
        renderWithMantine(<LoginFormContent />);

        await user.click(screen.getByRole('button', { name: /registrate/i }));

        await user.type(screen.getByLabelText(/nombre/i), 'Test User');
        await user.type(screen.getByLabelText(/email/i), 'test@example.com');
        await user.type(screen.getByPlaceholderText('Tu contrasena'), password);
        await user.type(screen.getByPlaceholderText(/repite tu contrasena/i), password);
        await user.click(screen.getByRole('button', { name: /crear cuenta/i }));

        if (shouldError && !hasNumber) {
          expect(await screen.findByText(/al menos un numero/i)).toBeInTheDocument();
        } else if (shouldError) {
          expect(await screen.findByText(/al menos una letra/i)).toBeInTheDocument();
        }
      });
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

    describe('name validation in register mode', () => {
      it.each([
        ['A', true],     // 1 char - should error
        ['AB', false],   // 2 chars - should pass
        ['Test User', false],  // normal - should pass
      ])('name "%s" should %s error', async (name, shouldError) => {
        vi.mocked(signUpWithEmail).mockResolvedValue({ success: true, needsEmailConfirmation: false });
        const user = userEvent.setup();
        renderWithMantine(<LoginFormContent />);

        // Switch to register
        await user.click(screen.getByRole('button', { name: /registrate/i }));

        await user.type(screen.getByLabelText(/nombre/i), name);
        await user.type(screen.getByLabelText(/email/i), 'test@example.com');
        await user.type(screen.getByPlaceholderText('Tu contrasena'), 'password123');
        await user.type(screen.getByPlaceholderText(/repite tu contrasena/i), 'password123');
        await user.click(screen.getByRole('button', { name: /crear cuenta/i }));

        if (shouldError) {
          expect(await screen.findByText(/ingresa tu nombre/i)).toBeInTheDocument();
        } else {
          expect(screen.queryByText(/ingresa tu nombre/i)).not.toBeInTheDocument();
        }
      });
    });
  });

  describe('login submission', () => {
    it('should call signInWithEmail with exact email and password', async () => {
      vi.mocked(signInWithEmail).mockResolvedValue({ success: true });
      const user = userEvent.setup();
      renderWithMantine(<LoginFormContent />);

      const email = 'test@example.com';
      const password = 'password123';

      await user.type(screen.getByLabelText(/email/i), email);
      await user.type(screen.getByLabelText(/contrasena/i), password);
      await user.click(screen.getByRole('button', { name: /iniciar sesion/i }));

      await waitFor(() => {
        expect(signInWithEmail).toHaveBeenCalledWith(email, password);
        expect(signInWithEmail).toHaveBeenCalledTimes(1);
      });
    });

    it('should redirect to exact /admin path on successful login', async () => {
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

    it('should show notification with exact title and color on successful login', async () => {
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

    it('should show error notification with exact color on failed login', async () => {
      const errorMsg = 'Email o contrasena incorrectos';
      vi.mocked(signInWithEmail).mockResolvedValue({
        success: false,
        error: errorMsg,
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

    it.each([
      ['email1@example.com', 'pass1234'],
      ['email2@example.com', 'pass5678'],
      ['email3@example.com', 'pass9999'],
    ])('should call signInWithEmail with different credentials', async (email, password) => {
      vi.mocked(signInWithEmail).mockResolvedValue({ success: true });
      const user = userEvent.setup();
      renderWithMantine(<LoginFormContent />);

      await user.type(screen.getByLabelText(/email/i), email);
      await user.type(screen.getByLabelText(/contrasena/i), password);
      await user.click(screen.getByRole('button', { name: /iniciar sesion/i }));

      await waitFor(() => {
        expect(signInWithEmail).toHaveBeenCalledWith(email, password);
      });
    });
  });

  describe('register submission', () => {
    it('should call signUpWithEmail with exact email, password, and name', async () => {
      vi.mocked(signUpWithEmail).mockResolvedValue({ success: true });
      const user = userEvent.setup();
      renderWithMantine(<LoginFormContent />);

      const name = 'Test User';
      const email = 'test@example.com';
      const password = 'password123';

      await user.click(screen.getByRole('button', { name: /registrate/i }));

      await user.type(screen.getByLabelText(/nombre/i), name);
      await user.type(screen.getByLabelText(/email/i), email);
      await user.type(screen.getByPlaceholderText('Tu contrasena'), password);
      await user.type(screen.getByPlaceholderText(/repite tu contrasena/i), password);
      await user.click(screen.getByRole('button', { name: /crear cuenta/i }));

      await waitFor(() => {
        expect(signUpWithEmail).toHaveBeenCalledWith(email, password, name);
        expect(signUpWithEmail).toHaveBeenCalledTimes(1);
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
        // Verify the notification color is blue for confirmation
        expect(notifications.show).toHaveBeenCalledWith(
          expect.objectContaining({
            color: 'blue',
          })
        );
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
        // Verify heading changed back to login
        expect(screen.getByRole('heading', { name: 'Iniciar Sesion' })).toBeInTheDocument();
        // Verify success notification color
        expect(notifications.show).toHaveBeenCalledWith(
          expect.objectContaining({
            color: 'green',
            title: 'Cuenta creada',
          })
        );
      });
    });

    it.each([
      ['user1@example.com', 'User One', 'Password1'],
      ['user2@example.com', 'User Two', 'MyPass123'],
      ['user3@example.com', 'User Three', 'StrongPwd9'],
    ])('should register different users correctly', async (email, name, password) => {
      vi.mocked(signUpWithEmail).mockResolvedValue({ success: true, needsEmailConfirmation: false });
      const user = userEvent.setup();
      renderWithMantine(<LoginFormContent />);

      await user.click(screen.getByRole('button', { name: /registrate/i }));

      await user.type(screen.getByLabelText(/nombre/i), name);
      await user.type(screen.getByLabelText(/email/i), email);
      await user.type(screen.getByPlaceholderText('Tu contrasena'), password);
      await user.type(screen.getByPlaceholderText(/repite tu contrasena/i), password);
      await user.click(screen.getByRole('button', { name: /crear cuenta/i }));

      await waitFor(() => {
        expect(signUpWithEmail).toHaveBeenCalledWith(email, password, name);
      });
    });
  });

  describe('Google OAuth', () => {
    it('should call signInWithGoogle exactly once when clicking Google button', async () => {
      vi.mocked(signInWithGoogle).mockResolvedValue({ success: true });
      const user = userEvent.setup();
      renderWithMantine(<LoginFormContent />);

      await user.click(screen.getByRole('button', { name: /google/i }));

      await waitFor(() => {
        expect(signInWithGoogle).toHaveBeenCalled();
        expect(signInWithGoogle).toHaveBeenCalledTimes(1);
      });
    });

    it('should show error notification with correct color on Google login failure', async () => {
      const errorMsg = 'No se pudo conectar con Google';
      vi.mocked(signInWithGoogle).mockResolvedValue({
        success: false,
        error: errorMsg,
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

    it('should set loading state during Google login attempt', async () => {
      vi.mocked(signInWithGoogle).mockImplementation(
        () => new Promise((resolve) => setTimeout(() => resolve({ success: true }), 100))
      );
      const user = userEvent.setup();
      renderWithMantine(<LoginFormContent />);

      const googleButton = screen.getByRole('button', { name: /google/i });
      await user.click(googleButton);

      // Button should be in loading state
      expect(googleButton).toHaveAttribute('data-loading', 'true');
    });
  });

  describe('loading state', () => {
    it('should disable form during login submission', async () => {
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

      // Button should be in loading state (data-loading='true')
      expect(submitButton).toHaveAttribute('data-loading', 'true');
    });

    it('should disable form during register submission', async () => {
      vi.mocked(signUpWithEmail).mockImplementation(
        () => new Promise((resolve) => setTimeout(() => resolve({ success: true }), 100))
      );
      const user = userEvent.setup();
      renderWithMantine(<LoginFormContent />);

      await user.click(screen.getByRole('button', { name: /registrate/i }));

      await user.type(screen.getByLabelText(/nombre/i), 'Test User');
      await user.type(screen.getByLabelText(/email/i), 'test@example.com');
      await user.type(screen.getByPlaceholderText('Tu contrasena'), 'password123');
      await user.type(screen.getByPlaceholderText(/repite tu contrasena/i), 'password123');

      const submitButton = screen.getByRole('button', { name: /crear cuenta/i });
      await user.click(submitButton);

      // Button should be in loading state
      expect(submitButton).toHaveAttribute('data-loading', 'true');
    });

    it('should clear loading state after successful submission', async () => {
      vi.mocked(signInWithEmail).mockResolvedValue({ success: true });
      const user = userEvent.setup();
      renderWithMantine(<LoginFormContent />);

      await user.type(screen.getByLabelText(/email/i), 'test@example.com');
      await user.type(screen.getByLabelText(/contrasena/i), 'password123');

      const submitButton = screen.getByRole('button', { name: /iniciar sesion/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(submitButton).not.toHaveAttribute('data-loading', 'true');
      });
    });

    it('should clear loading state after failed submission', async () => {
      vi.mocked(signInWithEmail).mockResolvedValue({
        success: false,
        error: 'Auth failed',
      });
      const user = userEvent.setup();
      renderWithMantine(<LoginFormContent />);

      await user.type(screen.getByLabelText(/email/i), 'test@example.com');
      await user.type(screen.getByLabelText(/contrasena/i), 'wrongpassword');

      const submitButton = screen.getByRole('button', { name: /iniciar sesion/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(submitButton).not.toHaveAttribute('data-loading', 'true');
      });
    });
  });
});
