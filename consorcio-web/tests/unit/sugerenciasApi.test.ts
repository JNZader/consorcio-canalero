import { beforeEach, describe, expect, it, vi } from 'vitest';

import { sugerenciasApi } from '../../src/lib/api/sugerencias';
import { apiFetch } from '../../src/lib/api/core';

vi.mock('../../src/lib/api/core', () => ({
  apiFetch: vi.fn(),
}));

describe('sugerenciasApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(apiFetch).mockResolvedValue({} as unknown as never);
  });

  it('sends public suggestion with skipAuth enabled', async () => {
    await sugerenciasApi.createPublic({
      titulo: 'Canal obstruido',
      descripcion: 'Hay maleza en la compuerta principal',
      contacto_verificado: true,
      contacto_email: 'vecino@example.com',
    });

    expect(apiFetch).toHaveBeenCalledWith(
      '/public/sugerencias',
      expect.objectContaining({
        method: 'POST',
        skipAuth: true,
      })
    );
  });

  // checkLimit is a documented no-op stub in production
  // (see TODO: v2 rate limit endpoint pending). When the endpoint is built,
  // these tests should revert to the legacy network-call style.
  it('checkLimit returns stub RateLimitInfo when contact params are provided', async () => {
    const result = await sugerenciasApi.checkLimit('vecino@example.com', '3534000000');

    expect(result).toEqual({ remaining: 3, limit: 3, reset_hours: 24 });
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it('checkLimit returns stub RateLimitInfo when contact is missing', async () => {
    const result = await sugerenciasApi.checkLimit();

    expect(result).toEqual({ remaining: 3, limit: 3, reset_hours: 24 });
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it('builds admin list query with provided filters only', async () => {
    await sugerenciasApi.getAll({ page: 2, estado: 'pendiente', prioridad: 'alta' });

    expect(apiFetch).toHaveBeenCalledWith('/sugerencias?page=2&estado=pendiente&prioridad=alta');
  });

  it('calls detail and mutation endpoints with expected payloads', async () => {
    await sugerenciasApi.get('sug-1');
    await sugerenciasApi.getHistorial('sug-1');
    await sugerenciasApi.update('sug-1', { estado: 'en_agenda' });
    await sugerenciasApi.agendar('sug-1', '2026-03-20');
    await sugerenciasApi.resolver('sug-1', 'Tema tratado en comision');
    await sugerenciasApi.delete('sug-1');

    expect(apiFetch).toHaveBeenNthCalledWith(1, '/sugerencias/sug-1');
    expect(apiFetch).toHaveBeenNthCalledWith(2, '/sugerencias/sug-1/historial');
    expect(apiFetch).toHaveBeenNthCalledWith(
      3,
      '/sugerencias/sug-1',
      expect.objectContaining({ method: 'PATCH' })
    );
    expect(apiFetch).toHaveBeenNthCalledWith(
      4,
      '/sugerencias/sug-1/agendar',
      expect.objectContaining({ method: 'POST' })
    );
    expect(apiFetch).toHaveBeenNthCalledWith(
      5,
      '/sugerencias/sug-1/resolver',
      expect.objectContaining({ method: 'POST' })
    );
    expect(apiFetch).toHaveBeenNthCalledWith(6, '/sugerencias/sug-1', { method: 'DELETE' });
  });

  it('calls stats and meeting endpoints', async () => {
    await sugerenciasApi.getStats();
    await sugerenciasApi.getProximaReunion();
    await sugerenciasApi.createInternal({
      titulo: 'Tema interno',
      descripcion: 'Propuesta para proxima reunion',
      prioridad: 'alta',
    });

    expect(apiFetch).toHaveBeenNthCalledWith(1, '/sugerencias/stats');
    expect(apiFetch).toHaveBeenNthCalledWith(2, '/sugerencias/proxima-reunion');
    expect(apiFetch).toHaveBeenNthCalledWith(
      3,
      '/sugerencias/interna',
      expect.objectContaining({ method: 'POST' })
    );
  });
});
