import { beforeEach, describe, expect, it, vi } from 'vitest';

import { publicApi, reportsApi, statsApi } from '../../src/lib/api/reports';
import { apiFetch, getAuthToken } from '../../src/lib/api/core';

vi.mock('../../src/lib/api/core', () => ({
  apiFetch: vi.fn(),
  getAuthToken: vi.fn(),
  API_URL: 'https://api.example.com',
  API_PREFIX: '/api/v2',
  LONG_TIMEOUT: 1000,
}));

describe('reportsApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(apiFetch).mockResolvedValue({} as never);
    vi.mocked(getAuthToken).mockResolvedValue('jwt-token');
    global.fetch = vi.fn();
  });

  it('builds query params for both getAll overloads', async () => {
    await reportsApi.getAll(2, 15, 'pendiente');
    await reportsApi.getAll({ page: 3, cuenca: 'norte', assigned_to: 'op-1' });

    expect(apiFetch).toHaveBeenNthCalledWith(1, '/denuncias?page=2&limit=15&status=pendiente');
    expect(apiFetch).toHaveBeenNthCalledWith(2, '/denuncias?page=3&cuenca=norte&assigned_to=op-1');
  });

  it('calls update, assign and resolve endpoints with expected payloads', async () => {
    await reportsApi.updateStatus('rep-1', 'en_revision', 'revisar en campo');
    await reportsApi.update('rep-1', { prioridad: 'alta' });
    await reportsApi.assign('rep-1', 'oper-1', 'asignado');
    await reportsApi.resolve('rep-1', { status: 'resolved' });

    expect(apiFetch).toHaveBeenNthCalledWith(
      1,
      '/denuncias/rep-1',
      expect.objectContaining({ method: 'PATCH' })
    );
    expect(apiFetch).toHaveBeenNthCalledWith(
      2,
      '/denuncias/rep-1',
      expect.objectContaining({ method: 'PATCH' })
    );
    expect(apiFetch).toHaveBeenNthCalledWith(
      3,
      '/denuncias/rep-1',
      expect.objectContaining({ method: 'PATCH' })
    );
    expect(apiFetch).toHaveBeenNthCalledWith(
      4,
      '/denuncias/rep-1',
      expect.objectContaining({ method: 'PATCH' })
    );
  });

  it('calls get, getStats and public create endpoints', async () => {
    await reportsApi.get('rep-1');
    await reportsApi.getStats();
    await publicApi.createReport({
      tipo: 'desborde',
      descripcion: 'Detalle del incidente',
      latitud: -32.1,
      longitud: -62.4,
      contacto_email: 'vecino@example.com',
      contacto_verificado: true,
    });

    expect(apiFetch).toHaveBeenNthCalledWith(1, '/denuncias/rep-1');
    expect(apiFetch).toHaveBeenNthCalledWith(2, '/denuncias/stats');
    expect(apiFetch).toHaveBeenNthCalledWith(
      3,
      '/public/denuncias',
      expect.objectContaining({ method: 'POST', skipAuth: true })
    );
  });

  it('uploads public photo and returns parsed payload', async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => ({ photo_url: 'https://cdn/photo.jpg', filename: 'photo.jpg' }),
    });

    const result = await publicApi.uploadPhoto(new File(['img'], 'photo.jpg', { type: 'image/jpeg' }));

    expect(result.photo_url).toContain('photo.jpg');
  });

  it('maps upload timeout to user-friendly message', async () => {
    const abortError = new Error('aborted');
    abortError.name = 'AbortError';
    (global.fetch as ReturnType<typeof vi.fn>).mockRejectedValue(abortError);

    await expect(
      publicApi.uploadPhoto(new File(['img'], 'photo.jpg', { type: 'image/jpeg' }))
    ).rejects.toThrow(/tiempo limite/i);
  });

  it('maps upload non-ok responses to API message', async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: false,
      json: async () => ({ detail: 'archivo invalido' }),
    });

    await expect(
      publicApi.uploadPhoto(new File(['img'], 'photo.jpg', { type: 'image/jpeg' }))
    ).rejects.toThrow(/archivo invalido/i);
  });

  it('exports stats as blob using auth token and format headers', async () => {
    const blob = new Blob(['csv']);
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      blob: async () => blob,
    });

    const result = await statsApi.export({ format: 'csv' });

    expect(result).toBe(blob);
    expect(global.fetch).toHaveBeenCalledWith(
      'https://api.example.com/api/v2/monitoring/dashboard',
      expect.objectContaining({
        method: 'GET',
        headers: expect.objectContaining({ Authorization: 'Bearer jwt-token', Accept: 'text/csv' }),
      })
    );
  });

  it('calls dashboard and summary stats endpoints', async () => {
    await statsApi.getDashboard('7d');
    await statsApi.getByCuenca('analysis-1');
    await statsApi.getHistorical({ cuenca: 'norte', limit: 5 });
    await statsApi.getSummary();

    expect(apiFetch).toHaveBeenNthCalledWith(1, '/monitoring/dashboard?period=7d');
    expect(apiFetch).toHaveBeenNthCalledWith(2, '/monitoring/dashboard?analysis_id=analysis-1');
    expect(apiFetch).toHaveBeenNthCalledWith(3, '/monitoring/analyses?cuenca=norte&limit=5');
    expect(apiFetch).toHaveBeenNthCalledWith(4, '/monitoring/dashboard');
  });

  it('exports with pdf accept header by default', async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      blob: async () => new Blob(['pdf']),
    });

    await statsApi.export({ format: 'pdf' });

    expect(global.fetch).toHaveBeenCalledWith(
      'https://api.example.com/api/v2/monitoring/dashboard',
      expect.objectContaining({
        headers: expect.objectContaining({ Accept: 'application/pdf' }),
      })
    );
  });
});
