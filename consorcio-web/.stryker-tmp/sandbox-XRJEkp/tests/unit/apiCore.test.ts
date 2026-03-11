// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from 'vitest';

const getSessionMock = vi.fn();

vi.mock('../../src/lib/supabase', () => ({
  getSupabaseClient: () => ({
    auth: {
      getSession: getSessionMock,
    },
  }),
}));

describe('api core', () => {
  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
    global.fetch = vi.fn();
  });

  it('caches auth token and sends Authorization header', async () => {
    getSessionMock.mockResolvedValue({
      data: {
        session: {
          access_token: 'jwt-123',
          expires_at: Math.floor(Date.now() / 1000) + 3600,
        },
      },
    });
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true }),
    });

    const { apiFetch } = await import('../../src/lib/api/core');

    await apiFetch('/reports');
    await apiFetch('/reports');

    expect(getSessionMock).toHaveBeenCalledTimes(1);
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/reports'),
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer jwt-123' }),
      })
    );
  });

  it('supports FormData bodies without forcing JSON content-type', async () => {
    getSessionMock.mockResolvedValue({ data: { session: null } });
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
    getSessionMock.mockResolvedValue({ data: { session: null } });
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
});
