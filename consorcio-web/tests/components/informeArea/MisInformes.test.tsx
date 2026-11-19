/**
 * MisInformes.test.tsx — the «Mis informes» table (PR 2, S2/S8).
 *
 * Behavior-first, the api module mocked at module level (vi.hoisted error
 * class, the InformeAreaDrawer.test.tsx pattern): one row per informe with
 * its estado Badge, hectares (dash while unknown — never a fabricated 0),
 * polled progreso and es-AR date; the download button enabled ONLY on
 * `completed` (the PDF endpoint answers 409 until the bytes exist); the
 * failed row surfaces the stored readable reason; plus the empty, loading
 * and list-error states.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MantineProvider } from '@mantine/core';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { InformeAreaItem } from '../../../src/lib/api/informesArea';

const elevado = vi.hoisted(() => {
  class InformesAreaApiError extends Error {
    readonly status: number;
    readonly codigo: string;
    readonly extra: Record<string, unknown>;
    constructor(
      status: number,
      codigo: string,
      detail: string,
      extra: Record<string, unknown> = {}
    ) {
      super(detail);
      this.name = 'InformesAreaApiError';
      this.status = status;
      this.codigo = codigo;
      this.extra = extra;
    }
  }
  return {
    InformesAreaApiError,
    listarInformesArea: vi.fn(),
    descargarInformeAreaPdf: vi.fn(),
  };
});

vi.mock('../../../src/lib/api/informesArea', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../src/lib/api/informesArea')>();
  return {
    ...actual,
    InformesAreaApiError: elevado.InformesAreaApiError,
    listarInformesArea: elevado.listarInformesArea,
    descargarInformeAreaPdf: elevado.descargarInformeAreaPdf,
  };
});

vi.mock('../../../src/lib/notifications', () => ({
  showInfo: vi.fn(),
  showSuccess: vi.fn(),
  showError: vi.fn(),
}));

import { MisInformes } from '../../../src/components/map2d/informeArea/MisInformes';

function wrapper({ children }: { children: ReactNode }) {
  const cliente = new QueryClient({
    defaultOptions: { queries: { retry: false, retryDelay: 0 }, mutations: { retry: false } },
  });
  return (
    <MantineProvider env="test">
      <QueryClientProvider client={cliente}>{children}</QueryClientProvider>
    </MantineProvider>
  );
}

function fila(parciales: Partial<InformeAreaItem> = {}): InformeAreaItem {
  return {
    id: 'id-' + Math.random().toString(36).slice(2, 8),
    nombre: 'Cuenca norte',
    estado: 'completed',
    progreso: 100,
    desde_cache: false,
    area_ha: 1234.5,
    cantidad_zonas: 4,
    error: null,
    vence_at: '2027-02-17T12:00:00Z',
    created_at: '2026-11-01T12:00:00Z',
    updated_at: '2026-11-01T12:05:00Z',
    ...parciales,
  };
}

function filaFija(id: string, parciales: Partial<InformeAreaItem> = {}): InformeAreaItem {
  return fila({ id, ...parciales });
}

const FILAS: InformeAreaItem[] = [
  filaFija('listo', { nombre: 'Cuenca norte', estado: 'completed', progreso: 100 }),
  filaFija('corriendo', {
    nombre: 'Informe en curso',
    estado: 'running',
    progreso: 40,
    area_ha: null,
    error: null,
  }),
  filaFija('cola', { nombre: 'En cola', estado: 'pending', progreso: 0, area_ha: null }),
  filaFija('roto', {
    nombre: 'Intento fallido',
    estado: 'failed',
    progreso: 30,
    area_ha: null,
    error: 'GEE no disponible',
  }),
];

beforeEach(() => {
  elevado.listarInformesArea.mockReset().mockResolvedValue({ items: FILAS, total: FILAS.length });
  elevado.descargarInformeAreaPdf.mockReset().mockResolvedValue(undefined);
});

afterEach(() => {
  vi.clearAllMocks();
});

/** Row lookup by nombre (unique per fixture row) — ids are not rendered. */
function filaPorNombre(nombre: string): HTMLElement {
  return screen
    .getAllByTestId('informe-area-mis-informes-fila')
    .find((nodo) => within(nodo).queryByText(nombre) !== null) as HTMLElement;
}

