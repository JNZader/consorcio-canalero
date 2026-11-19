/**
 * InformeAreaDrawer.test.tsx — the three-step informe de área flow.
 *
 * The api modules, the basins hook, the history-close hook and the workspace
 * breakpoint are mocked at module level; everything else (reducer, layer
 * helpers) runs for real. Behavior-first: stepper gating, the map-click
 * bridge through the real wiring, the Elegir list, the cap alert at 60 zonas,
 * the Revisar preview (online vs trabajo — PR 2: trabajo no longer blocks),
 * and the PR 2 Generar step (nombre + nivel de detalle + create mutation,
 * inline progress, desde_cache instant download, cap/ceiling error surfaces)
 * plus the «Mis informes» panel reachable from the title.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MantineProvider } from '@mantine/core';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { FeatureCollection } from 'geojson';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const elevado = vi.hoisted(() => {
  class FichaApiError extends Error {
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
      this.name = 'FichaApiError';
      this.status = status;
      this.codigo = codigo;
      this.extra = extra;
    }
  }

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

  /** Cuenca "Río Tercero": 61 zonas (para llenar el cupo de 60 y que sobre una). */
  const features = [
    { id: 'z-a1', nombre: 'Alta 1', cuenca: 'Río Tercero' },
    { id: 'z-a2', nombre: 'Alta 2', cuenca: 'Río Tercero' },
    ...Array.from({ length: 59 }, (_, i) => ({
      id: `z-g${String(i + 1).padStart(2, '0')}`,
      nombre: `Generada ${String(i + 1).padStart(2, '0')}`,
      cuenca: 'Río Tercero',
    })),
    { id: 'z-b1', nombre: 'Baja 1', cuenca: 'Arroyo Algodón' },
  ].map((props) => ({
    type: 'Feature' as const,
    properties: props,
    geometry: {
      type: 'Polygon' as const,
      coordinates: [
        [
          [-62, -32],
          [-61, -32],
          [-61, -31],
          [-62, -31],
          [-62, -32],
        ],
      ],
    },
  }));

  const basins: FeatureCollection = { type: 'FeatureCollection', features };

  return {
    FichaApiError,
    InformesAreaApiError,
    fetchZonasPreview: vi.fn(),
    fetchInformeZonas: vi.fn(),
    crearInformeArea: vi.fn(),
    listarInformesArea: vi.fn(),
    descargarInformeAreaPdf: vi.fn(),
    useMapWorkspaceDesktop: vi.fn(() => true),
    basins,
  };
});

vi.mock('../../../src/lib/api/ficha', () => ({
  FichaApiError: elevado.FichaApiError,
  fetchZonasPreview: elevado.fetchZonasPreview,
  fetchInformeZonas: elevado.fetchInformeZonas,
}));

vi.mock('../../../src/lib/api/informesArea', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../src/lib/api/informesArea')>();
  return {
    ...actual,
    InformesAreaApiError: elevado.InformesAreaApiError,
    crearInformeArea: elevado.crearInformeArea,
    listarInformesArea: elevado.listarInformesArea,
    descargarInformeAreaPdf: elevado.descargarInformeAreaPdf,
  };
});

const notificaciones = vi.hoisted(() => ({
  showInfo: vi.fn(),
  showSuccess: vi.fn(),
  showError: vi.fn(),
}));

vi.mock('../../../src/lib/notifications', () => ({
  showInfo: notificaciones.showInfo,
  showSuccess: notificaciones.showSuccess,
  showError: notificaciones.showError,
}));

vi.mock('../../../src/hooks/useBasins', () => ({
  useBasins: vi.fn(() => ({ basins: elevado.basins })),
}));

vi.mock('../../../src/hooks/useDrawerHistoryClose', () => ({
  useDrawerHistoryClose: vi.fn(),
}));

vi.mock('../../../src/components/map2d/MapWorkspace', () => ({
  useMapWorkspaceDesktop: elevado.useMapWorkspaceDesktop,
}));

import { informeAreaPicked } from '../../../src/components/map2d/informeArea/informeAreaLayers';
import { InformeAreaDrawer } from '../../../src/components/map2d/informeArea/InformeAreaDrawer';
import { LIMITE_ZONAS } from '../../../src/components/map2d/informeArea/useSeleccionArea';

