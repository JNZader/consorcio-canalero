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

import { completeEmailCodeExchange, exchangeEmailCode } from '../../src/lib/auth';
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

  it('clears only the exact exchange after downstream success', async () => {
    const fetchMock = global.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue(response(200, { token: 'resolved-token' }));

    const result = await exchangeEmailCode('VERIFY42', 'verify');
    expect(result).toMatchObject({ status: 'success', token: 'resolved-token' });
    if (result.status !== 'success') throw new Error('Expected a successful exchange');

    const [request] = exchangeBodies(fetchMock);
    expect(request).toEqual({
      code: 'VERIFY42',
      purpose: 'verify',
      exchange_id: expect.any(String),
    });
    expect(result.handle).toEqual({
      code: 'VERIFY42',
      purpose: 'verify',
      exchangeId: request.exchange_id,
    });
    expect(window.sessionStorage.getItem(EMAIL_CODE_EXCHANGE_STORAGE_KEYS.verify)).not.toBeNull();

    completeEmailCodeExchange(result.handle);
    expect(window.sessionStorage.getItem(EMAIL_CODE_EXCHANGE_STORAGE_KEYS.verify)).toBeNull();
  });

  it('does not clear a newer exchange when an older completion arrives late', async () => {
    const fetchMock = global.fetch as ReturnType<typeof vi.fn>;
    fetchMock
      .mockResolvedValueOnce(response(200, { token: 'token-a' }))
      .mockResolvedValueOnce(response(200, { token: 'token-b' }));

    const exchangeA = await exchangeEmailCode('VERIFY-A', 'verify');
    const exchangeB = await exchangeEmailCode('VERIFY-B', 'verify');
    if (exchangeA.status !== 'success' || exchangeB.status !== 'success') {
      throw new Error('Expected successful exchanges');
    }

    const storedB = window.sessionStorage.getItem(EMAIL_CODE_EXCHANGE_STORAGE_KEYS.verify);
    expect(storedB).not.toBeNull();

    completeEmailCodeExchange(exchangeA.handle);

    expect(window.sessionStorage.getItem(EMAIL_CODE_EXCHANGE_STORAGE_KEYS.verify)).toBe(storedB);
    expect(JSON.parse(String(storedB))).toEqual({
      code: 'VERIFY-B',
      purpose: 'verify',
      exchangeId: exchangeB.handle.exchangeId,
    });
  });

  it('retains storage after a terminal exchange response until a new code replaces it', async () => {
    const fetchMock = global.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue(response(400, { detail: 'Código inválido o expirado.' }));

    await expect(exchangeEmailCode('RESET001', 'reset')).resolves.toEqual({
      status: 'terminal-error',
      reason: 'invalid-or-expired',
    });
    expect(window.sessionStorage.getItem(EMAIL_CODE_EXCHANGE_STORAGE_KEYS.reset)).not.toBeNull();
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

    const recovered = await exchangeEmailCode('RESET001', 'reset');
    expect(recovered).toMatchObject({
      status: 'success',
      token: 'recovered-token',
    });
    if (recovered.status !== 'success') throw new Error('Expected a successful retry');

    const [firstAttempt, retry] = exchangeBodies(fetchMock);
    expect(retry.exchange_id).toBe(firstAttempt.exchange_id);
    expect(recovered.handle.exchangeId).toBe(firstAttempt.exchange_id);
    expect(window.sessionStorage.getItem(EMAIL_CODE_EXCHANGE_STORAGE_KEYS.reset)).not.toBeNull();

    completeEmailCodeExchange(recovered.handle);
    expect(window.sessionStorage.getItem(EMAIL_CODE_EXCHANGE_STORAGE_KEYS.reset)).toBeNull();
  });

  it('reuses the original completion handle after downstream failure and reload', async () => {
    const fetchMock = global.fetch as ReturnType<typeof vi.fn>;
    fetchMock
      .mockResolvedValueOnce(response(200, { token: 'first-token' }))
      .mockResolvedValueOnce(response(200, { token: 'replayed-token' }));

    const beforeReload = await exchangeEmailCode('RESET001', 'reset');
    if (beforeReload.status !== 'success') throw new Error('Expected a successful exchange');

    const persisted = window.sessionStorage.getItem(EMAIL_CODE_EXCHANGE_STORAGE_KEYS.reset);
    expect(persisted).not.toBeNull();

    const afterReload = await exchangeEmailCode('RESET001', 'reset');
    if (afterReload.status !== 'success') throw new Error('Expected a replayed exchange');

    expect(afterReload.handle).toEqual(beforeReload.handle);
    expect(afterReload.handle).toEqual(JSON.parse(String(persisted)));
    const [firstAttempt, replayedAttempt] = exchangeBodies(fetchMock);
    expect(replayedAttempt.exchange_id).toBe(firstAttempt.exchange_id);
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
      {
        status: 'success',
        token: 'resolved-token',
        handle: expect.objectContaining({ code: 'VERIFY42', purpose: 'verify' }),
      },
      {
        status: 'success',
        token: 'resolved-token',
        handle: expect.objectContaining({ code: 'VERIFY42', purpose: 'verify' }),
      },
    ]);
  });
});
