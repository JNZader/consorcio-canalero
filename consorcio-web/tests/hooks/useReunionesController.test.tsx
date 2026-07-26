import { notifications } from '@mantine/notifications';
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { apiFetchMock, getAuthTokenMock, loggerMock } = vi.hoisted(() => ({
  apiFetchMock: vi.fn(),
  getAuthTokenMock: vi.fn().mockResolvedValue('token'),
  loggerMock: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
}));

vi.mock('../../src/lib/api', () => ({
  API_URL: 'http://localhost:8000',
  apiFetch: apiFetchMock,
  getAuthToken: getAuthTokenMock,
}));

vi.mock('../../src/lib/logger', () => ({ logger: loggerMock }));

vi.mock('@mantine/notifications', () => ({ notifications: { show: vi.fn() } }));

import { useReunionesController } from '../../src/components/admin/management/reuniones/useReunionesController';

const reunion = {
  id: 'r1',
  titulo: 'Asamblea de marzo',
  fecha_reunion: '2026-03-10T18:00:00Z',
  lugar: 'Sede',
  descripcion: '',
  orden_del_dia_items: ['Punto 1'],
  estado: 'programada',
};

const agendaItem = {
  id: 'a1',
  titulo: 'Limpieza canal norte',
  descripcion: 'Estado de avance',
  referencias: [],
};

type Handlers = Partial<Record<string, (url: string, options?: RequestInit) => unknown>>;

/** Persistent router over apiFetch — never mockImplementationOnce (repo gotcha (a)). */
function stubApi(handlers: Handlers = {}) {
  apiFetchMock.mockImplementation(async (url: string, options?: RequestInit) => {
    for (const [key, handler] of Object.entries(handlers)) {
      const [method, path] = key.split(' ');
      if ((options?.method ?? 'GET') === method && url === path) return handler?.(url, options);
    }
    if (url === '/reuniones' && !options) return { items: [reunion], total: 1 };
    if (url.startsWith('/reuniones/') && url.endsWith('/agenda') && !options) return [agendaItem];
    if (url.startsWith('/denuncias')) {
      return { items: [{ id: 'd1', tipo: 'canal_obstruido', ubicacion_texto: 'Lote 5' }] };
    }
    if (url === '/tramites') return [{ id: 't1', titulo: 'Permiso', numero_expediente: 'EXP-1' }];
    return {};
  });
}

async function mountController() {
  const rendered = renderHook(() => useReunionesController());
  await waitFor(() => expect(rendered.result.current.loading).toBe(false));
  await waitFor(() => expect(rendered.result.current.loadingEntities).toBe(false));
  return rendered;
}

const postedBody = (path: string) => {
  const call = apiFetchMock.mock.calls.find(
    ([url, options]) => url === path && options?.method === 'POST'
  );
  return call ? JSON.parse(call[1].body) : null;
};

beforeEach(() => {
  vi.clearAllMocks();
  stubApi();
  window.confirm = vi.fn().mockReturnValue(true);
  window.URL.createObjectURL = vi.fn().mockReturnValue('blob:pdf');
  window.URL.revokeObjectURL = vi.fn();
  vi.mocked(global.fetch).mockResolvedValue({
    ok: true,
    blob: async () => new Blob(['pdf']),
  } as unknown as Response);
});

describe('useReunionesController — initial load', () => {
  it('loads meetings and referrable entities on mount', async () => {
    const { result } = await mountController();

    expect(result.current.reuniones).toEqual([reunion]);
    expect(result.current.availableEntities).toEqual([
      {
        value: 'd1',
        label: 'canal obstruido - Lote 5',
        group: 'Reportes',
        type: 'reporte',
      },
      { value: 't1', label: 'Permiso (EXP-1)', group: 'Tramites', type: 'tramite' },
    ]);
  });

  it('degrades to an empty list when /reuniones fails', async () => {
    stubApi({ 'GET /reuniones': () => Promise.reject(new Error('500')) });

    const { result } = await mountController();

    expect(result.current.reuniones).toEqual([]);
    expect(result.current.loading).toBe(false);
  });

  it('logs and keeps entities empty when the referrables requests fail', async () => {
    stubApi({ 'GET /tramites': () => Promise.reject(new Error('500')) });

    const { result } = await mountController();

    expect(result.current.availableEntities).toEqual([]);
    expect(loggerMock.error).toHaveBeenCalledWith('Error fetching referrables:', expect.anything());
    expect(result.current.loadingEntities).toBe(false);
  });
});

