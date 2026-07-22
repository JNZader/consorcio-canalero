import { MantineProvider } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import FinanzasPanel from '../../src/components/admin/management/FinanzasPanel';
import { API_URL, apiFetch, getAuthToken } from '../../src/lib/api';
import contracts from '../fixtures/admin-api-contracts.json';

vi.mock('../../src/lib/api', () => ({
  API_URL: 'http://localhost:8000',
  apiFetch: vi.fn(),
  getAuthToken: vi.fn().mockResolvedValue('token'),
}));

vi.mock('@mantine/notifications', () => ({
  notifications: {
    show: vi.fn(),
  },
}));

vi.mock('../../src/lib/logger', () => ({
  logger: {
    error: vi.fn(),
    warn: vi.fn(),
    info: vi.fn(),
    debug: vi.fn(),
  },
}));

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

const renderPanel = () =>
  render(
    <MantineProvider>
      <FinanzasPanel />
    </MantineProvider>
  );

function mockFinanceApi() {
  vi.mocked(apiFetch).mockImplementation(async (path: string, options?: RequestInit) => {
    if (path === '/finanzas/gastos' && !options) return [gasto];
    if (path === '/finanzas/ingresos' && !options) return [ingreso];
    if (path.startsWith('/finanzas/resumen/')) {
      return { total_ingresos: 50000, total_gastos: 20000, balance: 30000 };
    }
    if (path === '/finanzas/gastos' && options?.method === 'POST') return { id: 'new-gasto' };
    if (path === '/finanzas/ingresos' && options?.method === 'POST') return { id: 'new-ingreso' };
    if (path === '/finanzas/gastos/g1' && options?.method === 'PATCH') return { id: 'g1' };
    return {};
  });
}

async function chooseOption(input: HTMLElement, name: string) {
  const user = userEvent.setup();
  await user.selectOptions(input, name);
}

