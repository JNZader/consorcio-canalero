import { MantineProvider } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import FinanzasPanel from '../../src/components/admin/management/FinanzasPanel';
import { apiFetch } from '../../src/lib/api';

vi.mock('../../src/lib/api', () => ({
  apiFetch: vi.fn(),
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

const renderPanel = () => render(<MantineProvider><FinanzasPanel /></MantineProvider>);

describe('FinanzasPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(apiFetch).mockImplementation(async (path: string) => {
      if (path === '/finance/gastos') {
        return [
          {
            id: 'g1',
            fecha: '2026-03-02',
            descripcion: 'Combustible retroexcavadora',
            monto: 12000,
            categoria: 'combustible',
            infraestructura: { nombre: 'Canal Norte' },
          },
        ];
      }

      if (path === '/finance/ingresos') {
        return [
          {
            id: 'i1',
            fecha: '2026-03-03',
            descripcion: 'Cuota marzo',
            monto: 20000,
            fuente: 'cuotas_extra',
            pagador: 'Productor A',
          },
        ];
      }

      if (path.startsWith('/finance/balance-summary/')) {
        return { total_ingresos: 50000, total_gastos: 20000, balance: 30000 };
      }

      if (path === '/finance/categorias') {
        return ['combustible', 'obras'];
      }

      if (path === '/finance/fuentes') {
        return ['cuotas_extra', 'subsidio'];
      }

      return {};
    });
  });

  it('renders financial summary and expense rows', async () => {
    const user = userEvent.setup();
    renderPanel();

    expect(await screen.findByText('Administracion Financiera')).toBeInTheDocument();
    expect(screen.getByText(/ingresos totales/i)).toBeInTheDocument();
    expect(screen.getByText(/caja actual/i)).toBeInTheDocument();

    await user.click(screen.getByRole('tab', { name: /libro de gastos/i }));
    expect(await screen.findByText('Combustible retroexcavadora')).toBeInTheDocument();

    await user.click(screen.getByRole('tab', { name: /libro de ingresos/i }));
    expect(await screen.findByText('Cuota marzo')).toBeInTheDocument();
  });

  it('creates a new gasto and shows success notification', async () => {
    const user = userEvent.setup();

    vi.mocked(apiFetch).mockImplementation(async (path: string, options?: RequestInit) => {
      if (path === '/finance/gastos' && !options) {
        return [];
      }
      if (path === '/finance/ingresos' && !options) {
        return [];
      }
      if (path.startsWith('/finance/balance-summary/')) {
        return { total_ingresos: 0, total_gastos: 0, balance: 0 };
      }
      if (path === '/finance/categorias') {
        return ['obras'];
      }
      if (path === '/finance/fuentes') {
        return ['subsidio'];
      }
      if (path === '/finance/gastos' && options?.method === 'POST') {
        return { id: 'new' };
      }
      return {};
    });

    renderPanel();
    await screen.findByText('Administracion Financiera');

    await user.click(screen.getByRole('button', { name: /registrar gasto/i }));
    const dialog = await screen.findByRole('dialog', { name: /registrar gasto de caja/i });

    await user.type(within(dialog).getByLabelText(/descripcion del gasto/i), 'Repuestos bomba');
    await user.type(within(dialog).getByLabelText(/monto \(\$\)/i), '1500');

    const categoriaInput = within(dialog).getByLabelText(/categoria/i);
    fireEvent.change(categoriaInput, { target: { value: 'obras' } });

    fireEvent.change(within(dialog).getByLabelText(/^fecha$/i), { target: { value: '2026-03-10' } });
    await user.click(within(dialog).getByRole('button', { name: /guardar gasto/i }));

    await waitFor(() => {
      expect(apiFetch).toHaveBeenCalledWith(
        '/finance/gastos',
        expect.objectContaining({ method: 'POST' })
      );
    });

    expect(notifications.show).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Gasto registrado',
        color: 'green',
      })
    );
  });

  it('adds a custom category from modal and applies it to form', async () => {
    const user = userEvent.setup();
    renderPanel();
    await screen.findByText('Administracion Financiera');

    await user.click(screen.getByRole('button', { name: /registrar gasto/i }));
    const gastoDialog = await screen.findByRole('dialog', { name: /registrar gasto de caja/i });
    await user.click(within(gastoDialog).getByRole('button', { name: /agregar categoria/i }));

    const dialog = screen.getByRole('dialog', { name: /nueva categoria/i });
    await user.type(within(dialog).getByLabelText('Nombre'), 'Viaticos');
    await user.click(within(dialog).getByRole('button', { name: /guardar categoria/i }));

    expect(within(gastoDialog).getByLabelText(/categoria/i)).toHaveValue('viaticos');
  });

  it('registers a new ingreso using a custom source', async () => {
    const user = userEvent.setup();

    vi.mocked(apiFetch).mockImplementation(async (path: string, options?: RequestInit) => {
      if (path === '/finance/gastos' && !options) {
        return [];
      }
      if (path === '/finance/ingresos' && !options) {
        return [];
      }
      if (path.startsWith('/finance/balance-summary/')) {
        return { total_ingresos: 0, total_gastos: 0, balance: 0 };
      }
      if (path === '/finance/categorias') {
        return ['obras'];
      }
      if (path === '/finance/fuentes') {
        return [];
      }
      if (path === '/finance/ingresos' && options?.method === 'POST') {
        return { id: 'ing-2' };
      }
      return {};
    });

    renderPanel();
    await screen.findByText('Administracion Financiera');

    await user.click(screen.getByRole('button', { name: /registrar ingreso/i }));
    const ingresoDialog = await screen.findByRole('dialog', { name: /registrar ingreso/i });

    await user.click(within(ingresoDialog).getByRole('button', { name: /agregar fuente/i }));
    const sourceDialog = await screen.findByRole('dialog', { name: /nueva fuente de ingreso/i });
    await user.type(within(sourceDialog).getByLabelText('Nombre'), 'Convenio');
    await user.click(within(sourceDialog).getByRole('button', { name: /guardar fuente/i }));

    expect(within(ingresoDialog).getByLabelText(/fuente/i)).toHaveValue('convenio');

    await user.type(within(ingresoDialog).getByLabelText(/descripcion/i), 'Aporte extraordinario');
    await user.type(within(ingresoDialog).getByLabelText(/monto \(\$\)/i), '2500');
    await user.type(within(ingresoDialog).getByLabelText(/pagador/i), 'Provincia');
    await user.click(within(ingresoDialog).getByRole('button', { name: /guardar ingreso/i }));

    await waitFor(() => {
      expect(apiFetch).toHaveBeenCalledWith(
        '/finance/ingresos',
        expect.objectContaining({ method: 'POST' })
      );
    });

    expect(notifications.show).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Ingreso registrado',
        color: 'green',
      })
    );
  });

  it('updates gasto category from edit modal', async () => {
    const user = userEvent.setup();

    vi.mocked(apiFetch).mockImplementation(async (path: string, options?: RequestInit) => {
      if (path === '/finance/gastos' && !options) {
        return [
          {
            id: 'g1',
            fecha: '2026-03-02',
            descripcion: 'Combustible retroexcavadora',
            monto: 12000,
            categoria: 'combustible',
            infraestructura: { nombre: 'Canal Norte' },
          },
        ];
      }
      if (path === '/finance/ingresos' && !options) {
        return [];
      }
      if (path.startsWith('/finance/balance-summary/')) {
        return { total_ingresos: 0, total_gastos: 12000, balance: -12000 };
      }
      if (path === '/finance/categorias') {
        return ['combustible', 'obras'];
      }
      if (path === '/finance/fuentes') {
        return ['subsidio'];
      }
      if (path === '/finance/gastos/g1' && options?.method === 'PATCH') {
        return { id: 'g1' };
      }
      return {};
    });

    renderPanel();
    await screen.findByText('Administracion Financiera');

    await user.click(screen.getByRole('tab', { name: /libro de gastos/i }));
    const row = await screen.findByRole('row', { name: /combustible retroexcavadora/i });
    await user.click(within(row).getByRole('button'));

    const editDialog = await screen.findByRole('dialog', { name: /editar categoria de gasto/i });
    fireEvent.change(within(editDialog).getByLabelText(/categoria/i), { target: { value: 'obras' } });
    await user.click(within(editDialog).getByRole('button', { name: /actualizar categoria/i }));

    await waitFor(() => {
      expect(apiFetch).toHaveBeenCalledWith(
        '/finance/gastos/g1',
        expect.objectContaining({ method: 'PATCH' })
      );
    });

    expect(notifications.show).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Categoria actualizada', color: 'green' })
    );
  });
});