function renderDrawer(abierto = true) {
  const onClose = vi.fn();
  const cliente = new QueryClient({
    defaultOptions: { queries: { retry: false, retryDelay: 0 } },
  });
  const envoltura = ({ children }: { children: ReactNode }) => (
    <MantineProvider env="test">
      <QueryClientProvider client={cliente}>{children}</QueryClientProvider>
    </MantineProvider>
  );
  render(<InformeAreaDrawer opened={abierto} onClose={onClose} />, { wrapper: envoltura });
  return { onClose, cliente };
}

const PREVIEW_ONLINE = {
  area_total_ha: 600,
  area_total_ha_geodesica: 601.2,
  subcuencas: [{ id: 'z-a1', nombre: 'Alta 1', cuenca: 'Río Tercero', ha: 600 }],
  fuera_de_subcuencas_ha: 0,
  modo: 'online',
  aviso_cap: false,
} as const;

/** Un informe row del wire (InformesAreaItem) con overrides por test. */
function filaInforme(parciales: Partial<import('../../../src/lib/api/informesArea').InformeAreaItem> = {}) {
  return {
    id: 'inf-1',
    nombre: 'Cuenca norte',
    estado: 'pending' as const,
    progreso: 0,
    desde_cache: false,
    area_ha: null,
    cantidad_zonas: 0,
    error: null,
    vence_at: '2027-02-17T12:00:00Z',
    created_at: '2026-11-18T12:00:00Z',
    updated_at: '2026-11-18T12:00:00Z',
    ...parciales,
  };
}

/** Un pick de mapa pasado por el puente real del módulo. */
function pickEnMapa(id: string, nombre: string, additive = false) {
  act(() => {
    informeAreaPicked({ id, nombre, cuenca: 'Río Tercero' }, additive);
  });
}

const contador = () => screen.getByTestId('informe-area-contador').textContent;

beforeEach(() => {
  elevado.fetchZonasPreview.mockReset();
  elevado.fetchInformeZonas.mockReset();
  elevado.useMapWorkspaceDesktop.mockReset().mockReturnValue(true);
  elevado.crearInformeArea.mockReset();
  elevado.descargarInformeAreaPdf.mockReset().mockResolvedValue(undefined);
  elevado.listarInformesArea.mockReset().mockResolvedValue({ items: [], total: 0 });
  notificaciones.showInfo.mockReset();
  notificaciones.showSuccess.mockReset();
  notificaciones.showError.mockReset();
});

afterEach(() => {
  // El paso Elegir queda desactivado al desmontar; por si un pick quedó a medio
  // camino, apagamos el puente del módulo.
  act(() => {
    informeAreaPicked({ id: 'x', nombre: 'x', cuenca: 'x' }, false);
  });
});

/** Abre el accordion de una cuenca y devuelve su panel (por aria-controls). */
async function abrirCuenca(user: ReturnType<typeof userEvent.setup>, cuenca: RegExp) {
  const control = screen.getByRole('button', { name: cuenca });
  await user.click(control);
  const panel = document.getElementById(control.getAttribute('aria-controls') ?? '');
  expect(panel).not.toBeNull();
  return panel as HTMLElement;
}