describe('FinanzasPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFinanceApi();
    Object.defineProperty(window.URL, 'createObjectURL', {
      configurable: true,
      value: vi.fn(() => 'blob:financial-summary'),
    });
    Object.defineProperty(window.URL, 'revokeObjectURL', {
      configurable: true,
      value: vi.fn(),
    });
    Object.defineProperty(HTMLAnchorElement.prototype, 'click', {
      configurable: true,
      value: vi.fn(),
    });
  });

  it('renders backend-shaped financial rows', async () => {
    const user = userEvent.setup();
    renderPanel();

    expect(await screen.findByText('Administracion Financiera')).toBeInTheDocument();
    expect(screen.getByText(/ingresos totales/i)).toBeInTheDocument();

    await user.click(screen.getByRole('tab', { name: /libro de gastos/i }));
    expect(await screen.findByText('Mantenimiento retroexcavadora')).toBeInTheDocument();

    await user.click(screen.getByRole('tab', { name: /libro de ingresos/i }));
    expect(await screen.findByText('Cuota marzo')).toBeInTheDocument();
    expect(screen.getByText('CUOTAS')).toBeInTheDocument();
  });

  it('creates a gasto with the shared backend contract and offers no fake upload', async () => {
    const user = userEvent.setup();
    renderPanel();
    await screen.findByText('Administracion Financiera');

    await user.click(screen.getByRole('button', { name: /registrar gasto/i }));
    const dialog = await screen.findByRole('dialog', { name: /registrar gasto de caja/i });

    await user.type(
      within(dialog).getByLabelText(/descripcion del gasto/i),
      contracts.finanzas.gasto_create.descripcion
    );
    await user.type(
      within(dialog).getByLabelText(/monto \(\$\)/i),
      String(contracts.finanzas.gasto_create.monto)
    );
    await chooseOption(within(dialog).getByLabelText(/categoria/i), 'obras');
    fireEvent.change(within(dialog).getByLabelText(/^fecha/i), {
      target: { value: contracts.finanzas.gasto_create.fecha },
    });

    expect(within(dialog).queryByLabelText(/subir comprobante/i)).not.toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: /guardar gasto/i }));

    await waitFor(() => {
      const postCall = vi
        .mocked(apiFetch)
        .mock.calls.find(
          ([path, options]) => path === '/finanzas/gastos' && options?.method === 'POST'
        );
      expect(JSON.parse(String(postCall?.[1]?.body))).toEqual(contracts.finanzas.gasto_create);
    });
    expect(apiFetch).not.toHaveBeenCalledWith(
      '/finanzas/comprobantes/upload',
      expect.anything()
    );
    expect(notifications.show).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Gasto registrado', color: 'green' })
    );
  });

  it('connects new gasto validation errors to required fields', async () => {
    const user = userEvent.setup();
    renderPanel();
    await screen.findByText('Administracion Financiera');

    await user.click(screen.getByRole('button', { name: /registrar gasto/i }));
    const dialog = await screen.findByRole('dialog', { name: /registrar gasto de caja/i });
    await user.click(within(dialog).getByRole('button', { name: /guardar gasto/i }));

    const description = within(dialog).getByLabelText(/descripcion del gasto/i);
    const amount = within(dialog).getByLabelText(/monto \(\$\)/i);
    const category = within(dialog).getByLabelText(/categoria/i);

    await waitFor(() => {
      expect(description).toHaveAttribute('aria-invalid', 'true');
      expect(description.getAttribute('aria-describedby')).toContain('gasto-description-error');
      expect(amount).toHaveAttribute('aria-invalid', 'true');
      expect(amount.getAttribute('aria-describedby')).toContain('gasto-amount-error');
      expect(category).toHaveAttribute('aria-invalid', 'true');
      expect(category.getAttribute('aria-describedby')).toContain('gasto-category-error');
    });
  });

  it('creates an ingreso with backend field names and enum values', async () => {
    const user = userEvent.setup();
    renderPanel();
    await screen.findByText('Administracion Financiera');

    await user.click(screen.getByRole('button', { name: /registrar ingreso/i }));
    const dialog = await screen.findByRole('dialog', { name: /registrar ingreso/i });
    await user.type(
      within(dialog).getByLabelText(/descripcion/i),
      contracts.finanzas.ingreso_create.descripcion
    );
    await user.type(
      within(dialog).getByLabelText(/monto \(\$\)/i),
      String(contracts.finanzas.ingreso_create.monto)
    );
    await chooseOption(within(dialog).getByLabelText(/categoria/i), 'subsidio');
    fireEvent.change(within(dialog).getByLabelText(/^fecha/i), {
      target: { value: contracts.finanzas.ingreso_create.fecha },
    });
    await user.click(within(dialog).getByRole('button', { name: /guardar ingreso/i }));

    await waitFor(() => {
      const postCall = vi
        .mocked(apiFetch)
        .mock.calls.find(
          ([path, options]) => path === '/finanzas/ingresos' && options?.method === 'POST'
        );
      expect(JSON.parse(String(postCall?.[1]?.body))).toEqual(contracts.finanzas.ingreso_create);
    });
    expect(notifications.show).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Ingreso registrado', color: 'green' })
    );
  });

  it('connects edit ingreso validation errors to required fields', async () => {
    const user = userEvent.setup();
    renderPanel();
    await screen.findByText('Administracion Financiera');

    await user.click(screen.getByRole('tab', { name: /libro de ingresos/i }));
    const row = await screen.findByRole('row', { name: /cuota marzo/i });
    await user.click(within(row).getByRole('button'));

    const dialog = await screen.findByRole('dialog', { name: /editar ingreso/i });
    const description = within(dialog).getByLabelText(/descripcion/i);
    const amount = within(dialog).getByLabelText(/monto \(\$\)/i);
    await user.clear(description);
    await user.clear(amount);
    await user.click(within(dialog).getByRole('button', { name: /actualizar ingreso/i }));

    await waitFor(() => {
      expect(description).toHaveAttribute('aria-invalid', 'true');
      expect(description.getAttribute('aria-describedby')).toContain(
        'edit-ingreso-description-error'
      );
      expect(amount).toHaveAttribute('aria-invalid', 'true');
      expect(amount.getAttribute('aria-describedby')).toContain('edit-ingreso-amount-error');
    });
  });

  it('updates a gasto using a backend-supported category', async () => {
    const user = userEvent.setup();
    renderPanel();
    await screen.findByText('Administracion Financiera');

    await user.click(screen.getByRole('tab', { name: /libro de gastos/i }));
    const row = await screen.findByRole('row', { name: /mantenimiento retroexcavadora/i });
    await user.click(within(row).getByRole('button'));

    const dialog = await screen.findByRole('dialog', { name: /editar categoria de gasto/i });
    await chooseOption(within(dialog).getByLabelText(/categoria/i), 'obras');
    await user.click(within(dialog).getByRole('button', { name: /actualizar categoria/i }));

    await waitFor(() => {
      expect(apiFetch).toHaveBeenCalledWith('/finanzas/gastos/g1', {
        method: 'PATCH',
        body: JSON.stringify({ categoria: 'obras' }),
      });
    });
  });

  it('downloads the authenticated year-specific financial summary PDF', async () => {
    const user = userEvent.setup();
    const currentYear = new Date().getFullYear();
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(new Blob(['pdf'], { type: 'application/pdf' }), {
        status: 200,
        headers: { 'Content-Type': 'application/pdf' },
      })
    );
    vi.stubGlobal('fetch', fetchMock);
    const appendSpy = vi.spyOn(document.body, 'appendChild');

    renderPanel();
    await screen.findByText('Administracion Financiera');

    await user.click(
      screen.getByRole('button', { name: /descargar resumen financiero pdf/i })
    );

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        `${API_URL}/api/v2/finanzas/resumen/${currentYear}/export-pdf`,
        {
          headers: {
            Accept: 'application/pdf',
            Authorization: 'Bearer token',
          },
        }
      );
    });
    expect(getAuthToken).toHaveBeenCalledTimes(1);

    const appendedAnchor = appendSpy.mock.calls
      .map(([node]) => node)
      .find((node): node is HTMLAnchorElement => node instanceof HTMLAnchorElement);
    expect(appendedAnchor?.download).toBe(`resumen_financiero_${currentYear}.pdf`);
    expect(appendedAnchor?.href).toContain('blob:financial-summary');
  });

  it('reports a truthful error when the financial PDF cannot be downloaded', async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: 'unavailable' }), {
          status: 503,
          headers: { 'Content-Type': 'application/json' },
        })
      )
    );

    renderPanel();
    await screen.findByText('Administracion Financiera');
    await user.click(
      screen.getByRole('button', { name: /descargar resumen financiero pdf/i })
    );

    await waitFor(() => {
      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'No se pudo descargar el resumen',
          color: 'red',
        })
      );
    });
  });

});
