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

  it('sends authenticated suggestion through /sugerencias', async () => {
    // Mirror del flujo de denuncias: el create de sugerencias exige
    // login (anti-spam + ownership). El backend autollena
    // `usuario_id` y `contacto_email` desde el JWT, así que el cliente
    // ya no necesita mandar `contacto_verificado`/`skipAuth`.
    await sugerenciasApi.create({
      titulo: 'Canal obstruido',
      descripcion: 'Hay maleza en la compuerta principal',
    });

    expect(apiFetch).toHaveBeenCalledWith(
      '/sugerencias',
      expect.objectContaining({
        method: 'POST',
      })
    );
    // No `skipAuth` y no `/public/sugerencias` — esos vectores se
    // retiraron junto con el flujo anónimo.
    const [, options] = vi.mocked(apiFetch).mock.calls[0];
    expect(options).not.toHaveProperty('skipAuth');
  });

  it('checkLimit hits the real backend endpoint', async () => {
    // Antes era un stub que devolvía `{remaining: 3}` hardcodeado y no
    // hacía request. Ahora el backend cuenta sobre la base
    // (`GET /sugerencias/rate-limit`).
    await sugerenciasApi.checkLimit();

    expect(apiFetch).toHaveBeenCalledWith('/sugerencias/rate-limit');
  });

  it('builds admin list query with provided filters only', async () => {
    await sugerenciasApi.getAll({ page: 2, estado: 'pendiente', prioridad: 'alta' });

    expect(apiFetch).toHaveBeenCalledWith('/sugerencias?page=2&estado=pendiente&prioridad=alta');
  });

  it('calls detail and mutation endpoints with expected payloads', async () => {
    await sugerenciasApi.get('sug-1');
    await sugerenciasApi.update('sug-1', { estado: 'revisada' });
    await sugerenciasApi.agendar('sug-1', '2026-03-20');

    expect(apiFetch).toHaveBeenNthCalledWith(1, '/sugerencias/sug-1');
    expect(apiFetch).toHaveBeenNthCalledWith(
      2,
      '/sugerencias/sug-1',
      expect.objectContaining({ method: 'PATCH' })
    );
    expect(apiFetch).toHaveBeenNthCalledWith(
      3,
      '/sugerencias/sug-1/agendar',
      expect.objectContaining({ method: 'POST' })
    );
    expect(apiFetch).not.toHaveBeenCalledWith(
      '/sugerencias/sug-1',
      expect.objectContaining({ method: 'DELETE' })
    );
  });

  it('calls stats and meeting endpoints', async () => {
    await sugerenciasApi.getStats();
    await sugerenciasApi.getProximaReunion();

    expect(apiFetch).toHaveBeenNthCalledWith(1, '/sugerencias/stats');
    expect(apiFetch).toHaveBeenNthCalledWith(2, '/sugerencias/proxima-reunion');
    expect(apiFetch).not.toHaveBeenCalledWith(
      '/sugerencias/interna',
      expect.anything()
    );
  });

  it('does not expose unbacked interna create or delete clients', () => {
    expect(sugerenciasApi).not.toHaveProperty('createInternal');
    expect(sugerenciasApi).not.toHaveProperty('delete');
  });

  it('listMine paginates citizen-owned sugerencias', async () => {
    await sugerenciasApi.listMine(2, 5);

    expect(apiFetch).toHaveBeenCalledWith('/sugerencias/mine?page=2&limit=5');
  });
});