describe('InformeAreaDrawer — paso Elegir', () => {
  it('abre en Elegir con el contador en cero y Revisar deshabilitado', () => {
    renderDrawer();

    expect(screen.getByText('Informe de área')).toBeInTheDocument();
    expect(contador()).toBe(`0/${LIMITE_ZONAS} subcuencas`);
    expect(screen.getByRole('button', { name: 'Revisar selección' })).toBeDisabled();
    expect(screen.getByText('Elegir')).toBeInTheDocument();
    expect(screen.getByText('Revisar')).toBeInTheDocument();
    expect(screen.getByText('Generar')).toBeInTheDocument();
    expect(screen.getByTestId('informe-area-chips-vacio')).toBeInTheDocument();
  });

  it('un pick simple del mapa reemplaza la selección; con aditivo suma', () => {
    renderDrawer();

    pickEnMapa('z-a1', 'Alta 1');
    expect(contador()).toBe('1/60 subcuencas');

    pickEnMapa('z-a2', 'Alta 2'); // reemplazar: sigue habiendo una
    expect(contador()).toBe('1/60 subcuencas');
    expect(screen.getAllByTestId('informe-area-chip')).toHaveLength(1);
    expect(screen.getAllByTestId('informe-area-chip')[0]).toHaveTextContent('Alta 2');

    pickEnMapa('z-a1', 'Alta 1', true); // ctrl/⌘: alterna sobre la selección
    expect(contador()).toBe('2/60 subcuencas');

    pickEnMapa('z-a1', 'Alta 1', true); // alternar de nuevo la saca
    expect(contador()).toBe('1/60 subcuencas');
  });

  it('en móvil el switch "Sumar a la selección" vuelve aditivo al pick simple', async () => {
    const user = userEvent.setup();
    elevado.useMapWorkspaceDesktop.mockReturnValue(false);
    renderDrawer();

    await user.click(screen.getByTestId('informe-area-sumar-movil'));

    pickEnMapa('z-a1', 'Alta 1');
    pickEnMapa('z-a2', 'Alta 2'); // con switch: alterna y suma
    expect(contador()).toBe('2/60 subcuencas');

    pickEnMapa('z-a2', 'Alta 2', false); // el switch manda sobre el gesto
    expect(contador()).toBe('1/60 subcuencas');
  });

  it('la lista permite elegir zonas con checkbox y quitar por chip', async () => {
    const user = userEvent.setup();
    renderDrawer();

    await user.click(screen.getByRole('tab', { name: 'Lista' }));
    const region = await abrirCuenca(user, /Río Tercero/);
    await user.click(within(region).getByRole('checkbox', { name: 'Alta 1' }));
    expect(contador()).toBe('1/60 subcuencas');
    expect(screen.getByRole('button', { name: 'Revisar selección' })).toBeEnabled();

    const chip = screen.getAllByTestId('informe-area-chip')[0];
    await user.click(within(chip).getByRole('button', { hidden: true }));
    expect(contador()).toBe('0/60 subcuencas');
    expect(screen.getByRole('button', { name: 'Revisar selección' })).toBeDisabled();
  });

  it('"Toda la cuenca" llena el cupo, avisando el tope y trabando nuevas zonas', async () => {
    const user = userEvent.setup();
    renderDrawer();

    await user.click(screen.getByRole('tab', { name: 'Lista' }));
    const region = await abrirCuenca(user, /Río Tercero/);
    await user.click(within(region).getByRole('checkbox', { name: 'Toda la cuenca' }));

    // 61 zonas en la cuenca: el reducer para en el límite de 60.
    expect(contador()).toBe('60/60 subcuencas');
    expect(screen.getByTestId('informe-area-cupo')).toHaveTextContent(
      `Llegaste al máximo de ${LIMITE_ZONAS} subcuencas`
    );
    // La zona que quedó afuera (y las de otras cuencas) se traban.
    expect(within(region).getByRole('checkbox', { name: 'Generada 59' })).toBeDisabled();

    const algodon = await abrirCuenca(user, /Arroyo Algodón/);
    expect(within(algodon).getByRole('checkbox', { name: 'Baja 1' })).toBeDisabled();

    await user.click(screen.getByRole('button', { name: 'Quitar todas' }));
    expect(contador()).toBe('0/60 subcuencas');
    expect(screen.queryByTestId('informe-area-cupo')).not.toBeInTheDocument();
  });
});

