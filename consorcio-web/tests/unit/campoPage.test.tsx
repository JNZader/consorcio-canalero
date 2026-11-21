/**
 * CampoPage tests (W-INF-06): verifies GPS fix before map load paints once load fires,
 * revoked links fail cleanly without offline fallback, and cache quota/notas surface on UI.
 */

import { act, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import CampoPage from '@/components/campo/CampoPage';
import { CampoRevocadoError } from '@/components/campo/campoCache';
import type { PaqueteCampo } from '@/components/campo/tiposCampo';

const mocks = vi.hoisted(() => ({
  cargarPaqueteCampo: vi.fn(),
  gpsSetData: vi.fn(),
  tapSetData: vi.fn(),
  fitBounds: vi.fn(),
  loadListeners: [] as Array<() => void>,
}));

vi.mock('@/components/campo/campoCache', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/campo/campoCache')>();
  return {
    ...actual,
    cargarPaqueteCampo: mocks.cargarPaqueteCampo,
  };
});

vi.mock('@/lib/maplibreLoader', () => ({
  loadMapLibre: vi.fn(async () => ({
    Map: class FakeMap {
      on(event: string, cb: () => void) {
        if (event === 'load') mocks.loadListeners.push(cb);
      }
      fitBounds(...args: unknown[]) {
        mocks.fitBounds(...args);
      }
      getLayer() {
        return true;
      }
      setLayoutProperty() {}
      getSource(name: string) {
        if (name === 'gps') return { setData: mocks.gpsSetData };
        if (name === 'tap') return { setData: mocks.tapSetData };
        return undefined;
      }
      isStyleLoaded() {
        return true;
      }
      getZoom() {
        return 12;
      }
      easeTo() {}
      remove() {}
    },
  })),
}));

const PAQUETE: PaqueteCampo = {
  version: 1,
  nombre: 'Informe campo test',
  generado_el: '2026-11-20T12:00:00Z',
  area_ha: 100,
  limites: {
    seleccion: {
      type: 'Polygon',
      coordinates: [
        [
          [-61.91, -33.01],
          [-61.88, -33.01],
          [-61.88, -33.0],
          [-61.91, -33.0],
          [-61.91, -33.01],
        ],
      ],
    },
    subcuencas: [],
  },
  temas: {
    riesgo: {
      titulo: 'Riesgo hídrico',
      clases: [
        {
          clase: 'Bajo',
          color: '#1a9850',
          geometrias: [
            {
              type: 'Polygon',
              coordinates: [
                [
                  [-61.91, -33.01],
                  [-61.88, -33.01],
                  [-61.88, -33.0],
                  [-61.91, -33.0],
                  [-61.91, -33.01],
                ],
              ],
            },
          ],
        },
      ],
    },
  },
  basemap: null,
  notas: ['Cota verificada en campo'],
};

beforeEach(() => {
  mocks.cargarPaqueteCampo.mockReset();
  mocks.gpsSetData.mockReset();
  mocks.tapSetData.mockReset();
  mocks.fitBounds.mockReset();
  mocks.loadListeners = [];
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('CampoPage', () => {
  it('pinta el punto azul aunque el fix GPS llegue antes de map.on("load") y muestra notas/avisoCache', async () => {
    mocks.cargarPaqueteCampo.mockResolvedValue({
      paquete: PAQUETE,
      desdeCache: false,
      avisoCache: 'No hay espacio suficiente para guardar el mapa sin señal.',
    });

    vi.spyOn(navigator.geolocation, 'watchPosition').mockImplementation((onSuccess) => {
      onSuccess({
        coords: {
          longitude: -61.905,
          latitude: -33.005,
          accuracy: 25,
          altitude: null,
          altitudeAccuracy: null,
          heading: null,
          speed: null,
          toJSON: () => ({}),
        },
        timestamp: Date.now(),
        toJSON: () => ({}),
      });
      return 1;
    });
    vi.spyOn(navigator.geolocation, 'clearWatch').mockImplementation(() => {});

    render(<CampoPage token="tok-1" />);

    await waitFor(() => expect(mocks.loadListeners.length).toBeGreaterThan(0));
    expect(mocks.gpsSetData).not.toHaveBeenCalled();

    act(() => {
      for (const cb of mocks.loadListeners) cb();
    });

    await waitFor(() => expect(mocks.gpsSetData).toHaveBeenCalled());
    const payload = mocks.gpsSetData.mock.calls.at(-1)?.[0] as GeoJSON.FeatureCollection;
    expect(payload.features.map((f) => f.properties?.tipo)).toEqual(['precision', 'punto']);

    expect(screen.getByTestId('campo-aviso-cache')).toHaveTextContent('espacio suficiente');
    expect(screen.getByTestId('campo-notas')).toHaveTextContent('Cota verificada en campo');
  });

  it('enlace revocado (404/410) muestra error claro de enlace vencido o eliminado', async () => {
    mocks.cargarPaqueteCampo.mockRejectedValue(new CampoRevocadoError(404));
    vi.spyOn(navigator.geolocation, 'watchPosition').mockReturnValue(1);
    vi.spyOn(navigator.geolocation, 'clearWatch').mockImplementation(() => {});

    render(<CampoPage token="tok-muerto" />);

    const err = await screen.findByTestId('campo-error');
    expect(err).toHaveTextContent('Este enlace de campo venció o fue eliminado.');
  });
});
