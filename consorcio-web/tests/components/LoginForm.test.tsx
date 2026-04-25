import { MantineProvider } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { LoginFormContent } from '../../src/components/LoginForm';
import { signInWithEmail, signInWithGoogle, signUpWithEmail } from '../../src/lib/auth';
import { logger } from '../../src/lib/logger';

vi.mock('../../src/lib/auth', () => ({
  signInWithEmail: vi.fn(),
  signUpWithEmail: vi.fn(),
  signInWithGoogle: vi.fn(),
}));

vi.mock('@mantine/notifications', () => ({
  notifications: {
    show: vi.fn(),
  },
}));

vi.mock('../../src/lib/logger', () => ({
  logger: {
    error: vi.fn(),
    warn: vi.fn(),
    info: vi.fn(),
    debug: vi.fn(),
  },
}));

const mockLocation = { href: '' };
Object.defineProperty(window, 'location', {
  value: mockLocation,
  writable: true,
});

function renderForm() {
  return render(
    <MantineProvider>
      <LoginFormContent />
    </MantineProvider>
  );
}

async function switchToRegister(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: /registrate/i }));
}

function getPasswordInputs() {
  return screen
    .getAllByLabelText(/contrasena/i)
    .filter((element) => element.tagName === 'INPUT');
}

async function submitLogin(user: ReturnType<typeof userEvent.setup>, email: string, password: string) {
  await user.type(screen.getByLabelText(/email/i), email);
  await user.type(getPasswordInputs()[0], password);
  await user.click(screen.getByRole('button', { name: /iniciar sesion/i }));
}

async function submitRegister(
  user: ReturnType<typeof userEvent.setup>,
  values: { nombre: string; email: string; password: string; confirmPassword: string }
) {
  await switchToRegister(user);
  await user.type(screen.getByLabelText(/nombre/i), values.nombre);
  await user.type(screen.getByLabelText(/email/i), values.email);
  const passwordInputs = getPasswordInputs();
  await user.type(passwordInputs[0], values.password);
  await user.type(passwordInputs[1], values.confirmPassword);
  await user.click(screen.getByRole('button', { name: /crear cuenta/i }));
}

