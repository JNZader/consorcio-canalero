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

import { useFinanzasController } from '../../src/components/admin/management/finanzas/useFinanzasController';

const gasto = {
  id: 'g1',
  fecha: '2026-03-02',
  descripcion: 'Mantenimiento retroexcavadora',
  monto: 12000,
  categoria: 'mantenimiento',
  proveedor: 'Taller Norte',
  created_at: '2026-03-02T10:00:00Z',
};

const ingreso = {
  id: 'i1',
  fecha: '2026-03-03',
  descripcion: 'Cuota marzo',
  monto: 20000,
  categoria: 'cuotas',
  consorcista_id: null,
  created_at: '2026-03-03T10:00:00Z',
};

const balance = { total_ingresos: 50000, total_gastos: 20000, balance: 30000 };
const currentYear = new Date().getFullYear();

type Handlers = Partial<Record<string, (url: string, options?: RequestInit) => unknown>>;

/** Persistent router over apiFetch — never mockImplementationOnce (repo gotcha (a)). */
function stubApi(handlers: Handlers = {}) {
  apiFetchMock.mockImplementation(async (url: string, options?: RequestInit) => {
    for (const [key, handler] of Object.entries(handlers)) {
      const [method, path] = key.split(' ');
      if ((options?.method ?? 'GET') === method && url === path) return handler?.(url, options);
    }
    if (url === '/finanzas/gastos' && !options?.method) return [gasto];
    if (url === '/finanzas/ingresos' && !options?.method) return { items: [ingreso] };
    if (url.startsWith('/finanzas/resumen/')) return balance;
    return {};
  });
}

async function mountController() {
  const rendered = renderHook(() => useFinanzasController());
  await waitFor(() => expect(rendered.result.current.loading).toBe(false));
  return rendered;
}

const bodyOf = (path: string, method: string) => {
  const call = apiFetchMock.mock.calls.find(
    ([url, options]) => url === path && options?.method === method
  );
  return call ? JSON.parse(call[1].body) : null;
};

const pdfResponse = (overrides: Record<string, unknown> = {}) =>
  ({
    ok: true,
    status: 200,
    headers: { get: () => 'application/pdf' },
    blob: async () => new Blob(['pdf']),
    ...overrides,
  }) as unknown as Response;

beforeEach(() => {
  vi.clearAllMocks();
  stubApi();
  window.URL.createObjectURL = vi.fn().mockReturnValue('blob:pdf');
  window.URL.revokeObjectURL = vi.fn();
  vi.mocked(global.fetch).mockResolvedValue(pdfResponse());
});

describe('useFinanzasController — initial load', () => {
  it('loads gastos, ingresos and balance, normalizing both payload shapes', async () => {
    const { result } = await mountController();

    expect(result.current.gastos).toEqual([gasto]);
    expect(result.current.ingresos).toEqual([ingreso]);
    expect(result.current.balance).toEqual(balance);
    expect(apiFetchMock).toHaveBeenCalledWith(`/finanzas/resumen/${currentYear}`);
    expect(result.current.activeTab).toBe('balance');
    expect(result.current.categoryData.map((option) => option.value)).toEqual([
      'obras',
      'mantenimiento',
      'personal',
      'administrativo',
      'otros',
    ]);
    expect(result.current.ingresoCategoryData.map((option) => option.value)).toEqual([
      'cuotas',
      'subsidio',
      'otros',
    ]);
  });

  it('logs and leaves an empty state when the load fails', async () => {
    stubApi({ 'GET /finanzas/gastos': () => Promise.reject(new Error('500')) });

    const { result } = await mountController();

    expect(result.current.gastos).toEqual([]);
    expect(result.current.ingresos).toEqual([]);
    expect(result.current.balance).toBeNull();
    expect(loggerMock.error).toHaveBeenCalledWith('Error fetching finanzas:', expect.anything());
  });
});