describe('useReunionesController — agenda', () => {
  it('handleViewAgenda selects the meeting, opens the modal and loads its agenda', async () => {
    const { result } = await mountController();

    await act(async () => {
      result.current.handleViewAgenda(reunion);
    });

    expect(result.current.selectedReunion).toEqual(reunion);
    expect(result.current.agendaOpened).toBe(true);
    await waitFor(() => expect(result.current.agenda).toEqual([agendaItem]));
  });

  it('accepts a wrapped { items } agenda payload and degrades to [] on failure', async () => {
    stubApi({ 'GET /reuniones/r1/agenda': () => ({ items: [agendaItem] }) });
    const { result } = await mountController();

    await act(async () => {
      result.current.handleViewAgenda(reunion);
    });
    await waitFor(() => expect(result.current.agenda).toEqual([agendaItem]));

    stubApi({ 'GET /reuniones/r1/agenda': () => Promise.reject(new Error('down')) });
    await act(async () => {
      result.current.handleViewAgenda(reunion);
    });
    await waitFor(() => expect(result.current.agenda).toEqual([]));
  });

  it('handleAddTopic posts the next order plus resolved references and reloads the agenda', async () => {
    const { result } = await mountController();
    await act(async () => {
      result.current.handleViewAgenda(reunion);
    });
    await waitFor(() => expect(result.current.agenda).toHaveLength(1));

    await act(async () => {
      await result.current.handleAddTopic({
        titulo: 'Nuevo tema',
        descripcion: 'detalle',
        referencias: ['t1'],
      });
    });

    expect(postedBody('/reuniones/r1/agenda')).toEqual({
      titulo: 'Nuevo tema',
      descripcion: 'detalle',
      orden: 2,
      referencias: [
        { entidad_id: 't1', entidad_tipo: 'tramite', metadata: { label: 'Permiso (EXP-1)' } },
      ],
    });
    expect(result.current.itemForm.values.titulo).toBe('');
  });

  it('handleAddTopic is a no-op without a selected meeting', async () => {
    const { result } = await mountController();
    apiFetchMock.mockClear();

    await act(async () => {
      await result.current.handleAddTopic({ titulo: 'x', descripcion: '', referencias: [] });
    });

    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it('logs when adding a topic fails', async () => {
    const { result } = await mountController();
    await act(async () => {
      result.current.handleViewAgenda(reunion);
    });
    await waitFor(() => expect(result.current.agenda).toHaveLength(1));
    stubApi({ 'POST /reuniones/r1/agenda': () => Promise.reject(new Error('nope')) });

    await act(async () => {
      await result.current.handleAddTopic({ titulo: 'x', descripcion: '', referencias: [] });
    });

    expect(loggerMock.error).toHaveBeenCalledWith('Error adding agenda topic:', expect.anything());
  });
});

describe('useReunionesController — delete agenda topic', () => {
  async function mountWithAgenda() {
    const rendered = await mountController();
    await act(async () => {
      rendered.result.current.handleViewAgenda(reunion);
    });
    await waitFor(() => expect(rendered.result.current.agenda).toHaveLength(1));
    return rendered;
  }

  it('does nothing when the user cancels the confirmation', async () => {
    const { result } = await mountWithAgenda();
    window.confirm = vi.fn().mockReturnValue(false);
    apiFetchMock.mockClear();

    await act(async () => {
      await result.current.handleDeleteTopic(agendaItem);
    });

    expect(apiFetchMock).not.toHaveBeenCalled();
    expect(result.current.deletingAgendaItemId).toBeNull();
  });

  it('deletes, reloads and notifies on success', async () => {
    const { result } = await mountWithAgenda();

    await act(async () => {
      await result.current.handleDeleteTopic(agendaItem);
    });

    expect(apiFetchMock).toHaveBeenCalledWith('/reuniones/r1/agenda/a1', { method: 'DELETE' });
    expect(notifications.show).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Tema eliminado', color: 'green' })
    );
    expect(result.current.deletingAgendaItemId).toBeNull();
  });

  it('notifies in red and releases the spinner when the delete fails', async () => {
    const { result } = await mountWithAgenda();
    stubApi({ 'DELETE /reuniones/r1/agenda/a1': () => Promise.reject(new Error('409')) });

    await act(async () => {
      await result.current.handleDeleteTopic(agendaItem);
    });

    expect(notifications.show).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'No se pudo eliminar el tema', color: 'red' })
    );
    expect(loggerMock.error).toHaveBeenCalledWith(
      'Error deleting agenda topic:',
      expect.anything()
    );
    expect(result.current.deletingAgendaItemId).toBeNull();
  });
});