describe('InformeAreaDrawer — paso Revisar', () => {
  it('pide la preview de la selección y muestra el total de la unión', async () => {
    const user = userEvent.setup();
    elevado.fetchZonasPreview.mockResolvedValue({ ...PREVIEW_ONLINE });
    renderDrawer();

    pickEnMapa('z-a1', 'Alta 1');
    await user.click(screen.getByRole('button', { name: 'Revisar selección' }));

    expect(await screen.findByTestId('informe-area-preview')).toBeInTheDocument();
    expect(screen.getByTestId('informe-area-preview-total')).toHaveTextContent(
      '1 subcuenca · 600.0 ha'
    );
    const [pedido] = elevado.fetchZonasPreview.mock.calls[0];
    expect(pedido).toEqual({ zona_ids: ['z-a1'] });

    expect(screen.getByRole('button', { name: 'Generar informe' })).toBeEnabled();
  });

  it('modo trabajo ya no bloquea: el aviso anuncia el camino en segundo plano (PR 2)', async () => {
    const user = userEvent.setup();
    elevado.fetchZonasPreview.mockResolvedValue({
      ...PREVIEW_ONLINE,
      modo: 'trabajo',
      aviso_cap: true,
    });
    renderDrawer();

    pickEnMapa('z-a1', 'Alta 1');
    await user.click(screen.getByRole('button', { name: 'Revisar selección' }));

    expect(await screen.findByTestId('informe-area-preview-cap')).toHaveTextContent('35.000 ha');
    expect(screen.getByTestId('informe-area-preview-cap')).toHaveTextContent(
      'se genera en segundo plano'
    );
    expect(screen.getByRole('button', { name: 'Generar informe' })).toBeEnabled();
  });

  it('un 503 funcionalidad_no_disponible muestra la copia de entorno deshabilitado', async () => {
    const user = userEvent.setup();
    elevado.fetchZonasPreview.mockRejectedValue(
      new elevado.FichaApiError(503, 'funcionalidad_no_disponible', 'detalle del servidor')
    );
    renderDrawer();

    pickEnMapa('z-a1', 'Alta 1');
    await user.click(screen.getByRole('button', { name: 'Revisar selección' }));

    expect(
      await screen.findByText('El informe de área no está habilitado en este entorno.')
    ).toBeInTheDocument();
    expect(screen.queryByText('detalle del servidor')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Generar informe' })).toBeDisabled();
  });
});

describe('InformeAreaDrawer — paso Generar (PR 2: lanzar el informe en segundo plano)', () => {
  async function llegarAGenerar(user: ReturnType<typeof userEvent.setup>) {
    elevado.fetchZonasPreview.mockResolvedValue({ ...PREVIEW_ONLINE });
    renderDrawer();
    pickEnMapa('z-a1', 'Alta 1');
    await user.click(screen.getByRole('button', { name: 'Revisar selección' }));
    await screen.findByTestId('informe-area-preview');
    await user.click(screen.getByRole('button', { name: 'Generar informe' }));
    await screen.findByTestId('informe-area-nombre');
  }

  it('requiere nombre: crear queda deshabilitado hasta escribirlo', async () => {
    const user = userEvent.setup();
    await llegarAGenerar(user);

    expect(screen.getByTestId('informe-area-crear')).toBeDisabled();

    await user.type(screen.getByTestId('informe-area-nombre'), 'Cuenca norte');
    expect(screen.getByTestId('informe-area-crear')).toBeEnabled();
    expect(elevado.crearInformeArea).not.toHaveBeenCalled();
  });

  it('crea con nombre, selección y desglose por defecto; 202 pendiente muestra el progreso inline', async () => {
    const user = userEvent.setup();
    elevado.crearInformeArea.mockResolvedValue(filaInforme({ estado: 'pending', progreso: 0 }));
    elevado.listarInformesArea.mockResolvedValue({
      items: [filaInforme({ estado: 'running', progreso: 40 })],
      total: 1,
    });
    await llegarAGenerar(user);

    await user.type(screen.getByTestId('informe-area-nombre'), 'Cuenca norte');
    await user.click(screen.getByTestId('informe-area-crear'));

    await waitFor(() =>
      expect(elevado.crearInformeArea).toHaveBeenCalledWith({
        nombre: 'Cuenca norte',
        zona_ids: ['z-a1'],
        desglose: true,
      })
    );
    // The list row (polled) wins over the create snapshot → 40 % inline.
    const progreso = await screen.findByTestId('informe-area-progreso-inline');
    expect(progreso).toHaveTextContent('Generando «Cuenca norte»');
    await waitFor(() => expect(progreso).toHaveTextContent('40%'));
    expect(notificaciones.showInfo).toHaveBeenCalledWith(
      'Generando «Cuenca norte»',
      'Te avisamos cuando esté.'
    );
  });

  it('el nivel "Solo total" envía desglose false', async () => {
    const user = userEvent.setup();
    elevado.crearInformeArea.mockResolvedValue(filaInforme());
    await llegarAGenerar(user);

    await user.click(screen.getByRole('radio', { name: 'Solo total' }));
    await user.type(screen.getByTestId('informe-area-nombre'), 'Solo total');
    await user.click(screen.getByTestId('informe-area-crear'));

    await waitFor(() =>
      expect(elevado.crearInformeArea).toHaveBeenCalledWith(
        expect.objectContaining({ desglose: false })
      )
    );
  });

  it('desde_cache: descarga inmediata del PDF y panel listo', async () => {
    const user = userEvent.setup();
    elevado.crearInformeArea.mockResolvedValue(
      filaInforme({
        estado: 'completed',
        progreso: 100,
        desde_cache: true,
        area_ha: 600,
        cantidad_zonas: 1,
      })
    );
    elevado.listarInformesArea.mockResolvedValue({
      items: [
        filaInforme({ estado: 'completed', progreso: 100, desde_cache: true, area_ha: 600, cantidad_zonas: 1 }),
      ],
      total: 1,
    });
    await llegarAGenerar(user);

    await user.type(screen.getByTestId('informe-area-nombre'), 'Cuenca norte');
    await user.click(screen.getByTestId('informe-area-crear'));

    expect(await screen.findByTestId('informe-area-listo-inline')).toHaveTextContent('600.0 ha');
    await waitFor(() =>
      expect(elevado.descargarInformeAreaPdf).toHaveBeenCalledWith('inf-1', 'Cuenca norte')
    );
    expect(notificaciones.showSuccess).toHaveBeenCalledTimes(1);
    expect(notificaciones.showInfo).not.toHaveBeenCalled();
  });

  it('la descarga desde el panel listo pide el PDF de ese informe', async () => {
    const user = userEvent.setup();
    elevado.crearInformeArea.mockResolvedValue(
      filaInforme({ estado: 'completed', progreso: 100, desde_cache: true })
    );
    await llegarAGenerar(user);
    await user.type(screen.getByTestId('informe-area-nombre'), 'Cuenca norte');
    await user.click(screen.getByTestId('informe-area-crear'));
    const listo = await screen.findByTestId('informe-area-listo-inline');

    await user.click(within(listo).getByRole('button', { name: 'Descargar PDF' }));
    await waitFor(() => expect(elevado.descargarInformeAreaPdf).toHaveBeenCalled());
  });

  it('un 422 cap_excedido muestra la copia del tope y no ofrece reintentar', async () => {
    const user = userEvent.setup();
    elevado.crearInformeArea.mockRejectedValue(
      new elevado.InformesAreaApiError(422, 'cap_excedido', 'Se supero el limite de area_ha', {
        cap: 'area_ha',
        limite: 150000,
        valor: 168000,
      })
    );
    await llegarAGenerar(user);

    await user.type(screen.getByTestId('informe-area-nombre'), 'Demasiado grande');
    await user.click(screen.getByTestId('informe-area-crear'));

    expect(await screen.findByTestId('informe-area-crear-error')).toHaveTextContent(
      'supera el tope de 150000.0 ha'
    );
    expect(screen.queryByTestId('informe-area-crear-reintentar')).not.toBeInTheDocument();
  });

  it('un 429 de límite en curso muestra el detalle y ofrece reintentar', async () => {
    const user = userEvent.setup();
    elevado.crearInformeArea
      .mockRejectedValueOnce(
        new elevado.InformesAreaApiError(
          429,
          'limite_informes_en_curso',
          'Ya tenés 3 informes en curso.'
        )
      )
      .mockResolvedValueOnce(filaInforme());
    await llegarAGenerar(user);

    await user.type(screen.getByTestId('informe-area-nombre'), 'El cuarto');
    await user.click(screen.getByTestId('informe-area-crear'));

    expect(await screen.findByTestId('informe-area-crear-error')).toHaveTextContent(
      'Ya tenés 3 informes en curso.'
    );
    await user.click(screen.getByTestId('informe-area-crear-reintentar'));
    await waitFor(() => expect(elevado.crearInformeArea).toHaveBeenCalledTimes(2));
  });

  it('la preview sobre 150.000 ha deshabilita crear con el aviso del tope', async () => {
    const user = userEvent.setup();
    elevado.fetchZonasPreview.mockResolvedValue({
      ...PREVIEW_ONLINE,
      area_total_ha: 150_001,
      modo: 'trabajo',
      aviso_cap: true,
    });
    renderDrawer();
    pickEnMapa('z-a1', 'Alta 1');
    await user.click(screen.getByRole('button', { name: 'Revisar selección' }));
    await screen.findByTestId('informe-area-preview');
    await user.click(screen.getByRole('button', { name: 'Generar informe' }));

    expect(await screen.findByTestId('informe-area-tope')).toHaveTextContent('150000.0 ha');
    await user.type(screen.getByTestId('informe-area-nombre'), 'Grande');
    expect(screen.getByTestId('informe-area-crear')).toBeDisabled();
    expect(elevado.crearInformeArea).not.toHaveBeenCalled();
  });

  it('un informe que falla muestra el motivo guardado y Volver a intentar re-crea', async () => {
    const user = userEvent.setup();
    elevado.fetchZonasPreview.mockResolvedValue({ ...PREVIEW_ONLINE });
    elevado.crearInformeArea.mockResolvedValue(filaInforme({ estado: 'pending' }));
    elevado.listarInformesArea.mockResolvedValue({
      items: [filaInforme({ estado: 'pending' })],
      total: 1,
    });
    const { cliente } = renderDrawer();
    pickEnMapa('z-a1', 'Alta 1');
    await user.click(screen.getByRole('button', { name: 'Revisar selección' }));
    await screen.findByTestId('informe-area-preview');
    await user.click(screen.getByRole('button', { name: 'Generar informe' }));
    await user.type(screen.getByTestId('informe-area-nombre'), 'Cuenca norte');
    await user.click(screen.getByTestId('informe-area-crear'));
    expect(await screen.findByTestId('informe-area-progreso-inline')).toBeInTheDocument();

    // The polled list turns the row failed → the panel flips to the error.
    elevado.listarInformesArea.mockResolvedValue({
      items: [filaInforme({ estado: 'failed', error: 'GEE no disponible' })],
      total: 1,
    });
    await act(async () => {
      await cliente.invalidateQueries({ queryKey: ['informes-area'] });
    });

    const fallo = await screen.findByTestId('informe-area-fallo-inline');
    expect(fallo).toHaveTextContent('GEE no disponible');
    await user.click(within(fallo).getByRole('button', { name: 'Volver a intentar' }));
    await waitFor(() => expect(elevado.crearInformeArea).toHaveBeenCalledTimes(2));
  });

  it('volver a Revisar y a Elegir no pierde el cierre limpio del flujo', async () => {
    const user = userEvent.setup();
    await llegarAGenerar(user);

    await user.click(screen.getByRole('button', { name: 'Volver a revisar' }));
    expect(screen.getByTestId('informe-area-preview')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Volver' }));
    expect(screen.getByTestId('informe-area-elegir')).toBeInTheDocument();
  });
});

describe('InformeAreaDrawer — Mis informes', () => {
  it('el botón del título cambia a la tabla y vuelve al flujo donde estaba', async () => {
    const user = userEvent.setup();
    // Set BEFORE mounting: the drawer mounts the list query on open, and its
    // 30 s staleTime means the panel reads that first answer, not a refetch.
    elevado.fetchZonasPreview.mockResolvedValue({ ...PREVIEW_ONLINE });
    elevado.listarInformesArea.mockResolvedValue({
      items: [filaInforme({ estado: 'completed', nombre: 'Viejo confiable' })],
      total: 1,
    });
    renderDrawer();
    pickEnMapa('z-a1', 'Alta 1');
    await user.click(screen.getByRole('button', { name: 'Revisar selección' }));
    await screen.findByTestId('informe-area-preview');

    await user.click(screen.getByTestId('informe-area-abrir-mis-informes'));

    const panel = await screen.findByTestId('informe-area-panel-mis-informes');
    expect(screen.queryByTestId('informe-area-stepper')).not.toBeInTheDocument();
    expect(await within(panel).findByText('Viejo confiable')).toBeInTheDocument();
    expect(within(panel).getByText('Listo')).toBeInTheDocument();

    await user.click(screen.getByTestId('informe-area-mis-informes-volver'));
    expect(screen.getByTestId('informe-area-stepper')).toBeInTheDocument();
    // El flujo sobrevivió: sigue en Revisar con la selección intacta.
    expect(screen.getByTestId('informe-area-preview')).toBeInTheDocument();
    expect(contador()).toBe('1/60 subcuencas');
  });
});

describe('InformeAreaDrawer — cierre', () => {
  it('cerrar descarta la selección y vuelve al paso Elegir', async () => {
    const user = userEvent.setup();
    const { onClose } = renderDrawer();

    pickEnMapa('z-a1', 'Alta 1');
    await user.click(screen.getByRole('button', { name: 'Cerrar informe de área' }));
    expect(onClose).toHaveBeenCalledTimes(1);

    // Reabrir: el estado del flujo quedó en cero (§6.5).
    await waitFor(() => expect(contador()).toBe(`0/${LIMITE_ZONAS} subcuencas`));
    expect(screen.getByRole('button', { name: 'Revisar selección' })).toBeDisabled();
  });
});
