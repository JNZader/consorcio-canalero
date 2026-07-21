import { MantineProvider } from '@mantine/core';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import VerifyEmailPage from '../../src/components/auth/VerifyEmailPage';
import { completeEmailCodeExchange, exchangeEmailCode, verifyEmailWithToken } from '../../src/lib/auth';

vi.mock('../../src/lib/auth', () => ({
  completeEmailCodeExchange: vi.fn(),
  exchangeEmailCode: vi.fn(),
  verifyEmailWithToken: vi.fn(),
}));

const VERIFY_EXCHANGE_HANDLE = {
  code: 'VERIFY42',
  purpose: 'verify' as const,
  exchangeId: '00000000-0000-4000-8000-000000000042',
};

function renderPage({ code = '', token = '' }: { code?: string; token?: string }) {
  return render(
    <MantineProvider>
      <VerifyEmailPage code={code} token={token} />
    </MantineProvider>
  );
}

describe('VerifyEmailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('exchanges the email code and verifies the resolved token', async () => {
    vi.mocked(exchangeEmailCode).mockResolvedValue({
      status: 'success',
      token: 'resolved-verify-token',
      handle: VERIFY_EXCHANGE_HANDLE,
    });
    vi.mocked(verifyEmailWithToken).mockResolvedValue({ success: true });

    renderPage({ code: 'VERIFY42' });

    await waitFor(() => {
      expect(exchangeEmailCode).toHaveBeenCalledWith('VERIFY42', 'verify');
      expect(verifyEmailWithToken).toHaveBeenCalledWith('resolved-verify-token');
    });
    expect(await screen.findByText(/correo verificado/i)).toBeInTheDocument();
    expect(completeEmailCodeExchange).toHaveBeenCalledWith(VERIFY_EXCHANGE_HANDLE);
  });

  it('retains recovery metadata when downstream verification fails', async () => {
    vi.mocked(exchangeEmailCode).mockResolvedValue({
      status: 'success',
      token: 'resolved-verify-token',
      handle: VERIFY_EXCHANGE_HANDLE,
    });
    vi.mocked(verifyEmailWithToken).mockResolvedValue({
      success: false,
      error: 'temporary downstream failure',
    });

    renderPage({ code: 'VERIFY42' });

    expect(await screen.findByText('temporary downstream failure')).toBeInTheDocument();
    expect(completeEmailCodeExchange).not.toHaveBeenCalled();
  });

  it('offers a retry after a temporary failure instead of declaring the link invalid', async () => {
    const user = userEvent.setup();
    vi.mocked(exchangeEmailCode)
      .mockResolvedValueOnce({ status: 'retryable-error', reason: 'network' })
      .mockResolvedValueOnce({
        status: 'success',
        token: 'resolved-after-retry',
        handle: VERIFY_EXCHANGE_HANDLE,
      });
    vi.mocked(verifyEmailWithToken).mockResolvedValue({ success: true });

    renderPage({ code: 'VERIFY42' });

    const retry = await screen.findByRole('button', { name: /reintentar verificación/i });
    expect(screen.getByText(/problema temporal de conexión/i)).toBeInTheDocument();
    expect(screen.queryByText(/enlace inválido/i)).not.toBeInTheDocument();

    await user.click(retry);

    expect(await screen.findByText(/correo verificado/i)).toBeInTheDocument();
    expect(exchangeEmailCode).toHaveBeenCalledTimes(2);
    expect(exchangeEmailCode).toHaveBeenNthCalledWith(2, 'VERIFY42', 'verify');
  });

  it('shows the invalid-link state after a terminal exchange response', async () => {
    vi.mocked(exchangeEmailCode).mockResolvedValue({
      status: 'terminal-error',
      reason: 'invalid-or-expired',
    });

    renderPage({ code: 'EXPIRED1' });

    expect(await screen.findByText(/enlace de verificación es inválido o expiró/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /reintentar/i })).not.toBeInTheDocument();
    expect(verifyEmailWithToken).not.toHaveBeenCalled();
  });

  it('keeps the legacy token route without calling the code exchange', async () => {
    vi.mocked(verifyEmailWithToken).mockResolvedValue({ success: true });

    renderPage({ token: 'legacy-verification-token' });

    expect(await screen.findByText(/correo verificado/i)).toBeInTheDocument();
    expect(exchangeEmailCode).not.toHaveBeenCalled();
    expect(verifyEmailWithToken).toHaveBeenCalledWith('legacy-verification-token');
  });
});
