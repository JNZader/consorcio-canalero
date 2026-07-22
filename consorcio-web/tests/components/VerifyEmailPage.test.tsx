import { MantineProvider } from '@mantine/core';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import VerifyEmailPage from '../../src/components/auth/VerifyEmailPage';
import { exchangeCodeForToken, verifyEmailWithToken } from '../../src/lib/auth';

vi.mock('../../src/lib/auth', () => ({
  exchangeCodeForToken: vi.fn(),
  verifyEmailWithToken: vi.fn(),
}));

function renderPage(code: string) {
  return render(
    <MantineProvider>
      <VerifyEmailPage code={code} token="" />
    </MantineProvider>
  );
}

describe('VerifyEmailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('exchanges the email code and verifies the resolved token', async () => {
    vi.mocked(exchangeCodeForToken).mockResolvedValue('resolved-verify-token');
    vi.mocked(verifyEmailWithToken).mockResolvedValue({ success: true });

    renderPage('VERIFY42');

    await waitFor(() => {
      expect(exchangeCodeForToken).toHaveBeenCalledWith('VERIFY42', 'verify');
      expect(verifyEmailWithToken).toHaveBeenCalledWith('resolved-verify-token');
    });
    expect(await screen.findByText(/correo verificado/i)).toBeInTheDocument();
  });
});
