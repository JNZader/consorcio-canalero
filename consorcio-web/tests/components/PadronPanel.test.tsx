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
});
