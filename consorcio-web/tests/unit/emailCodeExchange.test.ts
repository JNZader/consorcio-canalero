import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockAdapter } = vi.hoisted(() => ({
  mockAdapter: {
    login: vi.fn(),
    register: vi.fn(),
    loginWithGoogle: vi.fn(),
    logout: vi.fn(),
  },
}));

vi.mock('../../src/lib/auth/index', () => ({
  authAdapter: mockAdapter,
}));

vi.mock('../../src/stores/authStore', () => ({
  useAuthStore: Object.assign(
    () => ({ user: null, session: null, profile: null, loading: false, error: null }),
    { getState: () => ({ reset: vi.fn(), profile: null }) }
  ),
}));

vi.mock('../../src/lib/logger', () => ({
  logger: {
    error: vi.fn(),
    warn: vi.fn(),
    info: vi.fn(),
    debug: vi.fn(),
  },
}));

import { exchangeEmailCode } from '../../src/lib/auth';
import { EMAIL_CODE_EXCHANGE_STORAGE_KEYS } from '../../src/lib/auth/emailCodeExchangeStorage';

function exchangeBodies(fetchMock: ReturnType<typeof vi.fn>) {
  return fetchMock.mock.calls.map(
    ([, options]) =>
      JSON.parse(String(options?.body)) as {
        code: string;
        purpose: string;
        exchange_id: string;
      }
  );
}

function response(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: vi.fn().mockResolvedValue(body),
  } as unknown as Response;
}

describe('exchangeEmailCode', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.sessionStorage.clear();
    global.fetch = vi.fn();
  });

  it('sends exchange_id and clears storage after a successful exchange', async () => {
    const fetchMock = global.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue(response(200, { token: 'resolved-token' }));

    await expect(exchangeEmailCode('VERIFY42', 'verify')).resolves.toEqual({
      status: 'success',
      token: 'resolved-token',
    });

    expect(exchangeBodies(fetchMock)).toEqual([
      {
        code: 'VERIFY42',
        purpose: 'verify',
        exchange_id: expect.any(String),
      },
    ]);
    expect(window.sessionStorage.getItem(EMAIL_CODE_EXCHANGE_STORAGE_KEYS.verify)).toBeNull();
  });

  it('clears storage after a terminal 4xx invalid or expired response', async () => {
    const fetchMock = global.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue(response(400, { detail: 'Código inválido o expirado.' }));

    await expect(exchangeEmailCode('RESET001', 'reset')).resolves.toEqual({
      status: 'terminal-error',
      reason: 'invalid-or-expired',
    });
    expect(window.sessionStorage.getItem(EMAIL_CODE_EXCHANGE_STORAGE_KEYS.reset)).toBeNull();
  });

  it('retains the same exchange ID across a network failure and retry', async () => {
    const fetchMock = global.fetch as ReturnType<typeof vi.fn>;
    fetchMock
      .mockRejectedValueOnce(new TypeError('network unavailable'))
      .mockResolvedValueOnce(response(200, { token: 'recovered-token' }));

    await expect(exchangeEmailCode('RESET001', 'reset')).resolves.toEqual({
      status: 'retryable-error',
      reason: 'network',
    });
    expect(window.sessionStorage.getItem(EMAIL_CODE_EXCHANGE_STORAGE_KEYS.reset)).not.toBeNull();

    await expect(exchangeEmailCode('RESET001', 'reset')).resolves.toEqual({
      status: 'success',
      token: 'recovered-token',
    });

    const [firstAttempt, retry] = exchangeBodies(fetchMock);
    expect(retry.exchange_id).toBe(firstAttempt.exchange_id);
    expect(window.sessionStorage.getItem(EMAIL_CODE_EXCHANGE_STORAGE_KEYS.reset)).toBeNull();
  });

  it('retains storage for 5xx and malformed successful responses', async () => {
    const fetchMock = global.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValueOnce(response(503, null));

    await expect(exchangeEmailCode('VERIFY42', 'verify')).resolves.toEqual({
      status: 'retryable-error',
      reason: 'server',
    });
    const storedAfterServerError = window.sessionStorage.getItem(
      EMAIL_CODE_EXCHANGE_STORAGE_KEYS.verify
    );
    expect(storedAfterServerError).not.toBeNull();

    fetchMock.mockResolvedValueOnce(response(200, { token: 42 }));
    await expect(exchangeEmailCode('VERIFY42', 'verify')).resolves.toEqual({
      status: 'retryable-error',
      reason: 'malformed-response',
    });
    expect(window.sessionStorage.getItem(EMAIL_CODE_EXCHANGE_STORAGE_KEYS.verify)).toBe(
      storedAfterServerError
    );

    const [serverAttempt, malformedAttempt] = exchangeBodies(fetchMock);
    expect(malformedAttempt.exchange_id).toBe(serverAttempt.exchange_id);
  });

  it('deduplicates parallel exchange attempts for the same code and purpose', async () => {
    const fetchMock = global.fetch as ReturnType<typeof vi.fn>;
    let resolveResponse: ((response: Response) => void) | undefined;
    fetchMock.mockImplementation(
      () =>
        new Promise<Response>((resolve) => {
          resolveResponse = resolve;
        })
    );

    const first = exchangeEmailCode('VERIFY42', 'verify');
    const repeatedClick = exchangeEmailCode('VERIFY42', 'verify');

    expect(fetchMock).toHaveBeenCalledTimes(1);
    resolveResponse?.(response(200, { token: 'resolved-token' }));

    await expect(Promise.all([first, repeatedClick])).resolves.toEqual([
      { status: 'success', token: 'resolved-token' },
      { status: 'success', token: 'resolved-token' },
    ]);
  });
});
