import { MantineProvider } from '@mantine/core';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ReportDetailModal } from '../../src/components/admin/reports/components/ReportDetailModal';
import { apiFetch } from '../../src/lib/api';

// `AssigneeField` pide la lista de operadores con `apiFetch`; en el test
// la stubbeamos (el resto del módulo queda real para `AuthenticatedImage`).
vi.mock('../../src/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../src/lib/api')>()),
  apiFetch: vi.fn(async () => [] as unknown),
}));

const sampleReport = {
  id: 'rep-101',
  created_at: '2026-03-10T12:00:00Z',
  updated_at: '2026-03-10T12:00:00Z',
  tipo: 'desborde',
  categoria: 'inundacion',
  descripcion: 'Desborde sobre camino secundario',
  ubicacion_texto: 'Camino rural norte',
  estado: 'pendiente',
  latitud: -32.6215,
  longitud: -62.6984,
  imagenes: [],
};

function renderModal(
  report: typeof sampleReport,
  onAsignadoChange?: (asignado: string | null) => void
) {
  return render(
    <MantineProvider env="test">
      <ReportDetailModal
        opened
        onClose={vi.fn()}
        selectedReport={report as never}
        history={[]}
        loadingHistory={false}
        newStatus="pendiente"
        setNewStatus={vi.fn()}
        publicComment=""
        setPublicComment={vi.fn()}
        adminNotes=""
        setAdminNotes={vi.fn()}
        onUpdate={vi.fn()}
        updating={false}
        onAsignadoChange={onAsignadoChange}
      />
    </MantineProvider>
  );
}

describe('ReportDetailModal (ADM-05)', () => {
  it('renders a "Ver en el mapa" deep link with the report coordinates', () => {
    renderModal(sampleReport);

    expect(screen.getByText(/Coordenadas: -32.6215, -62.6984/i)).toBeInTheDocument();
    const mapLink = screen.getByRole('link', { name: /ver en el mapa/i });
    expect(mapLink).toHaveAttribute(
      'href',
      '/mapa?report=1&lat=-32.6215&lng=-62.6984&zoom=15'
    );
  });

  it('seeds the assignee select with the saved asignado_a of the denuncia', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce([
      { id: 'op-7', nombre: 'Romina Torres', email: 'romina@consorcio.gob.ar' },
    ] as never);

    renderModal({ ...sampleReport, asignado_a: 'op-7' });

    // Antes el select arrancaba siempre vacío: el operador guardado no
    // aparecía y limpiar el valor por error era fácil. Ahora el valor
    // persistido se muestra apenas cargan las opciones.
    expect(
      await screen.findByDisplayValue('Romina Torres (romina@consorcio.gob.ar)')
    ).toBeInTheDocument();
  });
});

describe('AssigneeField: persistencia de la asignación', () => {
  const operadores = [
    { id: 'op-7', nombre: 'Romina Torres', email: 'romina@consorcio.gob.ar' },
    { id: 'op-9', nombre: 'Marcos Diaz', email: 'marcos@consorcio.gob.ar' },
  ];

  beforeEach(() => {
    vi.mocked(apiFetch).mockReset();
    // Ruteo por defecto: operadores ok, PATCH ok. Cada test sobreescribe
    // lo que necesita (p.ej. PATCH que rechaza).
    vi.mocked(apiFetch).mockImplementation(async (path: string, options?: RequestInit) => {
      if (path === '/denuncias/operadores') return operadores;
      if (path === '/denuncias/rep-101' && options?.method === 'PATCH') return {};
      return [];
    });
  });

  it('revierte el select al último valor persistido y muestra el error cuando el PATCH falla', async () => {
    const user = userEvent.setup();
    vi.mocked(apiFetch).mockImplementation(async (path: string, options?: RequestInit) => {
      if (path === '/denuncias/operadores') return operadores;
      if (path === '/denuncias/rep-101' && options?.method === 'PATCH') {
        throw new Error('fallo de red');
      }
      return [];
    });

    renderModal({ ...sampleReport, asignado_a: 'op-7' });

    const select = await screen.findByRole('combobox', { name: /asignar operador/i });
    await user.click(select);
    await user.click(await screen.findByRole('option', { name: /marcos diaz/i }));

    // El PATCH rechazó: el select NO puede seguir mostrando una asignación
    // que nunca llegó al backend — vuelve al asignado persistido (op-7).
    await waitFor(() => {
      expect(screen.getByText('No se pudo guardar la asignación')).toBeInTheDocument();
    });
    expect(screen.getByRole('combobox', { name: /asignar operador/i })).toHaveValue(
      'Romina Torres (romina@consorcio.gob.ar)'
    );
  });

  it('limpia el error y notifica al padre cuando un reintento persiste', async () => {
    const user = userEvent.setup();
    let patchFalla = true;
    vi.mocked(apiFetch).mockImplementation(async (path: string, options?: RequestInit) => {
      if (path === '/denuncias/operadores') return operadores;
      if (path === '/denuncias/rep-101' && options?.method === 'PATCH') {
        if (patchFalla) {
          patchFalla = false;
          throw new Error('fallo de red');
        }
        return {};
      }
      return [];
    });
    const onAsignadoChange = vi.fn();

    renderModal({ ...sampleReport, asignado_a: null }, onAsignadoChange);

    // Primer intento: falla y deja el error en pantalla.
    const select = await screen.findByRole('combobox', { name: /asignar operador/i });
    await user.click(select);
    await user.click(await screen.findByRole('option', { name: /marcos diaz/i }));
    await waitFor(() => {
      expect(screen.getByText('No se pudo guardar la asignación')).toBeInTheDocument();
    });

    // Reintento con la misma elección: arranca limpiando el error y, al
    // persistir, el padre recibe el nuevo asignado_a.
    await user.click(select);
    await user.click(await screen.findByRole('option', { name: /marcos diaz/i }));

    await waitFor(() => {
      expect(onAsignadoChange).toHaveBeenCalledWith('op-9');
    });
    expect(screen.queryByText('No se pudo guardar la asignación')).not.toBeInTheDocument();
    expect(screen.getByText('Solo operadores y admins. Vacío quita la asignación.')).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: /asignar operador/i })).toHaveValue(
      'Marcos Diaz (marcos@consorcio.gob.ar)'
    );
  });
});
