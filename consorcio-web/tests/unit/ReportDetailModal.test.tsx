import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ReportDetailModal } from '../../src/components/admin/reports/components/ReportDetailModal';

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

describe('ReportDetailModal (ADM-05)', () => {
  it('renders a "Ver en el mapa" deep link with the report coordinates', () => {
    render(
      <MantineProvider env="test">
        <ReportDetailModal
          opened
          onClose={vi.fn()}
          selectedReport={sampleReport as never}
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

    expect(screen.getByText(/Coordenadas: -32.6215, -62.6984/i)).toBeInTheDocument();
    const mapLink = screen.getByRole('link', { name: /ver en el mapa/i });
    expect(mapLink).toHaveAttribute(
      'href',
      '/mapa?report=1&lat=-32.6215&lng=-62.6984&zoom=15'
    );
  });
});