describe('useFinanzasController — gastos', () => {
  it('creates a gasto, closes the modal, resets the form, reloads and notifies', async () => {
    const { result } = await mountController();
    act(() => result.current.gastoModal.open());
    act(() => result.current.form.setFieldValue('descripcion', 'Cambio de bomba'));
    apiFetchMock.mockClear();

    await act(async () => {
      await result.current.handleCreateGasto({
        descripcion: 'Cambio de bomba',
        monto: 5000,
        categoria: 'obras',
        fecha: '2026-03-05',
      });
    });

    expect(bodyOf('/finanzas/gastos', 'POST')).toEqual({
      descripcion: 'Cambio de bomba',
      monto: 5000,
      categoria: 'obras',
      fecha: '2026-03-05',
    });
    expect(result.current.gastoOpened).toBe(false);
    expect(result.current.form.values.descripcion).toBe('');
    expect(apiFetchMock).toHaveBeenCalledWith('/finanzas/gastos');
    expect(notifications.show).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Gasto registrado', color: 'green' })
    );
  });

  it('keeps the modal open and does not notify success when creating a gasto fails', async () => {
    const { result } = await mountController();
    act(() => result.current.gastoModal.open());
    stubApi({ 'POST /finanzas/gastos': () => Promise.reject(new Error('422')) });

    await act(async () => {
      await result.current.handleCreateGasto({
        descripcion: 'Cambio de bomba',
        monto: 5000,
        categoria: 'obras',
        fecha: '2026-03-05',
      });
    });

    expect(result.current.gastoOpened).toBe(true);
    expect(notifications.show).not.toHaveBeenCalled();
    expect(loggerMock.error).toHaveBeenCalledWith('Error creating gasto:', expect.anything());
  });

  it('handleOpenEditCategory preloads the category and opens the edit modal', async () => {
    const { result } = await mountController();

    act(() => result.current.handleOpenEditCategory(gasto));

    expect(result.current.editGastoOpened).toBe(true);
    expect(result.current.editCategoryForm.values.categoria).toBe('mantenimiento');
  });

  it('patches the category of the gasto under edit and clears it afterwards', async () => {
    const { result } = await mountController();
    act(() => result.current.handleOpenEditCategory(gasto));

    await act(async () => {
      await result.current.handleUpdateCategory({ categoria: 'obras' });
    });

    expect(bodyOf('/finanzas/gastos/g1', 'PATCH')).toEqual({ categoria: 'obras' });
    expect(result.current.editGastoOpened).toBe(false);
    expect(notifications.show).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Categoria actualizada', color: 'green' })
    );
  });

  it('does not patch when no gasto is under edit, and keeps the modal open on failure', async () => {
    const { result } = await mountController();
    apiFetchMock.mockClear();

    await act(async () => {
      await result.current.handleUpdateCategory({ categoria: 'obras' });
    });
    expect(apiFetchMock).not.toHaveBeenCalled();

    stubApi({ 'PATCH /finanzas/gastos/g1': () => Promise.reject(new Error('409')) });
    act(() => result.current.handleOpenEditCategory(gasto));
    await act(async () => {
      await result.current.handleUpdateCategory({ categoria: 'obras' });
    });

    expect(result.current.editGastoOpened).toBe(true);
    expect(loggerMock.error).toHaveBeenCalledWith('Error updating category:', expect.anything());
  });
});

describe('useFinanzasController — ingresos', () => {
  const values = {
    descripcion: 'Subsidio provincial',
    monto: 90000,
    categoria: 'subsidio',
    fecha: '2026-03-08',
  };

  it('creates an ingreso, closes the modal, reloads and notifies', async () => {
    const { result } = await mountController();
    act(() => result.current.ingresoModal.open());
    apiFetchMock.mockClear();

    await act(async () => {
      await result.current.handleCreateIngreso(values);
    });

    expect(bodyOf('/finanzas/ingresos', 'POST')).toEqual(values);
    expect(result.current.ingresoOpened).toBe(false);
    expect(apiFetchMock).toHaveBeenCalledWith('/finanzas/ingresos');
    expect(notifications.show).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Ingreso registrado', color: 'green' })
    );
  });

  it('keeps the ingreso modal open when creation fails', async () => {
    const { result } = await mountController();
    act(() => result.current.ingresoModal.open());
    stubApi({ 'POST /finanzas/ingresos': () => Promise.reject(new Error('422')) });

    await act(async () => {
      await result.current.handleCreateIngreso(values);
    });

    expect(result.current.ingresoOpened).toBe(true);
    expect(notifications.show).not.toHaveBeenCalled();
    expect(loggerMock.error).toHaveBeenCalledWith('Error creating ingreso:', expect.anything());
  });

  it('handleOpenEditIngreso preloads every field of the edit form', async () => {
    const { result } = await mountController();

    act(() => result.current.handleOpenEditIngreso(ingreso));

    expect(result.current.editIngresoOpened).toBe(true);
    expect(result.current.editingIngreso).toEqual(ingreso);
    expect(result.current.editIngresoForm.values).toEqual({
      descripcion: 'Cuota marzo',
      monto: 20000,
      categoria: 'cuotas',
      fecha: '2026-03-03',
    });
  });

  it('patches the ingreso under edit, clears it and notifies', async () => {
    const { result } = await mountController();
    act(() => result.current.handleOpenEditIngreso(ingreso));

    await act(async () => {
      await result.current.handleUpdateIngreso({ ...values, descripcion: 'Cuota corregida' });
    });

    expect(bodyOf('/finanzas/ingresos/i1', 'PATCH')).toMatchObject({
      descripcion: 'Cuota corregida',
    });
    expect(result.current.editIngresoOpened).toBe(false);
    expect(result.current.editingIngreso).toBeNull();
    expect(notifications.show).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Ingreso actualizado', color: 'green' })
    );
  });

  it('does not patch without an ingreso under edit, and keeps the modal open on failure', async () => {
    const { result } = await mountController();
    apiFetchMock.mockClear();

    await act(async () => {
      await result.current.handleUpdateIngreso(values);
    });
    expect(apiFetchMock).not.toHaveBeenCalled();

    stubApi({ 'PATCH /finanzas/ingresos/i1': () => Promise.reject(new Error('409')) });
    act(() => result.current.handleOpenEditIngreso(ingreso));
    await act(async () => {
      await result.current.handleUpdateIngreso(values);
    });

    expect(result.current.editIngresoOpened).toBe(true);
    expect(result.current.editingIngreso).toEqual(ingreso);
    expect(loggerMock.error).toHaveBeenCalledWith('Error updating ingreso:', expect.anything());
  });
});

