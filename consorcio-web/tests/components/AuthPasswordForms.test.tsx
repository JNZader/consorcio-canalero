import { MantineProvider } from '@mantine/core';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ForgotPasswordForm from '../../src/components/auth/ForgotPasswordForm';
import ResetPasswordForm from '../../src/components/auth/ResetPasswordForm';
import { exchangeEmailCode, resetPassword, resetPasswordWithToken } from '../../src/lib/auth';

vi.mock('../../src/lib/auth', () => ({
  exchangeEmailCode: vi.fn(),
  resetPassword: vi.fn(),
  resetPasswordWithToken: vi.fn(),
}));

function renderWithProvider(element: React.ReactNode) {
  return render(<MantineProvider>{element}</MantineProvider>);
}

describe('Auth password forms', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('connects forgot password email validation error to the field', async () => {
    const user = userEvent.setup();
    renderWithProvider(<ForgotPasswordForm />);

    await user.click(screen.getByRole('button', { name: /enviar enlace de recuperacion/i }));

    const email = screen.getByLabelText(/email/i);

    await waitFor(() => {
      expect(email).toHaveAttribute('aria-invalid', 'true');
      expect(email.getAttribute('aria-describedby')).toContain('forgot-password-email-error');
    });

    expect(screen.getByText(/el email es requerido/i)).toHaveAttribute('role', 'alert');
    expect(resetPassword).not.toHaveBeenCalled();
  });

  it('connects reset password validation errors to required fields', async () => {
    const user = userEvent.setup();
    renderWithProvider(<ResetPasswordForm token="reset-token" />);

    await user.type(screen.getByPlaceholderText('Minimo 8 caracteres'), 'password');
    await user.type(screen.getByPlaceholderText('Repite la nueva contrasena'), 'different');
    await user.click(screen.getByRole('button', { name: /restablecer contrasena/i }));

    const password = screen.getByPlaceholderText('Minimo 8 caracteres');
    const confirmPassword = screen.getByPlaceholderText('Repite la nueva contrasena');

    await waitFor(() => {
      expect(password).toHaveAttribute('aria-invalid', 'true');
      expect(password.getAttribute('aria-describedby')).toContain('reset-password-error');
      expect(confirmPassword).toHaveAttribute('aria-invalid', 'true');
      expect(confirmPassword.getAttribute('aria-describedby')).toContain(
        'reset-confirm-password-error'
      );
    });

    expect(screen.getByText(/al menos un numero/i)).toHaveAttribute('role', 'alert');
    expect(screen.getByText(/no coinciden/i)).toHaveAttribute('role', 'alert');
    expect(resetPasswordWithToken).not.toHaveBeenCalled();
    expect(exchangeEmailCode).not.toHaveBeenCalled();
  });

  it('offers a retry after a temporary code exchange failure and then renders the form', async () => {
    const user = userEvent.setup();
    vi.mocked(exchangeEmailCode)
      .mockResolvedValueOnce({ status: 'retryable-error', reason: 'server' })
      .mockResolvedValueOnce({ status: 'success', token: 'resolved-reset-token' });

    renderWithProvider(<ResetPasswordForm token="" code="RESET001" />);

    const retry = await screen.findByRole('button', { name: /reintentar verificación/i });
    expect(screen.getByText(/problema temporal de conexión/i)).toBeInTheDocument();
    expect(screen.queryByText(/este enlace de recuperacion es invalido/i)).not.toBeInTheDocument();

    await user.click(retry);

    expect(await screen.findByRole('heading', { name: /nueva contrasena/i })).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Minimo 8 caracteres')).toBeInTheDocument();
    expect(exchangeEmailCode).toHaveBeenCalledTimes(2);
    expect(exchangeEmailCode).toHaveBeenNthCalledWith(2, 'RESET001', 'reset');
  });

  it('shows the invalid-link state after a terminal reset-code response', async () => {
    vi.mocked(exchangeEmailCode).mockResolvedValue({
      status: 'terminal-error',
      reason: 'invalid-or-expired',
    });

    renderWithProvider(<ResetPasswordForm token="" code="EXPIRED1" />);

    expect(await screen.findByText(/este enlace de recuperacion es invalido o expiró/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /reintentar/i })).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText('Minimo 8 caracteres')).not.toBeInTheDocument();
  });
});
