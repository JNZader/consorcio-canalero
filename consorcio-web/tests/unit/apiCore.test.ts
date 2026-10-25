import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mockGetAccessToken = vi.fn();
const mockReplaceAccessToken = vi.fn();
const mockClearTokens = vi.fn();

vi.mock('../../src/lib/auth/index', () => ({
  authAdapter: {
    getAccessToken: mockGetAccessToken,
    replaceAccessToken: mockReplaceAccessToken,
    clearTokens: mockClearTokens,
  },
}));

describe('api core', () => {
  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
    global.fetch = vi.fn();
    window.localStorage.removeItem('consorcio_auth_logout_tombstone');
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('caches auth token and sends Authorization header', async () => {
    mockGetAccessToken.mockResolvedValue('jwt-123');
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      headers: new Headers(),
      json: async () => ({ ok: true }),
    });

    const { apiFetch, clearAuthTokenCache } = await import('../../src/lib/api/core');

    // Clear any cached token from previous imports
    clearAuthTokenCache();

    await apiFetch('/reports');
    await apiFetch('/reports');

    // Token is cached after first call, so getAccessToken is called once
    expect(mockGetAccessToken).toHaveBeenCalledTimes(1);
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v2/reports'),
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer jwt-123' }),
      })
    );
  });

  it('does not send a bearer cached in another tab context after a durable logout', async () => {
    mockGetAccessToken.mockResolvedValue('cached-before-logout');
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      headers: new Headers(),
      json: async () => ({ ok: true }),
    });

    const { apiFetch, clearAuthTokenCache } = await import('../../src/lib/api/core');
    clearAuthTokenCache();

    await apiFetch('/before-other-tab-logout');
    vi.mocked(window.localStorage.getItem).mockImplementation((key: string) =>
      key === 'consorcio_auth_logout_tombstone' ? 'logged-out' : null
    );
    await apiFetch('/after-other-tab-logout');
    vi.mocked(window.localStorage.getItem).mockImplementation(() => null);

    const calls = (global.fetch as ReturnType<typeof vi.fn>).mock.calls;
    expect(calls[0][1].headers.Authorization).toBe('Bearer cached-before-logout');
    expect(calls[1][1].headers.Authorization).toBeUndefined();
    expect(mockGetAccessToken).toHaveBeenCalledOnce();
  });

  it('does not deliver a bearer when logout wins the race while the token is loading', async () => {
    let resolveToken: ((token: string) => void) | undefined;
    let markTokenReadStarted: (() => void) | undefined;
    const tokenReadStarted = new Promise<void>((resolve) => {
      markTokenReadStarted = resolve;
    });
    mockGetAccessToken.mockImplementation(
      () =>
        new Promise<string>((resolve) => {
          resolveToken = resolve;
          markTokenReadStarted?.();
        })
    );

    const { getAuthToken, clearAuthTokenCache } = await import('../../src/lib/api/core');
    clearAuthTokenCache();
    const tokenRequest = getAuthToken();
    await tokenReadStarted;

    const { markLocalLogout } = await import('../../src/lib/auth/storage');
    markLocalLogout();
    resolveToken?.('must-not-be-delivered');

    await expect(tokenRequest).resolves.toBeNull();
    await expect(getAuthToken()).resolves.toBeNull();
    expect(mockGetAccessToken).toHaveBeenCalledOnce();
  });

  it('strips a caller-provided bearer immediately before send when logout is durable', async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      headers: new Headers(),
      json: async () => ({ ok: true }),
    });
    const { markLocalLogout } = await import('../../src/lib/auth/storage');
    markLocalLogout();

    const { apiFetch } = await import('../../src/lib/api/core');
    await apiFetch('/manual-bearer', {
      headers: { Authorization: 'Bearer stale-caller-token' },
    });

    const options = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0][1];
    expect(options.headers.Authorization).toBeUndefined();
  });

  it('refreshes a protected Admin GEE request once and retries with the new Bearer token', async () => {
    mockGetAccessToken.mockResolvedValueOnce('expired-token').mockResolvedValue('fresh-token');
    (global.fetch as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({
        ok: false,
        status: 401,
        headers: new Headers(),
        json: async () => ({ detail: 'Expired' }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers(),
        json: async () => ({ access_token: 'fresh-token' }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers(),
        json: async () => ({ tile_url: 'https://earthengine.googleapis.com/tiles/{z}/{x}/{y}' }),
      });

    const { apiFetch, clearAuthTokenCache } = await import('../../src/lib/api/core');
    clearAuthTokenCache();

    await apiFetch('/geo/gee/images/sentinel2?target_date=2026-03-05');

    expect(mockReplaceAccessToken).toHaveBeenCalledOnce();
    expect(global.fetch).toHaveBeenCalledTimes(3);
    const calls = (global.fetch as ReturnType<typeof vi.fn>).mock.calls;
    expect(calls[0][1].headers.Authorization).toBe('Bearer expired-token');
    expect(calls[1][0]).toContain('/api/v2/auth/jwt/refresh');
    expect(calls[2][1].headers.Authorization).toBe('Bearer fresh-token');
  });

  it('loads a protected photo as a blob with Bearer refresh semantics', async () => {
    const photoBlob = new Blob(['photo'], { type: 'image/png' });
    mockGetAccessToken.mockResolvedValueOnce('expired-token').mockResolvedValue('fresh-token');
    (global.fetch as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({
        ok: false,
        status: 401,
        headers: new Headers(),
        json: async () => ({ detail: 'Expired' }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers(),
        json: async () => ({ access_token: 'fresh-token' }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'image/png' }),
        blob: async () => photoBlob,
      });

    const { fetchAuthenticatedBlob, clearAuthTokenCache } = await import('../../src/lib/api/core');
    clearAuthTokenCache();

    await expect(fetchAuthenticatedBlob('/uploads/denuncias/report-photo.png')).resolves.toBe(
      photoBlob
    );

    const calls = (global.fetch as ReturnType<typeof vi.fn>).mock.calls;
    expect(calls[0][0]).toBe('http://localhost:8000/uploads/denuncias/report-photo.png');
    expect(String(calls[0][0])).not.toContain('access_token');
    expect(calls[0][1].headers.Authorization).toBe('Bearer expired-token');
    expect(calls[1][0]).toContain('/api/v2/auth/jwt/refresh');
    expect(calls[2][1].headers.Authorization).toBe('Bearer fresh-token');
  });

  it('does not silent-refresh a 401 after a durable local logout', async () => {
    const durableStorage = new Map<string, string>();
    vi.mocked(window.localStorage.getItem).mockImplementation(
      (key: string) => durableStorage.get(key) ?? null
    );
    vi.mocked(window.localStorage.setItem).mockImplementation((key: string, value: string) => {
      durableStorage.set(key, value);
    });
    vi.mocked(window.localStorage.removeItem).mockImplementation((key: string) => {
      durableStorage.delete(key);
    });
    const { markLocalLogout } = await import('../../src/lib/auth/storage');
    markLocalLogout();
    vi.resetModules(); // Simulate a hard reload; only the durable localStorage marker remains.
    mockGetAccessToken.mockResolvedValue(null);
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: false,
      status: 401,
      headers: new Headers(),
      json: async () => ({ detail: 'No bearer after reload' }),
    });

    const { apiFetch, clearAuthTokenCache } = await import('../../src/lib/api/core');
    clearAuthTokenCache();

    await expect(apiFetch('/reports')).rejects.toThrow(/sesión ha expirado/i);

    expect(global.fetch).toHaveBeenCalledOnce();
    expect(mockReplaceAccessToken).not.toHaveBeenCalled();
  });

  it('does not persist a refresh that started before the logout tombstone', async () => {
    mockGetAccessToken.mockResolvedValue('expired-token');
    let resolveRefresh: ((response: Response) => void) | undefined;
    let markRefreshStarted: (() => void) | undefined;
    const refreshStarted = new Promise<void>((resolve) => {
      markRefreshStarted = resolve;
    });
    (global.fetch as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({
        ok: false,
        status: 401,
        headers: new Headers(),
        json: async () => ({ detail: 'Expired' }),
      })
      .mockImplementationOnce(
        () =>
          new Promise<Response>((resolve) => {
            resolveRefresh = resolve;
            markRefreshStarted?.();
          })
      );

    const { apiFetch, clearAuthTokenCache } = await import('../../src/lib/api/core');
    clearAuthTokenCache();
    const request = apiFetch('/reports');
    await refreshStarted;

    const { markLocalLogout } = await import('../../src/lib/auth/storage');
    markLocalLogout();
    resolveRefresh?.(
      new Response(JSON.stringify({ access_token: 'must-not-survive' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    );

    await expect(request).rejects.toThrow(/sesión ha expirado/i);
    expect(mockReplaceAccessToken).not.toHaveBeenCalled();
    expect(global.fetch).toHaveBeenCalledTimes(2);
  });

  it('does not start a second refresh when the retried Admin GEE request is still 401', async () => {
    mockGetAccessToken.mockResolvedValueOnce('expired-token').mockResolvedValue('fresh-token');
    (global.fetch as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({
        ok: false,
        status: 401,
        headers: new Headers(),
        json: async () => ({ detail: 'Expired' }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers(),
        json: async () => ({ access_token: 'fresh-token' }),
      })
      .mockResolvedValueOnce({
        ok: false,
        status: 401,
        headers: new Headers(),
        json: async () => ({ detail: 'Role revoked' }),
      });

    const { apiFetch, clearAuthTokenCache } = await import('../../src/lib/api/core');
    clearAuthTokenCache();

    await expect(apiFetch('/geo/gee/images/visualizations')).rejects.toThrow('Role revoked');

    const refreshCalls = (global.fetch as ReturnType<typeof vi.fn>).mock.calls.filter(([url]) =>
      String(url).includes('/auth/jwt/refresh')
    );
    expect(refreshCalls).toHaveLength(1);
  });

  it('propagates caller AbortSignal cancellation for protected Admin GEE requests', async () => {
    mockGetAccessToken.mockResolvedValue('jwt-123');
    let markStarted: (() => void) | undefined;
    const started = new Promise<void>((resolve) => {
      markStarted = resolve;
    });
    (global.fetch as ReturnType<typeof vi.fn>).mockImplementation(
      (_url: string, options: RequestInit) =>
        new Promise((_resolve, reject) => {
          markStarted?.();
          options.signal?.addEventListener(
            'abort',
            () => reject(new DOMException('The operation was aborted', 'AbortError')),
            { once: true }
          );
        })
    );

    const { apiFetch, clearAuthTokenCache } = await import('../../src/lib/api/core');
    clearAuthTokenCache();
    const controller = new AbortController();
    const request = apiFetch('/geo/gee/images/available-dates', {
      signal: controller.signal,
    });
    await started;
    controller.abort();

    await expect(request).rejects.toMatchObject({ name: 'AbortError' });
    const forwardedSignal = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0][1].signal;
    expect(forwardedSignal.aborted).toBe(true);
  });

  it('keeps the original timeout across 401 refresh and a stalled retried JSON body', async () => {
    vi.useFakeTimers();
    mockGetAccessToken.mockResolvedValueOnce('expired-token').mockResolvedValue('fresh-token');
    let markRetriedBodyStarted: (() => void) | undefined;
    const retriedBodyStarted = new Promise<void>((resolve) => {
      markRetriedBodyStarted = resolve;
    });
    (global.fetch as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({
        ok: false,
        status: 401,
        headers: new Headers(),
        json: () =>
          new Promise((resolve) => {
            setTimeout(() => resolve({ detail: 'Expired' }), 20);
          }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers(),
        json: async () => ({ access_token: 'fresh-token' }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers(),
        json: () => {
          markRetriedBodyStarted?.();
          return new Promise<never>(() => {});
        },
      });

    const { apiFetch, clearAuthTokenCache } = await import('../../src/lib/api/core');
    clearAuthTokenCache();
    const request = apiFetch('/retry-then-stall', { timeout: 25 });
    const observedRejection = request.catch((error: unknown) => error);

    await vi.advanceTimersByTimeAsync(20);
    await retriedBodyStarted;
    const calls = (global.fetch as ReturnType<typeof vi.fn>).mock.calls;
    expect(calls[1][1].signal).toBe(calls[0][1].signal);
    expect(calls[2][1].signal).toBe(calls[0][1].signal);
    await vi.advanceTimersByTimeAsync(5);

    await expect(observedRejection).resolves.toEqual(
      new Error('La solicitud excedió el tiempo límite (0.025s)')
    );
  });

  it('uses the caller abort scope across 401 refresh and a stalled retried blob body', async () => {
    mockGetAccessToken.mockResolvedValueOnce('expired-token').mockResolvedValue('fresh-token');
    let markRetriedBodyStarted: (() => void) | undefined;
    const retriedBodyStarted = new Promise<void>((resolve) => {
      markRetriedBodyStarted = resolve;
    });
    (global.fetch as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({
        ok: false,
        status: 401,
        headers: new Headers(),
        json: async () => ({ detail: 'Expired' }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers(),
        json: async () => ({ access_token: 'fresh-token' }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers(),
        blob: () => {
          markRetriedBodyStarted?.();
          return new Promise<never>(() => {});
        },
      });

    const { fetchAuthenticatedBlob, clearAuthTokenCache } = await import('../../src/lib/api/core');
    clearAuthTokenCache();
    const controller = new AbortController();
    const request = fetchAuthenticatedBlob('/uploads/denuncias/retry-stall.png', {
      signal: controller.signal,
    });

    await retriedBodyStarted;
    const calls = (global.fetch as ReturnType<typeof vi.fn>).mock.calls;
    expect(calls[1][1].signal).toBe(calls[0][1].signal);
    expect(calls[2][1].signal).toBe(calls[0][1].signal);
    controller.abort();

    await expect(request).rejects.toMatchObject({ name: 'AbortError' });
  });

  it('times out while a successful JSON response body is still pending', async () => {
    vi.useFakeTimers();
    mockGetAccessToken.mockResolvedValue(null);
    let markBodyStarted: (() => void) | undefined;
    const bodyStarted = new Promise<void>((resolve) => {
      markBodyStarted = resolve;
    });
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers(),
      json: () => {
        markBodyStarted?.();
        return new Promise<never>(() => {});
      },
    });

    const { apiFetch } = await import('../../src/lib/api/core');
    let rejection: unknown;
    void apiFetch('/slow-json', { timeout: 25 }).catch((error: unknown) => {
      rejection = error;
    });
    await bodyStarted;
    await vi.advanceTimersByTimeAsync(25);

    expect(rejection).toEqual(new Error('La solicitud excedió el tiempo límite (0.025s)'));
    vi.useRealTimers();
  });

  it('propagates caller cancellation while a successful JSON body is pending', async () => {
    mockGetAccessToken.mockResolvedValue(null);
    let markBodyStarted: (() => void) | undefined;
    const bodyStarted = new Promise<void>((resolve) => {
      markBodyStarted = resolve;
    });
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers(),
      json: () => {
        markBodyStarted?.();
        return new Promise<never>(() => {});
      },
    });

    const { apiFetch } = await import('../../src/lib/api/core');
    const controller = new AbortController();
    const request = apiFetch('/slow-json', { signal: controller.signal });
    await bodyStarted;
    controller.abort();

    await expect(request).rejects.toMatchObject({ name: 'AbortError' });
  });

  it('times out while a successful authenticated blob body is still pending', async () => {
    vi.useFakeTimers();
    mockGetAccessToken.mockResolvedValue('jwt-123');
    let markBodyStarted: (() => void) | undefined;
    const bodyStarted = new Promise<void>((resolve) => {
      markBodyStarted = resolve;
    });
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers(),
      blob: () => {
        markBodyStarted?.();
        return new Promise<never>(() => {});
      },
    });

    const { fetchAuthenticatedBlob } = await import('../../src/lib/api/core');
    let rejection: unknown;
    void fetchAuthenticatedBlob('/uploads/denuncias/slow.png', { timeout: 25 }).catch(
      (error: unknown) => {
        rejection = error;
      }
    );
    await bodyStarted;
    await vi.advanceTimersByTimeAsync(25);

    expect(rejection).toEqual(new Error('La solicitud excedió el tiempo límite (0.025s)'));
    vi.useRealTimers();
  });

  it('propagates unmount cancellation while an authenticated blob body is pending', async () => {
    mockGetAccessToken.mockResolvedValue('jwt-123');
    let markBodyStarted: (() => void) | undefined;
    const bodyStarted = new Promise<void>((resolve) => {
      markBodyStarted = resolve;
    });
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers(),
      blob: () => {
        markBodyStarted?.();
        return new Promise<never>(() => {});
      },
    });

    const { fetchAuthenticatedBlob } = await import('../../src/lib/api/core');
    const controller = new AbortController();
    const request = fetchAuthenticatedBlob('/uploads/denuncias/slow.png', {
      signal: controller.signal,
    });
    await bodyStarted;
    controller.abort();

    await expect(request).rejects.toMatchObject({ name: 'AbortError' });
  });

  it('supports FormData bodies without forcing JSON content-type', async () => {
    mockGetAccessToken.mockResolvedValue(null);
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      headers: new Headers(),
      json: async () => ({ uploaded: true }),
    });
    const { apiFetch } = await import('../../src/lib/api/core');

    const body = new FormData();
    body.append('file', new Blob(['x']), 'test.txt');
    await apiFetch('/padron/consorcistas/import', { method: 'POST', body });

    const options = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0][1];
    expect(options.headers['Content-Type']).toBeUndefined();
  });

  it('maps timeout and api error payloads', async () => {
    mockGetAccessToken.mockResolvedValue(null);
    const { apiFetch } = await import('../../src/lib/api/core');

    const abortError = new Error('aborted');
    abortError.name = 'AbortError';
    (global.fetch as ReturnType<typeof vi.fn>).mockRejectedValueOnce(abortError);
    await expect(apiFetch('/stats')).rejects.toThrow(/tiempo límite/i);

    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: false,
      headers: new Headers(),
      status: 400,
      json: async () => ({ detail: 'Payload invalido' }),
    });
    await expect(apiFetch('/stats')).rejects.toThrow('Payload invalido');
  });

  it('maps generic backend error envelopes to user-facing messages', async () => {
    mockGetAccessToken.mockResolvedValue(null);
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: false,
      headers: new Headers(),
      status: 500,
      json: async () => ({
        error: {
          code: 'INTERNAL_ERROR',
          message: 'Error interno del servidor',
          details: {},
        },
      }),
    });

    const { apiFetch } = await import('../../src/lib/api/core');

    await expect(apiFetch('/geo/dem-pipeline')).rejects.toThrow('Error interno del servidor');
  });

  // ----------------------------------------------------------------------- //
  // RES2-001 (SEG-2 4R): refresh failures must discriminate session-death
  // (401/403 from /auth/jwt/refresh) from transient failures (5xx, 429,
  // network). With 60-minute tokens every active user hits the refresh
  // endpoint ~8x/workday; a backend blip must NOT force-logout users.
  // ----------------------------------------------------------------------- //
  describe('refresh failure discrimination (RES2-001)', () => {
    /** Mirrors REFRESH_TRANSIENT_BACKOFF_MS in core.ts (anti-spam guard). */
    const REFRESH_BACKOFF_MS = 2000;

    let expiredListener: ReturnType<typeof vi.fn>;
    let nowSpy: ReturnType<typeof vi.spyOn> | undefined;

    beforeEach(() => {
      expiredListener = vi.fn();
      window.addEventListener('auth:expired', expiredListener);
    });

    afterEach(() => {
      window.removeEventListener('auth:expired', expiredListener);
      nowSpy?.mockRestore();
      nowSpy = undefined;
    });

    function respuesta(status: number, cuerpo: unknown = { detail: 'Expired' }) {
      return {
        ok: status >= 200 && status < 300,
        status,
        headers: new Headers(),
        json: async () => cuerpo,
      };
    }

    function refreshCalls() {
      return (global.fetch as ReturnType<typeof vi.fn>).mock.calls.filter(([url]) =>
        String(url).includes('/auth/jwt/refresh')
      );
    }

    async function capturar<T>(promesa: Promise<T>): Promise<unknown> {
      return promesa.then(
        () => null,
        (error: unknown) => error
      );
    }

    it('a 5xx refresh answer is transient: QueryError, session intact, refresh retried on the next request', async () => {
      const realNow = Date.now();
      let now = realNow;
      nowSpy = vi.spyOn(Date, 'now').mockImplementation(() => now);

      mockGetAccessToken
        .mockResolvedValueOnce('expired-token')
        .mockResolvedValue('recovered-token');
      (global.fetch as ReturnType<typeof vi.fn>)
        // Request 1: bearer expired.
        .mockResolvedValueOnce(respuesta(401))
        // Refresh 1: backend blip.
        .mockResolvedValueOnce(respuesta(503, { detail: 'unavailable' }))
        // Request 2 (immediate, inside the anti-spam window): still 401.
        .mockResolvedValueOnce(respuesta(401))
        // Request 3 (after the backoff window): 401, then the refresh recovers.
        .mockResolvedValueOnce(respuesta(401))
        .mockResolvedValueOnce(respuesta(200, { access_token: 'recovered-token' }))
        .mockResolvedValueOnce(respuesta(200, { ok: true }));

      const { apiFetch, clearAuthTokenCache } = await import('../../src/lib/api/core');
      clearAuthTokenCache();

      // (a) The triggering request fails with the transient QueryError...
      const first = await capturar(apiFetch('/reports'));
      expect(first).toMatchObject({ name: 'QueryError', statusCode: 503 });
      expect((first as Error).message).toMatch(/No se pudo renovar la sesión/);
      // ...but the session is NOT torn down.
      expect(mockClearTokens).not.toHaveBeenCalled();
      expect(mockReplaceAccessToken).not.toHaveBeenCalled();
      expect(expiredListener).not.toHaveBeenCalled();

      // Anti-spam guard: an immediate retry fails fast without re-hitting
      // the refresh endpoint (2 originals + 1 refresh = 3 fetches).
      const second = await capturar(apiFetch('/reports'));
      expect(second).toMatchObject({ name: 'QueryError' });
      expect(global.fetch).toHaveBeenCalledTimes(3);

      // After the 2s window the next request attempts the refresh again and
      // the session recovers transparently.
      now += REFRESH_BACKOFF_MS + 1;
      await expect(apiFetch('/reports')).resolves.toEqual({ ok: true });
      expect(refreshCalls()).toHaveLength(2);
      expect(expiredListener).not.toHaveBeenCalled();
      expect(mockClearTokens).not.toHaveBeenCalled();
    });

    it('a network failure during refresh is transient (no status), session intact', async () => {
      mockGetAccessToken.mockResolvedValue('expired-token');
      (global.fetch as ReturnType<typeof vi.fn>)
        .mockResolvedValueOnce(respuesta(401))
        .mockRejectedValueOnce(new TypeError('network down'));

      const { apiFetch, clearAuthTokenCache } = await import('../../src/lib/api/core');
      clearAuthTokenCache();

      const error = await capturar(apiFetch('/reports'));
      expect(error).toMatchObject({ name: 'QueryError' });
      expect((error as { statusCode?: number }).statusCode).toBeUndefined();
      expect((error as Error).message).toMatch(/No se pudo renovar la sesión/);
      expect(mockClearTokens).not.toHaveBeenCalled();
      expect(mockReplaceAccessToken).not.toHaveBeenCalled();
      expect(expiredListener).not.toHaveBeenCalled();
    });

    it('two concurrent 401s share one transient-failed refresh: both get the QueryError, session intact', async () => {
      mockGetAccessToken.mockResolvedValue('expired-token');
      let resolveRefresh: ((response: Response) => void) | undefined;
      let markRefreshStarted: (() => void) | undefined;
      const refreshStarted = new Promise<void>((resolve) => {
        markRefreshStarted = resolve;
      });
      (global.fetch as ReturnType<typeof vi.fn>).mockImplementation(
        (url: string | URL | Request) =>
          String(url).includes('/auth/jwt/refresh')
            ? new Promise<Response>((resolve) => {
                resolveRefresh = resolve;
                markRefreshStarted?.();
              })
            : Promise.resolve(respuesta(401))
      );

      const { apiFetch, clearAuthTokenCache } = await import('../../src/lib/api/core');
      clearAuthTokenCache();

      const first = apiFetch('/a');
      const second = apiFetch('/b');
      await refreshStarted;
      // Let the second request's 401 handler join the in-flight refresh
      // before it settles (its remaining path is resolved microtasks).
      await new Promise((resolve) => setTimeout(resolve, 0));
      await new Promise((resolve) => setTimeout(resolve, 0));
      resolveRefresh?.(new Response(null, { status: 503 }));

      const errors = await Promise.all([first, second].map((p) => capturar(p)));
      for (const error of errors) {
        expect(error).toMatchObject({ name: 'QueryError', statusCode: 503 });
        expect((error as Error).message).toMatch(/No se pudo renovar la sesión/);
      }
      // Single-flight held: exactly ONE refresh call for both 401s.
      expect(refreshCalls()).toHaveLength(1);
      expect(mockClearTokens).not.toHaveBeenCalled();
      expect(expiredListener).not.toHaveBeenCalled();
    });

    it('a 401 from the refresh endpoint keeps the exact logout semantics', async () => {
      mockGetAccessToken.mockResolvedValue('expired-token');
      (global.fetch as ReturnType<typeof vi.fn>)
        .mockResolvedValueOnce(respuesta(401))
        .mockResolvedValueOnce(respuesta(401, { detail: 'Refresh token revoked' }));

      const { apiFetch, clearAuthTokenCache } = await import('../../src/lib/api/core');
      clearAuthTokenCache();

      await expect(apiFetch('/reports')).rejects.toThrow(
        'Tu sesión ha expirado. Por favor iniciá sesión nuevamente.'
      );
      expect(mockClearTokens).toHaveBeenCalledOnce();
      expect(expiredListener).toHaveBeenCalledOnce();
      expect(mockReplaceAccessToken).not.toHaveBeenCalled();
      // No retry of the original request: original + refresh only.
      expect(global.fetch).toHaveBeenCalledTimes(2);
    });

    it('a 429 from the refresh endpoint is transient (rate limiter), not session-death', async () => {
      mockGetAccessToken.mockResolvedValue('expired-token');
      (global.fetch as ReturnType<typeof vi.fn>)
        .mockResolvedValueOnce(respuesta(401))
        .mockResolvedValueOnce(respuesta(429, { detail: 'Too many requests' }));

      const { apiFetch, clearAuthTokenCache } = await import('../../src/lib/api/core');
      clearAuthTokenCache();

      const error = await capturar(apiFetch('/reports'));
      expect(error).toMatchObject({ name: 'QueryError', statusCode: 429 });
      expect((error as Error).message).toMatch(/No se pudo renovar la sesión/);
      expect(mockClearTokens).not.toHaveBeenCalled();
      expect(expiredListener).not.toHaveBeenCalled();
    });
  });
});