describe('useFinanzasController — summary PDF', () => {
  it('downloads the yearly summary with the bearer token and releases the flag', async () => {
    const clickSpy = vi.fn();
    const originalCreate = document.createElement.bind(document);
    vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      const element = originalCreate(tag) as HTMLAnchorElement;
      if (tag === 'a') element.click = clickSpy;
      return element;
    });
    const { result } = await mountController();

    await act(async () => {
      await result.current.handleDownloadSummaryPdf();
    });

    expect(global.fetch).toHaveBeenCalledWith(
      `http://localhost:8000/api/v2/finanzas/resumen/${currentYear}/export-pdf`,
      { headers: { Accept: 'application/pdf', Authorization: 'Bearer token' } }
    );
    expect(clickSpy).toHaveBeenCalled();
    expect(result.current.exportingSummaryPdf).toBe(false);
    vi.mocked(document.createElement).mockRestore();
  });

  it('omits the Authorization header when there is no token', async () => {
    getAuthTokenMock.mockResolvedValueOnce(null);
    const { result } = await mountController();

    await act(async () => {
      await result.current.handleDownloadSummaryPdf();
    });

    expect(global.fetch).toHaveBeenCalledWith(expect.any(String), {
      headers: { Accept: 'application/pdf' },
    });
  });

  it('surfaces the HTTP status when the export request fails', async () => {
    vi.mocked(global.fetch).mockResolvedValue(pdfResponse({ ok: false, status: 503 }));
    const { result } = await mountController();

    await act(async () => {
      await result.current.handleDownloadSummaryPdf();
    });

    expect(notifications.show).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'No se pudo descargar el resumen',
        message: 'Error al descargar el resumen financiero (503)',
        color: 'red',
      })
    );
    expect(result.current.exportingSummaryPdf).toBe(false);
    expect(window.URL.createObjectURL).not.toHaveBeenCalled();
  });

  it('rejects a non-PDF body instead of downloading an HTML error page', async () => {
    vi.mocked(global.fetch).mockResolvedValue(
      pdfResponse({ headers: { get: () => 'text/html' } })
    );
    const { result } = await mountController();

    await act(async () => {
      await result.current.handleDownloadSummaryPdf();
    });

    expect(notifications.show).toHaveBeenCalledWith(
      expect.objectContaining({ message: 'El servidor no devolvio un documento PDF' })
    );
    expect(window.URL.createObjectURL).not.toHaveBeenCalled();
  });

  it('handles a missing content-type header', async () => {
    vi.mocked(global.fetch).mockResolvedValue(pdfResponse({ headers: { get: () => null } }));
    const { result } = await mountController();

    await act(async () => {
      await result.current.handleDownloadSummaryPdf();
    });

    expect(notifications.show).toHaveBeenCalledWith(
      expect.objectContaining({ message: 'El servidor no devolvio un documento PDF' })
    );
  });
});
