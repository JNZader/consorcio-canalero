import { MantineProvider } from '@mantine/core';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('maplibre-gl', () => ({
  default: { Map: vi.fn(), Popup: vi.fn(), LngLatBounds: vi.fn() },
}));

const listCanalPublicacion = vi.fn();
const fetchAprhiReferencia = vi.fn();
const patchCanalPublicacion = vi.fn();

vi.mock('../../src/lib/api/canalesPublicacion', () => ({
  listCanalPublicacion: (...args: unknown[]) => listCanalPublicacion(...args),
  fetchAprhiReferencia: (...args: unknown[]) => fetchAprhiReferencia(...args),
  patchCanalPublicacion: (...args: unknown[]) => patchCanalPublicacion(...args),
}));

vi.mock('../../src/components/admin/CanalesPublicacionMap', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../src/components/admin/CanalesPublicacionMap')>();
  return {
    ...actual,
    CanalesPublicacionMap: ({ onSelect }: { onSelect: (id: string) => void }) => (
      <button type="button" onClick={() => onSelect('canal-1')}>
        mapa-canal
      </button>
    ),
  };
});

import CanalesPublicacionPanel from '../../src/components/admin/CanalesPublicacionPanel';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

describe('<CanalesPublicacionPanel />', () => {
  beforeEach(() => {
    listCanalPublicacion.mockResolvedValue({
      items: [
        {
          id: 'canal-1',
          estado: 'relevado',
          nombre_interno: 'Canal 10 de Mayo',
          nombre_publico: 'Canal 10 de Mayo',
          publicado: true,
          longitud_m: 20740,
        },
      ],
      geojson: { type: 'FeatureCollection', features: [] },
    });
    fetchAprhiReferencia.mockResolvedValue({
      type: 'FeatureCollection',
      features: [{ type: 'Feature', id: 1, properties: { nombre: 'Canal Viejo' }, geometry: null }],
    });
    patchCanalPublicacion.mockResolvedValue({
      id: 'canal-1',
      estado: 'relevado',
      nombre_interno: 'Canal 10 de Mayo',
      nombre_publico: 'Canal 10 de Mayo',
      publicado: false,
      longitud_m: 20740,
    });
  });

  it('shows the APRHI overlay as reference, not as the catalog', async () => {
    renderWithMantine(<CanalesPublicacionPanel />);
    expect(
      await screen.findByText(/red APRHI de referencia/i)
    ).toBeInTheDocument();
    expect(await screen.findByText(/APRHI 1 tramos/i)).toBeInTheDocument();
    expect(screen.getByLabelText('Mostrar red APRHI (solo referencia)')).toBeChecked();
  });

  it('selects a canal from the map and toggles public visibility', async () => {
    const user = userEvent.setup();
    renderWithMantine(<CanalesPublicacionPanel />);
    await user.click(await screen.findByRole('button', { name: 'mapa-canal' }));
    const toggle = await screen.findByLabelText('Publicar Canal 10 de Mayo');
    expect(toggle).toBeChecked();
    await user.click(toggle);
    await waitFor(() => {
      expect(patchCanalPublicacion).toHaveBeenCalledWith('canal-1', { publicado: false });
    });
  });
});
