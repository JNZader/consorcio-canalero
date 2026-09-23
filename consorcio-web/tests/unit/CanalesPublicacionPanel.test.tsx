import { MantineProvider } from '@mantine/core';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('maplibre-gl', () => ({
  default: { Map: vi.fn(), Popup: vi.fn(), LngLatBounds: vi.fn() },
}));

const listCanalPublicacion = vi.fn();
const fetchAprhiReferencia = vi.fn();
const patchCanalPublicacion = vi.fn();
const patchCanalPublicacionAprhi = vi.fn();
const patchCanalPublicacionSrPa = vi.fn();

vi.mock('../../src/lib/api/canalesPublicacion', () => ({
  CANAL_ORIGEN: { KMZ: 'kmz', APRHI: 'aprhi', SR_PA: 'sr_pa' },
  listCanalPublicacion: (...args: unknown[]) => listCanalPublicacion(...args),
  fetchAprhiReferencia: (...args: unknown[]) => fetchAprhiReferencia(...args),
  patchCanalPublicacion: (...args: unknown[]) => patchCanalPublicacion(...args),
  patchCanalPublicacionAprhi: (...args: unknown[]) => patchCanalPublicacionAprhi(...args),
  patchCanalPublicacionSrPa: (...args: unknown[]) => patchCanalPublicacionSrPa(...args),
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

const srPaCollection = {
  type: 'FeatureCollection',
  features: [
    {
      type: 'Feature',
      id: 'CA00140',
      geometry: { type: 'LineString', coordinates: [[-62.5, -32.5], [-62.4, -32.4]] },
      properties: {
        Identificador: 'CA00140',
        Nombre_Obra: 'Tramo Nuevo - Canal San Marcos',
        Estado_Registro: 'Vigente',
        Tipo_Obra_Lineal: 'Canal (CA)',
        OBJECTID: 140,
      },
    },
  ],
};

describe('<CanalesPublicacionPanel />', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo) => {
        const url = String(input);
        if (url.includes('aprhi_sr_pa')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve(srPaCollection),
          } as Response);
        }
        return Promise.resolve({ ok: false, json: () => Promise.resolve(null) } as Response);
      })
    );
    listCanalPublicacion.mockReset();
    fetchAprhiReferencia.mockReset();
    patchCanalPublicacion.mockReset();
    patchCanalPublicacionAprhi.mockReset();
    patchCanalPublicacionSrPa.mockReset();
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
        {
          id: 'canal-prop',
          estado: 'propuesto',
          nombre_interno: 'Canal propuesto',
          nombre_publico: 'Canal propuesto',
          publicado: true,
          longitud_m: 1000,
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
      sr_pa_items: [],
      geojson_sr_pa: { type: 'FeatureCollection', features: [] },
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
    patchCanalPublicacionSrPa.mockResolvedValue({
      id: 'srpa:CA00140',
      estado: 'relevado',
      nombre_interno: 'Tramo Nuevo - Canal San Marcos',
      nombre_publico: 'Tramo Nuevo - Canal San Marcos',
      publicado: true,
      origen: 'sr_pa',
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('treats SR PA as the APRHI layer and keeps the old existentes overlay off', async () => {
    renderWithMantine(<CanalesPublicacionPanel />);
    expect(await screen.findByText(/obras lineales rurales APRHI/i)).toBeInTheDocument();
    expect(screen.getByLabelText('Ver APRHI')).toBeChecked();
    expect(screen.getByLabelText('Ver existentes')).not.toBeChecked();
    expect(screen.getByText(/Existentes 1/)).toBeInTheDocument();
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

  it('selects an old existentes canal from the map and shows the publish switch', async () => {
    const user = userEvent.setup();
    renderWithMantine(<CanalesPublicacionPanel />);
    await user.click(await screen.findByLabelText('Ver existentes'));
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

  it('hides relevadas from the list without calling patch', async () => {
    const user = userEvent.setup();
    renderWithMantine(<CanalesPublicacionPanel />);
    expect(await screen.findByText('Canal 10 de Mayo')).toBeInTheDocument();
    expect(screen.getByText('Canal propuesto')).toBeInTheDocument();
    await user.click(screen.getByLabelText('Ver relevadas'));
    expect(patchCanalPublicacion).not.toHaveBeenCalled();
    expect(patchCanalPublicacionAprhi).not.toHaveBeenCalled();
    expect(screen.queryByText('Canal 10 de Mayo')).not.toBeInTheDocument();
    expect(screen.getByText('Canal propuesto')).toBeInTheDocument();
  });

  it('lists APRHI SR PA in the sidebar when only that layer is on', async () => {
    const user = userEvent.setup();
    renderWithMantine(<CanalesPublicacionPanel />);
    expect(await screen.findByText(/Tramo Nuevo - Canal San Marcos/)).toBeInTheDocument();
    expect(screen.getByText('APRHI SR PA 1')).toBeInTheDocument();
    await user.click(screen.getByLabelText('Ver relevadas'));
    await user.click(screen.getByLabelText('Ver propuestas'));
    expect(screen.queryByText('Canal 10 de Mayo')).not.toBeInTheDocument();
    expect(screen.getByText(/Tramo Nuevo - Canal San Marcos/)).toBeInTheDocument();
    expect(screen.getByText('CA00140')).toBeInTheDocument();
  });

  it('publishes a selected SR PA work without touching KMZ or existentes', async () => {
    const user = userEvent.setup();
    renderWithMantine(<CanalesPublicacionPanel />);
    await user.click(await screen.findByText(/Tramo Nuevo - Canal San Marcos/));
    const toggle = await screen.findByLabelText('Publicar Tramo Nuevo - Canal San Marcos');
    expect(toggle).not.toBeChecked();
    await user.click(toggle);
    await waitFor(() => {
      expect(patchCanalPublicacionSrPa).toHaveBeenCalledWith('srpa:CA00140', { publicado: true });
    });
    expect(patchCanalPublicacion).not.toHaveBeenCalled();
    expect(patchCanalPublicacionAprhi).not.toHaveBeenCalled();
  });
});
