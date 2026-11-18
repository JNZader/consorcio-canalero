/**
 * InformeAreaDrawer.test.tsx — the three-step informe de área flow.
 *
 * The api module, the basins hook, the history-close hook and the workspace
 * breakpoint are mocked at module level; everything else (reducer, layer
 * helpers, reused ficha components) runs for real. Behavior-first: stepper
 * gating, the map-click bridge through the real wiring, the Elegir list, the
 * cap alert at 60 zonas, the Revisar preview (online vs trabajo), the Generar
 * happy path through the reused dataset components, and the error surface
 * (503 disabled copy, retryable 429 with Reintentar, terminal statuses
 * without retry).
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
    fetchZonasPreview: vi.fn(),
    fetchInformeZonas: vi.fn(),
    useMapWorkspaceDesktop: vi.fn(() => true),
    basins,
  };
});

vi.mock('../../../src/lib/api/ficha', () => ({
  FichaApiError: elevado.FichaApiError,
  fetchZonasPreview: elevado.fetchZonasPreview,
  fetchInformeZonas: elevado.fetchInformeZonas,
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

function wrapper({ children }: { children: ReactNode }) {
  const cliente = new QueryClient({
    defaultOptions: { queries: { retryDelay: 0 } },
  });
  return (
    <MantineProvider env="test">
      <QueryClientProvider client={cliente}>{children}</QueryClientProvider>
    </MantineProvider>
  );
}

const PREVIEW_ONLINE = {
  area_total_ha: 600,
  area_total_ha_geodesica: 601.2,
  subcuencas: [{ id: 'z-a1', nombre: 'Alta 1', cuenca: 'Río Tercero', ha: 600 }],
  fuera_de_subcuencas_ha: 0,
  modo: 'online',
  aviso_cap: false,
} as const;

const FICHA = {
  tipo: 'zonas',
  area_ha: 600,
  suelos: {
    cobertura: 'total',
    clases: [{ clase: 'II', ha: 600, pct: 100 }],
    pixel_count: 6000,
    low_confidence: false,
    cobertura_ratio: 1,
  },
  flood_risk: {
    cobertura: 'total',
    clases: [{ clase: 'alto', ha: 600, pct: 100 }],
    pixel_count: 6000,
    low_confidence: false,
    cobertura_ratio: 1,
  },
  drainage_need: {
    cobertura: 'total',
    clases: [{ clase: 'medio', ha: 600, pct: 100 }],
    pixel_count: 6000,
    low_confidence: false,
    cobertura_ratio: 1,
  },
  precipitacion_mensual: {
    cobertura: 'total',
    low_confidence: false,
    pixel_count: 6000,
    cobertura_ratio: 1,
    unidad: 'mm',
    fuente: 'CHIRPS',
    periodo: '1991-2020',
    serie: [
      { mes: 1, mm: 120 },
      { mes: 2, mm: 95 },
    ],
    anual_mm: 900,
  },
  desglose_por_subcuenca: [
    {
      zona_id: 'z-a1',
      nombre: 'Alta 1',
      ha: 600,
      pct_alto_critico: 12.5,
      clase_suelo_dominante: 'IIe',
      lluvia_anual_mm: 850,
    },
  ],
  umbral_alto_critico: 'legacy70',
} as const;

function renderDrawer(abierto = true) {
  const onClose = vi.fn();
  render(<InformeAreaDrawer opened={abierto} onClose={onClose} />, { wrapper });
  return { onClose };
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

  it('modo trabajo bloquea Generar con el aviso del tope de 35.000 ha', async () => {
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
    expect(screen.getByRole('button', { name: 'Generar informe' })).toBeDisabled();
    expect(elevado.fetchInformeZonas).not.toHaveBeenCalled();
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

describe('InformeAreaDrawer — paso Generar', () => {
  async function llegarAGenerar(user: ReturnType<typeof userEvent.setup>) {
    elevado.fetchZonasPreview.mockResolvedValue({ ...PREVIEW_ONLINE });
    renderDrawer();
    pickEnMapa('z-a1', 'Alta 1');
    await user.click(screen.getByRole('button', { name: 'Revisar selección' }));
    await screen.findByTestId('informe-area-preview');
    await user.click(screen.getByRole('button', { name: 'Generar informe' }));
  }

  it('genera el informe con los componentes de ficha reutilizados y el desglose', async () => {
    const user = userEvent.setup();
    elevado.fetchInformeZonas.mockResolvedValue({ ...FICHA });
    await llegarAGenerar(user);

    expect(await screen.findByTestId('informe-area-informe-total')).toHaveTextContent(
      '1 subcuenca · 600.0 ha'
    );
    expect(elevado.fetchInformeZonas.mock.calls[0][0]).toEqual(['z-a1']);

    // FichaResumen (reutilizado) + coberturas por capa + tabs de dataset.
    expect(screen.getByText(/Superficie analizada:/)).toBeInTheDocument();
    expect(screen.getByText('Riesgo de inundación')).toBeInTheDocument();
    expect(screen.getByText('Necesidad de drenaje')).toBeInTheDocument();
    expect(screen.getAllByText('100.0%').length).toBeGreaterThanOrEqual(3);

    // Desglose por subcuenca con la nota del umbral legacy70.
    const desglose = screen.getByTestId('informe-area-desglose');
    expect(within(desglose).getByText('Alta 1')).toBeInTheDocument();
    expect(within(desglose).getByText(/usa el umbral histórico guardado/)).toBeInTheDocument();

    // Cambiar de pestaña de dataset renderiza los bins de riesgo.
    await user.click(screen.getByRole('radio', { name: 'Riesgo' }));
    expect(screen.getByTestId('informe-area-flood-risk')).toBeInTheDocument();
  });

  it('la pestaña Lluvia carga el gráfico diferido con el total anual', async () => {
    const user = userEvent.setup();
    elevado.fetchInformeZonas.mockResolvedValue({ ...FICHA });
    await llegarAGenerar(user);
    await screen.findByTestId('informe-area-informe-total');

    await user.click(screen.getByRole('radio', { name: 'Lluvia' }));
    expect(await screen.findByTestId('precip-anual')).toBeInTheDocument();
  });

  it('un 429 reintenable muestra Reintentar y el clic recupera el informe', async () => {
    const user = userEvent.setup();
    const error = new elevado.FichaApiError(429, 'limite_de_pedidos', 'Demasiados pedidos');
    elevado.fetchInformeZonas
      .mockRejectedValueOnce(error)
      .mockRejectedValueOnce(error) // el retry interno de la query
      .mockResolvedValueOnce({ ...FICHA });
    await llegarAGenerar(user);

    expect(await screen.findByText('No se pudo generar el informe')).toBeInTheDocument();
    expect(screen.getByText('Demasiados pedidos')).toBeInTheDocument();
    const reintentar = screen.getByTestId('informe-area-reintentar');

    await user.click(reintentar);
    expect(await screen.findByTestId('informe-area-informe-total')).toBeInTheDocument();
  });

  it.each([404, 413, 422])(
    'un error terminal %i no ofrece Reintentar',
    async (status) => {
      const user = userEvent.setup();
      elevado.fetchInformeZonas.mockRejectedValue(
        new elevado.FichaApiError(status, 'error_x', `detalle ${status}`)
      );
      await llegarAGenerar(user);

      expect(await screen.findByText(`detalle ${status}`)).toBeInTheDocument();
      expect(screen.queryByTestId('informe-area-reintentar')).not.toBeInTheDocument();
    }
  );

  it('el 503 de la ficha muestra la copia de entorno deshabilitado sin reintento', async () => {
    const user = userEvent.setup();
    elevado.fetchInformeZonas.mockRejectedValue(
      new elevado.FichaApiError(503, 'funcionalidad_no_disponible', 'detalle del servidor')
    );
    await llegarAGenerar(user);

    expect(
      await screen.findByText('El informe de área no está habilitado en este entorno.')
    ).toBeInTheDocument();
    expect(screen.queryByTestId('informe-area-reintentar')).not.toBeInTheDocument();
  });

  it('volver a Revisar y a Elegir no pierde el cierre limpio del flujo', async () => {
    const user = userEvent.setup();
    elevado.fetchInformeZonas.mockResolvedValue({ ...FICHA });
    await llegarAGenerar(user);
    await screen.findByTestId('informe-area-informe-total');

    await user.click(screen.getByRole('button', { name: 'Volver a revisar' }));
    expect(screen.getByTestId('informe-area-preview')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Volver' }));
    expect(screen.getByTestId('informe-area-elegir')).toBeInTheDocument();
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