describe('MisInformes — filas', () => {
  it('renderiza una fila por informe con badge, ha, progreso y fecha es-AR', async () => {
    render(<MisInformes />, { wrapper });

    expect(await screen.findByTestId('informe-area-mis-informes')).toBeInTheDocument();
    expect(screen.getAllByTestId('informe-area-mis-informes-fila')).toHaveLength(4);

    const lista = filaPorNombre('Cuenca norte');
    expect(within(lista).getByText('Listo')).toBeInTheDocument();
    expect(within(lista).getByText('1234.5 ha')).toBeInTheDocument();
    expect(within(lista).getByText('01/11/2026')).toBeInTheDocument();
    expect(within(lista).getByText('100%')).toBeInTheDocument();

    // ha unknown while the job runs — a dash, never a fabricated 0.
    const corriendo = filaPorNombre('Informe en curso');
    expect(within(corriendo).getByText('Generando')).toBeInTheDocument();
    expect(within(corriendo).getByText('—')).toBeInTheDocument();
    expect(within(corriendo).getByText('40%')).toBeInTheDocument();

    expect(within(filaPorNombre('En cola')).getByText('Pendiente')).toBeInTheDocument();
    expect(within(filaPorNombre('Intento fallido')).getByText('Falló')).toBeInTheDocument();
  });

  it('la fila fallida muestra el motivo legible que guardó la tarea (S8)', async () => {
    render(<MisInformes />, { wrapper });

    const roto = await waitFor(() => filaPorNombre('Intento fallido'));
    expect(within(roto).getByText('GEE no disponible')).toBeInTheDocument();
  });

  it('el botón de descarga sólo se habilita en completed; en curso queda esperando', async () => {
    render(<MisInformes />, { wrapper });
    await screen.findByTestId('informe-area-mis-informes');

    expect(within(filaPorNombre('Cuenca norte')).getByRole('button', { name: /Descargar el PDF de Cuenca norte/ })).toBeEnabled();
    expect(within(filaPorNombre('Informe en curso')).getByRole('button', { name: /Informe en curso/ })).toBeDisabled();
    expect(within(filaPorNombre('En cola')).getByRole('button', { name: /En cola/ })).toBeDisabled();
    expect(within(filaPorNombre('Intento fallido')).getByRole('button', { name: /Intento fallido/ })).toBeDisabled();
  });

  it('descargar pide el PDF con el id y el nombre de la fila', async () => {
    const user = userEvent.setup();
    render(<MisInformes />, { wrapper });
    await screen.findByTestId('informe-area-mis-informes');

    await user.click(
      within(filaPorNombre('Cuenca norte')).getByRole('button', { name: /Descargar el PDF de Cuenca norte/ })
    );

    await waitFor(() =>
      expect(elevado.descargarInformeAreaPdf).toHaveBeenCalledWith('listo', 'Cuenca norte')
    );
  });
});

describe('MisInformes — estados de la lista', () => {
  it('vacía: copia de estado vacío que guía al primer informe', async () => {
    elevado.listarInformesArea.mockResolvedValue({ items: [], total: 0 });
    render(<MisInformes />, { wrapper });

    const vacio = await screen.findByTestId('informe-area-mis-informes-vacio');
    expect(vacio).toHaveTextContent('Todavía no generaste informes.');
    expect(screen.queryByTestId('informe-area-mis-informes-fila')).not.toBeInTheDocument();
  });

  it('cargando: loader con texto mientras llega la primera tanda', () => {
    elevado.listarInformesArea.mockReturnValue(new Promise(() => {}));
    render(<MisInformes />, { wrapper });

    expect(screen.getByTestId('informe-area-mis-informes-cargando')).toHaveTextContent(
      'Cargando tus informes…'
    );
  });

  it('error de lista: alerta con Reintentar que recupera la tabla', async () => {
    const user = userEvent.setup();
    const fallo = new elevado.InformesAreaApiError(500, 'error_desconocido', 'El servidor no respondió');
    elevado.listarInformesArea
      .mockRejectedValueOnce(fallo)
      .mockRejectedValueOnce(fallo) // the query's own single retry (non-terminal 500)
      .mockResolvedValue({ items: [FILAS[0]], total: 1 });
    render(<MisInformes />, { wrapper });

    expect(await screen.findByText('No se pudo cargar tus informes')).toBeInTheDocument();
    expect(screen.getByText('El servidor no respondió')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Reintentar' }));
    expect(await screen.findByTestId('informe-area-mis-informes-fila')).toBeInTheDocument();
  });

  it('un rechazo terminal (401) no ofrece Reintentar', async () => {
    elevado.listarInformesArea.mockRejectedValue(
      new elevado.InformesAreaApiError(401, 'no_autenticado', 'Iniciá sesión')
    );
    render(<MisInformes />, { wrapper });

    expect(await screen.findByText('No se pudo cargar tus informes')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Reintentar' })).not.toBeInTheDocument();
  });
});
