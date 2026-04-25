import { MantineProvider } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ReunionesPanel from '../../src/components/admin/management/ReunionesPanel';
import { apiFetch } from '../../src/lib/api';

vi.mock('../../src/lib/api', () => ({
  apiFetch: vi.fn(),
  API_URL: 'http://localhost:8000',
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

const renderPanel = () => render(<MantineProvider><ReunionesPanel /></MantineProvider>);

describe('ReunionesPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(apiFetch).mockImplementation(async (path: string, options?: RequestInit) => {
      if (path === '/reuniones' && !options) {
        return [
          {
            id: 'r1',
            titulo: 'Reunion mensual',
            fecha_reunion: '2026-03-01T10:00:00.000Z',
            lugar: 'Sede central',
            estado: 'planificada',
            descripcion: 'Temas de mantenimiento',
            orden_del_dia_items: ['Canales', 'Puentes'],
          },
        ];
      }

      if (path === '/denuncias?limit=50') {
        return { items: [] };
      }

      if (path === '/tramites') {
        return { data: [] };
      }

      if (path === '/infraestructura/assets') {
        return { results: [] };
      }

      if (path === '/reuniones/r1/agenda') {
        return [
          {
            id: 'a1',
            titulo: 'Reparacion compuerta',
            descripcion: 'Definir responsables',
            referencias: [{ entidad_tipo: 'reporte', entidad_id: 'rep-1', metadata: { label: 'INCIDENTE' } }],
          },
        ];
      }

      return {};
    });
  });

  it('renders reuniones list and opens agenda details', async () => {
    const user = userEvent.setup();
    renderPanel();

    expect(await screen.findByText('Reuniones de Comision')).toBeInTheDocument();
    expect(screen.getByText('Reunion mensual')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /gestionar agenda/i }));

    expect(await screen.findByText('Orden del Dia')).toBeInTheDocument();
    expect(screen.getByText(/Agregar Tema a la Agenda/i)).toBeInTheDocument();
    expect(screen.getByText(/Reparacion compuerta/i)).toBeInTheDocument();
  });

  it('creates reunion with checklist points', async () => {
    const user = userEvent.setup();
    renderPanel();

    await screen.findByText('Reuniones de Comision');
    await user.click(screen.getByRole('button', { name: /nueva reunion/i }));
    const dialog = await screen.findByRole('dialog', { name: /nueva reunion/i });

    await user.type(
      within(dialog).getByPlaceholderText('Ej: Reunion de comision de marzo'),
      'Reunion extraordinaria'
    );
    fireEvent.change(within(dialog).getByLabelText(/fecha y hora/i), {
      target: { value: '2026-04-10T09:30' },
    });
    await user.type(within(dialog).getByLabelText('Lugar'), 'Salon principal');
    await user.type(within(dialog).getByPlaceholderText(/escribe un punto/i), 'Aprobar presupuesto');
    await user.click(within(dialog).getByRole('button', { name: /anadir punto/i }));

    await user.click(within(dialog).getByRole('button', { name: /crear reunion/i }));

    await waitFor(() => {
      expect(apiFetch).toHaveBeenCalledWith(
        '/reuniones',
        expect.objectContaining({ method: 'POST' })
      );
    });

    expect(notifications.show).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Reunion creada',
        color: 'green',
      })
    );
  });

  it('connects create reunion validation errors to their fields', async () => {
    const user = userEvent.setup();
    renderPanel();

    await screen.findByText('Reuniones de Comision');
    await user.click(screen.getByRole('button', { name: /nueva reunion/i }));
    const dialog = await screen.findByRole('dialog', { name: /nueva reunion/i });

    await user.click(within(dialog).getByRole('button', { name: /crear reunion/i }));

    const title = within(dialog).getByLabelText(/titulo/i);
    const date = within(dialog).getByLabelText(/fecha y hora/i);

    await waitFor(() => {
      expect(title).toHaveAttribute('aria-invalid', 'true');
      expect(title.getAttribute('aria-describedby')).toContain('reunion-title-error');
      expect(date).toHaveAttribute('aria-invalid', 'true');
      expect(date.getAttribute('aria-describedby')).toContain('reunion-date-error');
    });

    expect(within(dialog).getByText(/titulo requerido/i)).toHaveAttribute('role', 'alert');
    expect(within(dialog).getByText(/fecha y hora requeridas/i)).toHaveAttribute('role', 'alert');
    expect(within(dialog).getByText(/agrega al menos un punto/i)).toHaveAttribute('role', 'alert');
    expect(apiFetch).not.toHaveBeenCalledWith(
      '/reuniones',
      expect.objectContaining({ method: 'POST' })
    );
  });

  it('shows empty agenda and allows adding a new topic', async () => {
    const user = userEvent.setup();
    let agendaItems: Array<{
      id: string;
      titulo: string;
      descripcion: string;
      referencias: Array<{ entidad_tipo: string; entidad_id: string; metadata?: { label?: string } }>;
    }> = [];

    vi.mocked(apiFetch).mockImplementation(async (path: string, options?: RequestInit) => {
      if (path === '/reuniones' && !options) {
        return [
          {
            id: 'r1',
            titulo: 'Reunion mensual',
            fecha_reunion: '2026-03-01T10:00:00.000Z',
            lugar: 'Sede central',
            estado: 'planificada',
            descripcion: 'Temas de mantenimiento',
            orden_del_dia_items: ['Canales'],
          },
        ];
      }
      if (path === '/denuncias?limit=50') {
        return { items: [] };
      }
      if (path === '/tramites') {
        return { data: [] };
      }
      if (path === '/infraestructura/assets') {
        return { results: [] };
      }
      if (path === '/reuniones/r1/agenda' && !options) {
        return agendaItems;
      }
      if (path === '/reuniones/r1/agenda' && options?.method === 'POST') {
        agendaItems = [
          {
            id: 'a2',
            titulo: 'Nuevo tema operativo',
            descripcion: 'Asignar cuadrillas',
            referencias: [],
          },
        ];
        return { id: 'a2' };
      }
      return {};
    });

    renderPanel();
    await screen.findByText('Reuniones de Comision');

    await user.click(screen.getByRole('button', { name: /gestionar agenda/i }));
    expect(await screen.findByText(/no hay temas en la agenda todavia/i)).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText(/titulo del tema/i), 'Nuevo tema operativo');
    await user.type(screen.getByPlaceholderText(/descripcion o puntos a discutir/i), 'Asignar cuadrillas');
    await user.click(screen.getByRole('button', { name: /anadir tema/i }));

    await waitFor(() => {
      expect(apiFetch).toHaveBeenCalledWith(
        '/reuniones/r1/agenda',
        expect.objectContaining({ method: 'POST' })
      );
    });

    expect(await screen.findByText(/1\. nuevo tema operativo/i)).toBeInTheDocument();
  });

  it('connects agenda topic title validation error to the field', async () => {
    const user = userEvent.setup();
    renderPanel();

    await screen.findByText('Reuniones de Comision');
    await user.click(screen.getByRole('button', { name: /gestionar agenda/i }));

    const titleInput = await screen.findByLabelText(/titulo del tema/i);
    await user.click(screen.getByRole('button', { name: /anadir tema/i }));

    await waitFor(() => {
      expect(titleInput).toHaveAttribute('aria-invalid', 'true');
      expect(titleInput.getAttribute('aria-describedby')).toContain('agenda-topic-title-error');
    });

    expect(screen.getByText(/titulo requerido/i)).toHaveAttribute('role', 'alert');
    expect(apiFetch).not.toHaveBeenCalledWith(
      '/reuniones/r1/agenda',
      expect.objectContaining({ method: 'POST' })
    );
  });

  it('shows error notification when creating reunion fails', async () => {
    const user = userEvent.setup();

    vi.mocked(apiFetch).mockImplementation(async (path: string, options?: RequestInit) => {
      if (path === '/reuniones' && !options) {
        return [];
      }
      if (path === '/denuncias?limit=50') {
        return { items: [] };
      }
      if (path === '/tramites') {
        return { data: [] };
      }
      if (path === '/infraestructura/assets') {
        return { results: [] };
      }
      if (path === '/reuniones' && options?.method === 'POST') {
        throw new Error('backend unavailable');
      }
      return {};
    });

    renderPanel();
    await screen.findByText('Reuniones de Comision');

    await user.click(screen.getByRole('button', { name: /nueva reunion/i }));
    const dialog = await screen.findByRole('dialog', { name: /nueva reunion/i });

    await user.type(within(dialog).getByLabelText(/titulo/i), 'Reunion urgente');
    fireEvent.change(within(dialog).getByLabelText(/fecha y hora/i), {
      target: { value: '2026-05-12T09:00' },
    });
    await user.type(within(dialog).getByPlaceholderText(/escribe un punto/i), 'Revisar presupuesto');
    await user.click(within(dialog).getByRole('button', { name: /anadir punto/i }));
    await user.click(within(dialog).getByRole('button', { name: /crear reunion/i }));

    await waitFor(() => {
      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'No se pudo crear la reunion',
          color: 'red',
        })
      );
    });
  });
});