describe('useReunionesController — create meeting', () => {
  it('handleAddChecklistPoint trims, ignores blanks and clears the input', async () => {
    const { result } = await mountController();

    act(() => result.current.setNewChecklistPoint('   '));
    act(() => result.current.handleAddChecklistPoint());
    expect(result.current.reunionForm.values.orden_del_dia_items).toEqual(['']);
    expect(result.current.newChecklistPoint).toBe('   ');

    act(() => result.current.setNewChecklistPoint('  Revisar presupuesto  '));
    act(() => result.current.handleAddChecklistPoint());

    expect(result.current.reunionForm.values.orden_del_dia_items).toEqual([
      '',
      'Revisar presupuesto',
    ]);
    expect(result.current.newChecklistPoint).toBe('');
  });

  it('posts trimmed agenda points with an ISO date, resets the form and reloads', async () => {
    const { result } = await mountController();
    act(() => result.current.createModal.open());
    apiFetchMock.mockClear();

    await act(async () => {
      await result.current.handleCreateReunion({
        titulo: 'Asamblea',
        fecha_reunion: '2026-04-01T10:00',
        lugar: 'Sede',
        descripcion: 'd',
        orden_del_dia_items: ['  Punto A  ', '   ', 'Punto B'],
        tipo: 'ordinaria',
      });
    });

    const body = postedBody('/reuniones');
    expect(body.orden_del_dia_items).toEqual(['Punto A', 'Punto B']);
    expect(body.fecha_reunion).toBe(new Date('2026-04-01T10:00').toISOString());
    expect(notifications.show).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Reunion creada', color: 'green' })
    );
    expect(result.current.createOpened).toBe(false);
    expect(result.current.reunionForm.values.titulo).toBe('');
    // Reloaded the list after creating.
    expect(apiFetchMock).toHaveBeenCalledWith('/reuniones');
  });

  it('keeps the modal open and notifies in red when creation fails', async () => {
    const { result } = await mountController();
    act(() => result.current.createModal.open());
    stubApi({ 'POST /reuniones': () => Promise.reject(new Error('422')) });

    await act(async () => {
      await result.current.handleCreateReunion({
        titulo: 'Asamblea',
        fecha_reunion: '2026-04-01T10:00',
        lugar: 'Sede',
        descripcion: '',
        orden_del_dia_items: ['Punto A'],
        tipo: 'ordinaria',
      });
    });

    expect(notifications.show).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'No se pudo crear la reunion', color: 'red' })
    );
    expect(result.current.createOpened).toBe(true);
  });
});

describe('useReunionesController — PDF export', () => {
  it('is a no-op without a selected meeting', async () => {
    const { result } = await mountController();

    await act(async () => {
      await result.current.handleExportPDF();
    });

    expect(global.fetch).not.toHaveBeenCalled();
    expect(result.current.exporting).toBe(false);
  });

  it('downloads the agenda PDF with an authorization header and a safe filename', async () => {
    const clickSpy = vi.fn();
    const originalCreate = document.createElement.bind(document);
    vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      const element = originalCreate(tag) as HTMLAnchorElement;
      if (tag === 'a') element.click = clickSpy;
      return element;
    });

    const { result } = await mountController();
    await act(async () => {
      result.current.handleViewAgenda(reunion);
    });

    await act(async () => {
      await result.current.handleExportPDF();
    });

    expect(global.fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/v2/reuniones/r1/export-pdf',
      { headers: { Authorization: 'Bearer token' } }
    );
    expect(clickSpy).toHaveBeenCalled();
    expect(result.current.exporting).toBe(false);
    vi.mocked(document.createElement).mockRestore();
  });

  it('logs and releases the exporting flag when the server rejects the export', async () => {
    vi.mocked(global.fetch).mockResolvedValue({ ok: false, status: 500 } as unknown as Response);
    const { result } = await mountController();
    await act(async () => {
      result.current.handleViewAgenda(reunion);
    });

    await act(async () => {
      await result.current.handleExportPDF();
    });

    expect(loggerMock.error).toHaveBeenCalledWith('Export error:', expect.anything());
    expect(result.current.exporting).toBe(false);
  });
});
