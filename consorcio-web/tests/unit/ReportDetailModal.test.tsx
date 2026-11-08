import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

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

function renderModal(report: typeof sampleReport) {
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
