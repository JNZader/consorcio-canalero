import { MantineProvider } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import PadronPanel from '../../src/components/admin/management/PadronPanel';
import { apiFetch } from '../../src/lib/api';

vi.mock('../../src/lib/api', () => ({
  apiFetch: vi.fn(),
}));

vi.mock('../../src/lib/errorHandler', () => ({
  handleError: vi.fn(),
}));

vi.mock('../../src/lib/validators', () => ({
  isValidCUIT: vi.fn(() => true),
}));

vi.mock('@mantine/notifications', () => ({
  notifications: {
    show: vi.fn(),
  },
}));

const renderPanel = () => render(<MantineProvider><PadronPanel /></MantineProvider>);

describe('PadronPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(apiFetch).mockImplementation(async (path: string) => {
      if (path.startsWith('/padron/consorcistas?search=')) {
        return [
          {
            id: 'c1',
            nombre: 'Ana',
            apellido: 'Perez',
            cuit: '20-12345678-9',
            representa_a: 'Establecimiento La Paz',
          },
        ];
      }
      if (path === '/padron/consorcistas/c1/pagos') {
        return [{ id: 'p1', anio: 2025, monto: 5000, estado: 'pagado', fecha_pago: '2025-05-12' }];
      }
      return {};
    });
  });

  it('renders consorcistas and opens pagos modal', async () => {
    const user = userEvent.setup();
    renderPanel();

    expect(await screen.findByText('Padrón de Consorcistas')).toBeInTheDocument();
    expect(screen.getByText('Perez, Ana')).toBeInTheDocument();

    const row = screen.getByRole('row', { name: /perez, ana/i });
    await user.click(within(row).getByRole('button'));
    expect(await screen.findByText('Estado de Cuotas Anuales')).toBeInTheDocument();
    expect(screen.getByText('CUIT: 20-12345678-9')).toBeInTheDocument();
  });

  it('shows validation notification when import is requested without file', async () => {
    const user = userEvent.setup();
    renderPanel();
    await screen.findByText('Padrón de Consorcistas');

    await user.click(screen.getByRole('button', { name: /importar csv\/xls/i }));
    await user.click(screen.getByRole('button', { name: /procesar importacion/i }));

    await waitFor(() => {
      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Archivo requerido',
          color: 'yellow',
        })
      );
    });
  });

  it('creates a new consorcista from modal form', async () => {
    const user = userEvent.setup();
    renderPanel();
    await screen.findByText('Padrón de Consorcistas');

    await user.click(screen.getByRole('button', { name: /nuevo consorcista/i }));
    const dialog = await screen.findByRole('dialog', { name: /registrar nuevo consorcista/i });

    await user.type(within(dialog).getByLabelText(/nombre/i), 'Carlos');
    await user.type(within(dialog).getByLabelText(/apellido/i), 'Gomez');
    await user.type(within(dialog).getByLabelText(/cuit/i), '20-99887766-1');
    await user.click(within(dialog).getByRole('button', { name: /guardar en padrón/i }));

    await waitFor(() => {
      expect(apiFetch).toHaveBeenCalledWith(
        '/padron/consorcistas',
        expect.objectContaining({ method: 'POST' })
      );
    });

    expect(notifications.show).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Consorcista registrado', color: 'green' })
    );
  });

  it('validates pago input and then registers payment', async () => {
    const user = userEvent.setup();

    vi.mocked(apiFetch).mockImplementation(async (path: string, options?: RequestInit) => {
      if (path.startsWith('/padron/consorcistas?search=')) {
        return [
          {
            id: 'c1',
            nombre: 'Ana',
            apellido: 'Perez',
            cuit: '20-12345678-9',
            representa_a: 'Establecimiento La Paz',
          },
        ];
      }
      if (path === '/padron/consorcistas/c1/pagos') {
        return [];
      }
      if (path === '/padron/pagos' && options?.method === 'POST') {
        return { id: 'p2' };
      }
      return {};
    });

    renderPanel();
    await screen.findByText('Padrón de Consorcistas');

    const row = screen.getByRole('row', { name: /perez, ana/i });
    await user.click(within(row).getByRole('button'));
    const pagosDialog = await screen.findByRole('dialog', { name: /estado de cuotas anuales/i });

    await user.click(within(pagosDialog).getByRole('button', { name: /registrar/i }));
    expect(notifications.show).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Datos incompletos', color: 'yellow' })
    );

    await user.type(within(pagosDialog).getByLabelText(/monto/i), '3500');
    await user.click(within(pagosDialog).getByRole('button', { name: /registrar/i }));

    await waitFor(() => {
      expect(apiFetch).toHaveBeenCalledWith('/padron/pagos', expect.objectContaining({ method: 'POST' }));
    });
    expect(notifications.show).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Pago registrado', color: 'green' })
    );
  });

  it('imports padron file and renders import summary', async () => {
    const user = userEvent.setup();

    vi.mocked(apiFetch).mockImplementation(async (path: string, options?: RequestInit) => {
      if (path.startsWith('/padron/consorcistas?search=')) {
        return [
          {
            id: 'c1',
            nombre: 'Ana',
            apellido: 'Perez',
            cuit: '20-12345678-9',
            representa_a: 'Establecimiento La Paz',
          },
        ];
      }
      if (path === '/padron/consorcistas/import' && options?.method === 'POST') {
        return {
          filename: 'padron.csv',
          processed: 3,
          upserted: 2,
          skipped: 1,
          errors: [{ row: 2, error: 'CUIT invalido' }],
        };
      }
      return {};
    });

    renderPanel();
    await screen.findByText('Padrón de Consorcistas');

    await user.click(screen.getByRole('button', { name: /importar csv\/xls/i }));
    const dialog = await screen.findByRole('dialog', { name: /importar padron desde archivo/i });

    const file = new File(['cuit,nombre'], 'padron.csv', { type: 'text/csv' });
    const fileInput = dialog.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(fileInput, file);
    await user.click(within(dialog).getByRole('button', { name: /procesar importacion/i }));

    await waitFor(() => {
      expect(apiFetch).toHaveBeenCalledWith(
        '/padron/consorcistas/import',
        expect.objectContaining({ method: 'POST' })
      );
    });

    expect(await within(dialog).findByText('Archivo: padron.csv')).toBeInTheDocument();
    expect(within(dialog).getByText('Filas procesadas: 3')).toBeInTheDocument();
    expect(notifications.show).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Importacion completada', color: 'yellow' })
    );
  });
});
