import { beforeEach, describe, expect, it, vi } from 'vitest';

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
    await expect(apiFetch('/stats')).rejects.toThrow(/tiempo limite/i);

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
});
