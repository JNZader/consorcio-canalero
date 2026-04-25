import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockGetAccessToken = vi.fn();

vi.mock('../../src/lib/auth/index', () => ({
  authAdapter: {
    getAccessToken: mockGetAccessToken,
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

  it('supports FormData bodies without forcing JSON content-type', async () => {
    mockGetAccessToken.mockResolvedValue(null);
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
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
      status: 400,
      json: async () => ({ detail: 'Payload invalido' }),
    });
    await expect(apiFetch('/stats')).rejects.toThrow('Payload invalido');
  });

  it('maps generic backend error envelopes to user-facing messages', async () => {
    mockGetAccessToken.mockResolvedValue(null);
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: false,
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