describe('LoginForm', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockLocation.href = '';
  });

  it('renders login mode by default and switches to register mode', async () => {
    const user = userEvent.setup();
    renderForm();

    expect(screen.getByRole('heading', { name: /iniciar sesion/i })).toBeInTheDocument();
    expect(screen.getByText('Consorcio Canalero')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /google/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /olvidaste tu contrasena/i })).toHaveAttribute(
      'href',
      '/forgot-password'
    );

    await switchToRegister(user);

    expect(screen.getByRole('heading', { name: /crear cuenta/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/nombre/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/confirmar contrasena/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /inicia sesion/i })).toBeInTheDocument();
  });

  it('validates login fields before submit', async () => {
    const user = userEvent.setup();
    renderForm();

    await submitLogin(user, 'correo-invalido', '1234567');

    expect(await screen.findByText(/email invalido/i)).toBeInTheDocument();
    expect(screen.getByText(/al menos 8 caracteres/i)).toBeInTheDocument();
    expect(signInWithEmail).not.toHaveBeenCalled();
  });

  it('connects login validation errors to required fields', async () => {
    const user = userEvent.setup();
    renderForm();

    await user.click(screen.getByRole('button', { name: /iniciar sesion/i }));

    const email = screen.getByLabelText(/email/i);
    const password = screen.getByPlaceholderText('Tu contrasena');

    await waitFor(() => {
      expect(email).toHaveAttribute('aria-invalid', 'true');
      expect(email.getAttribute('aria-describedby')).toContain('login-email-error');
      expect(password).toHaveAttribute('aria-invalid', 'true');
      expect(password.getAttribute('aria-describedby')).toContain('login-password-error');
    });

    expect(screen.getByText(/el email es requerido/i)).toHaveAttribute('role', 'alert');
    expect(screen.getByText(/al menos 8 caracteres/i)).toHaveAttribute('role', 'alert');
    expect(signInWithEmail).not.toHaveBeenCalled();
  });

  it('connects register validation errors to required fields', async () => {
    const user = userEvent.setup();
    renderForm();

    await switchToRegister(user);
    await user.type(screen.getByLabelText(/email/i), 'test@example.com');
    const passwordInputs = getPasswordInputs();
    await user.type(passwordInputs[0], 'password');
    await user.type(passwordInputs[1], 'different');
    await user.click(screen.getByRole('button', { name: /crear cuenta/i }));

    const name = screen.getByLabelText(/nombre/i);
    const password = screen.getByPlaceholderText('Tu contrasena');
    const confirmPassword = screen.getByPlaceholderText('Repite tu contrasena');

    await waitFor(() => {
      expect(name).toHaveAttribute('aria-invalid', 'true');
      expect(name.getAttribute('aria-describedby')).toContain('login-name-error');
      expect(password).toHaveAttribute('aria-invalid', 'true');
      expect(password.getAttribute('aria-describedby')).toContain('login-password-error');
      expect(confirmPassword).toHaveAttribute('aria-invalid', 'true');
      expect(confirmPassword.getAttribute('aria-describedby')).toContain(
        'login-confirm-password-error'
      );
    });

    expect(screen.getByText(/ingresa tu nombre/i)).toHaveAttribute('role', 'alert');
    expect(screen.getByText(/al menos un numero/i)).toHaveAttribute('role', 'alert');
    expect(screen.getByText(/no coinciden/i)).toHaveAttribute('role', 'alert');
    expect(signUpWithEmail).not.toHaveBeenCalled();
  });

  it('logs in successfully and redirects to admin', async () => {
    const user = userEvent.setup();
    vi.mocked(signInWithEmail).mockResolvedValue({ success: true });
    renderForm();

    await submitLogin(user, 'test@example.com', 'password123');

    await waitFor(() => {
      expect(signInWithEmail).toHaveBeenCalledWith('test@example.com', 'password123');
    });
    expect(notifications.show).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Bienvenido', color: 'green' })
    );
    expect(mockLocation.href).toBe('/admin');
  });

  it('shows auth errors on failed login', async () => {
    const user = userEvent.setup();
    vi.mocked(signInWithEmail).mockResolvedValue({
      success: false,
      error: 'Email o contrasena incorrectos',
    });
    renderForm();

    await submitLogin(user, 'test@example.com', 'password123');

    await waitFor(() => {
      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Error al iniciar sesion',
          message: 'Email o contrasena incorrectos',
          color: 'red',
        })
      );
    });
  });

  it('validates register-specific fields', async () => {
    const user = userEvent.setup();
    renderForm();

    await submitRegister(user, {
      nombre: 'A',
      email: 'test@example.com',
      password: 'password',
      confirmPassword: 'different',
    });

    expect(await screen.findByText(/ingresa tu nombre/i)).toBeInTheDocument();
    expect(screen.getByText(/al menos un numero/i)).toBeInTheDocument();
    expect(screen.getByText(/no coinciden/i)).toBeInTheDocument();
    expect(signUpWithEmail).not.toHaveBeenCalled();
  });

  it('shows confirmation alert when registration requires email confirmation', async () => {
    const user = userEvent.setup();
    vi.mocked(signUpWithEmail).mockResolvedValue({
      success: true,
      needsEmailConfirmation: true,
    });
    renderForm();

    await submitRegister(user, {
      nombre: 'Test User',
      email: 'test@example.com',
      password: 'password123',
      confirmPassword: 'password123',
    });

    await waitFor(() => {
      expect(signUpWithEmail).toHaveBeenCalledWith('test@example.com', 'password123', 'Test User');
    });
    expect(screen.getByText(/confirma tu email/i)).toBeInTheDocument();
    expect(notifications.show).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Cuenta creada', color: 'blue' })
    );
  });

  it('returns to login mode after successful registration without confirmation', async () => {
    const user = userEvent.setup();
    vi.mocked(signUpWithEmail).mockResolvedValue({
      success: true,
      needsEmailConfirmation: false,
    });
    renderForm();

    await submitRegister(user, {
      nombre: 'Test User',
      email: 'test@example.com',
      password: 'password123',
      confirmPassword: 'password123',
    });

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /iniciar sesion/i })).toBeInTheDocument();
    });
    expect(notifications.show).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Cuenta creada', color: 'green' })
    );
  });

  it('shows provider errors for Google auth', async () => {
    const user = userEvent.setup();
    vi.mocked(signInWithGoogle).mockResolvedValue({
      success: false,
      error: 'No se pudo conectar con Google',
    });
    renderForm();

    await user.click(screen.getByRole('button', { name: /google/i }));

    await waitFor(() => {
      expect(signInWithGoogle).toHaveBeenCalledTimes(1);
    });
    expect(notifications.show).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Error con Google',
        message: 'No se pudo conectar con Google',
        color: 'red',
      })
    );
  });

  it('logs and shows a generic notification on unexpected auth errors', async () => {
    const user = userEvent.setup();
    vi.mocked(signInWithEmail).mockRejectedValue(new Error('boom'));
    renderForm();

    await submitLogin(user, 'test@example.com', 'password123');

    await waitFor(() => {
      expect(logger.error).toHaveBeenCalled();
    });
    expect(notifications.show).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Error',
        message: 'Ocurrio un error inesperado. Intenta de nuevo.',
        color: 'red',
      })
    );
  });
});
