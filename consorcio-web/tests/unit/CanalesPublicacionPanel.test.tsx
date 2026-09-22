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
const patchCanalPublicacionAprhi = vi.fn();

vi.mock('../../src/lib/api/canalesPublicacion', () => ({
  CANAL_ORIGEN: { KMZ: 'kmz', APRHI: 'aprhi' },
  listCanalPublicacion: (...args: unknown[]) => listCanalPublicacion(...args),
  fetchAprhiReferencia: (...args: unknown[]) => fetchAprhiReferencia(...args),
  patchCanalPublicacion: (...args: unknown[]) => patchCanalPublicacion(...args),
  patchCanalPublicacionAprhi: (...args: unknown[]) => patchCanalPublicacionAprhi(...args),
}));

vi.mock('../../src/components/admin/CanalesPublicacionMap', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../src/components/admin/CanalesPublicacionMap')>();
  return {
    ...actual,
    CanalesPublicacionMap: ({ onSelect }: { onSelect: (id: string) => void }) => (
      <>
        <button type="button" onClick={() => onSelect('canal-1')}>
          mapa-canal
        </button>
        <button type="button" onClick={() => onSelect('aprhi-canal-viejo')}>
          mapa-aprhi
        </button>
      </>
    ),
  };
});

import CanalesPublicacionPanel from '../../src/components/admin/CanalesPublicacionPanel';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

describe('<CanalesPublicacionPanel />', () => {
  beforeEach(() => {
    listCanalPublicacion.mockReset();
    fetchAprhiReferencia.mockReset();
    patchCanalPublicacion.mockReset();
    patchCanalPublicacionAprhi.mockReset();
    listCanalPublicacion.mockResolvedValue({
      items: [
        {
          id: 'canal-1',
          estado: 'relevado',
          nombre_interno: 'Canal 10 de Mayo',
          nombre_publico: 'Canal 10 de Mayo',
          publicado: true,
          longitud_m: 20740,
          origen: 'kmz',
        },
      ],
      geojson: { type: 'FeatureCollection', features: [] },
      aprhi_items: [
        {
          id: 'aprhi-canal-viejo',
          estado: 'relevado',
          nombre_interno: 'Canal Viejo',
          nombre_publico: 'Canal Viejo',
          publicado: false,
          longitud_m: 3500,
          origen: 'aprhi',
        },
      ],
      geojson_aprhi: { type: 'FeatureCollection', features: [] },
    });
    patchCanalPublicacion.mockResolvedValue({
      id: 'canal-1',
      estado: 'relevado',
      nombre_interno: 'Canal 10 de Mayo',
      nombre_publico: 'Canal 10 de Mayo',
      publicado: false,
      longitud_m: 20740,
      origen: 'kmz',
    });
    patchCanalPublicacionAprhi.mockResolvedValue({
      id: 'aprhi-canal-viejo',
      estado: 'relevado',
      nombre_interno: 'Canal Viejo',
      nombre_publico: 'Canal Viejo',
      publicado: true,
      longitud_m: 3500,
      origen: 'aprhi',
    });
  });

  it('lists APRHI as an opt-in inventory, not a read-only overlay', async () => {
    renderWithMantine(<CanalesPublicacionPanel />);
    expect(await screen.findByText(/inventario de base para mejorar/i)).toBeInTheDocument();
    expect(await screen.findByText(/APRHI 1 canales/i)).toBeInTheDocument();
    expect(screen.getByLabelText('Mostrar APRHI')).toBeChecked();
    expect(screen.getAllByText('APRHI').length).toBeGreaterThan(0);
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

  it('selects an APRHI canal from the map and shows the publish switch', async () => {
    const user = userEvent.setup();
    renderWithMantine(<CanalesPublicacionPanel />);
    await user.click(await screen.findByRole('button', { name: 'mapa-aprhi' }));
    const toggle = await screen.findByLabelText('Publicar Canal Viejo');
    expect(toggle).not.toBeChecked();
    await user.click(toggle);
    await waitFor(() => {
      expect(patchCanalPublicacionAprhi).toHaveBeenCalledWith('aprhi-canal-viejo', {
        publicado: true,
      });
    });
    expect(patchCanalPublicacion).not.toHaveBeenCalled();
  });
});
