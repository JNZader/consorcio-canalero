/**
 * VistaPrevia.test.tsx — the Revisar step's geometry-only preview (S1/S5/S6).
 *
 * Behavior-first: loading/error states, the aria-live totals line (union ha +
 * geodesic reference), per-cuenca share rows sorted desc, the 35.000 ha cap
 * Alert (aviso_cap or modo trabajo) and the "fuera de subcuencas" Alert.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { VistaPrevia } from '../../../src/components/map2d/informeArea/VistaPrevia';
import type { FichaZonasPreviewResponse } from '../../../src/lib/api/ficha';

function wrapper({ children }: { children: ReactNode }) {
  return <MantineProvider env="test">{children}</MantineProvider>;
}

function preview(parciales: Partial<FichaZonasPreviewResponse> = {}): FichaZonasPreviewResponse {
  return {
    area_total_ha: 1000,
    area_total_ha_geodesica: 1001.2,
    subcuencas: [
      { id: 'z2', nombre: 'Zona dos', cuenca: 'Arroyo Algodón', ha: 400 },
      { id: 'z1', nombre: 'Zona uno', cuenca: 'Río Tercero', ha: 600 },
    ],
    fuera_de_subcuencas_ha: 0,
    modo: 'online',
    aviso_cap: false,
    ...parciales,
  };
}

describe('VistaPrevia — estados', () => {
  it('cargando muestra el loader y el texto de medición', () => {
    render(<VistaPrevia cargando error={null} datos={null} />, { wrapper });

    expect(screen.getByTestId('informe-area-preview-cargando')).toHaveTextContent(
      'Midiendo la selección…'
    );
    expect(screen.queryByTestId('informe-area-preview')).not.toBeInTheDocument();
  });

  it('error muestra la alerta con la copia que pasó el drawer', () => {
    render(<VistaPrevia cargando={false} error='El informe de área no está habilitado.' datos={null} />, {
      wrapper,
    });

    expect(screen.getByText('No se pudo medir la selección')).toBeInTheDocument();
    expect(screen.getByText('El informe de área no está habilitado.')).toBeInTheDocument();
  });

  it('sin datos ni error cae en la copia genérica', () => {
    render(<VistaPrevia cargando={false} error={null} datos={null} />, { wrapper });

    expect(
      screen.getByText('Revisá la selección e intentá de nuevo.')
    ).toBeInTheDocument();
  });

  it('con onReintentar sugiere volver a Elegir para reintentar', () => {
    render(
      <VistaPrevia cargando={false} error='Sin conexión' datos={null} onReintentar={() => {}} />,
      { wrapper }
    );

    expect(
      screen.getByText(/Podés volver al paso Elegir y volver a entrar a Revisar/)
    ).toBeInTheDocument();
  });
});

describe('VistaPrevia — totales', () => {
  it('anuncia el total dentro de una región aria-live="polite"', () => {
    render(<VistaPrevia cargando={false} error={null} datos={preview()} />, { wrapper });

    const total = screen.getByTestId('informe-area-preview-total');
    expect(total).toHaveTextContent('2 subcuencas · 1000.0 ha');
    expect(total.closest('[aria-live="polite"]')).not.toBeNull();
  });

  it('muestra la referencia geodésica WGS84 al lado del total planimétrico', () => {
    render(<VistaPrevia cargando={false} error={null} datos={preview()} />, { wrapper });

    expect(screen.getByText(/referencia geodésica WGS84: 1001\.2 ha/)).toBeInTheDocument();
  });

  it('usa el singular para una sola subcuenca', () => {
    const datos = preview({
      subcuencas: [{ id: 'z1', nombre: 'Zona uno', cuenca: 'Río Tercero', ha: 600 }],
      area_total_ha: 600,
      area_total_ha_geodesica: 601,
    });
    render(<VistaPrevia cargando={false} error={null} datos={datos} />, { wrapper });

    expect(screen.getByTestId('informe-area-preview-total')).toHaveTextContent(
      '1 subcuenca · 600.0 ha'
    );
  });
});

describe('VistaPrevia — avisos', () => {
  it('aviso_cap en línea muestra la alerta del tope de 35.000 ha', () => {
    render(<VistaPrevia cargando={false} error={null} datos={preview({ aviso_cap: true })} />, {
      wrapper,
    });

    const alerta = screen.getByTestId('informe-area-preview-cap');
    expect(alerta).toHaveTextContent('Selección grande');
    expect(alerta).toHaveTextContent('35.000 ha');
    expect(alerta).toHaveTextContent('se genera en segundo plano');
  });

  it('modo trabajo muestra la misma alerta aunque aviso_cap llegue en false', () => {
    render(
      <VistaPrevia cargando={false} error={null} datos={preview({ modo: 'trabajo' })} />,
      { wrapper }
    );

    expect(screen.getByTestId('informe-area-preview-cap')).toBeInTheDocument();
  });

  it('sin cap ni modo trabajo no renderiza la alerta del tope', () => {
    render(<VistaPrevia cargando={false} error={null} datos={preview()} />, { wrapper });

    expect(screen.queryByTestId('informe-area-preview-cap')).not.toBeInTheDocument();
  });

  it('fuera_de_subcuencas > 0.01 anuncia las hectáreas fuera', () => {
    render(
      <VistaPrevia cargando={false} error={null} datos={preview({ fuera_de_subcuencas_ha: 12.5 })} />,
      { wrapper }
    );

    expect(screen.getByTestId('informe-area-preview-fuera')).toHaveTextContent(
      'Partes fuera de subcuencas'
    );
    expect(screen.getByTestId('informe-area-preview-fuera')).toHaveTextContent(
      '12.5 ha de la selección quedan fuera'
    );
  });

  it('fuera_de_subcuencas despreciable no muestra la alerta', () => {
    render(
      <VistaPrevia cargando={false} error={null} datos={preview({ fuera_de_subcuencas_ha: 0.005 })} />,
      { wrapper }
    );

    expect(screen.queryByTestId('informe-area-preview-fuera')).not.toBeInTheDocument();
  });
});

describe('VistaPrevia — reparto por cuenca', () => {
  it('ordena las cuencas por hectáreas descendente con su porcentaje', () => {
    render(<VistaPrevia cargando={false} error={null} datos={preview()} />, { wrapper });

    const renglones = screen.getAllByTestId('informe-area-preview-cuenca');
    expect(renglones).toHaveLength(2);

    const primera = within(renglones[0]);
    expect(primera.getByText('Río Tercero')).toBeInTheDocument();
    expect(primera.getByText('600.0 ha · 60.0%')).toBeInTheDocument();

    const segunda = within(renglones[1]);
    expect(segunda.getByText('Arroyo Algodón')).toBeInTheDocument();
    expect(segunda.getByText('400.0 ha · 40.0%')).toBeInTheDocument();
  });

  it('sin subcuencas no renderiza renglones de cuenca', () => {
    const datos = preview({
      subcuencas: [],
      area_total_ha: 0,
      area_total_ha_geodesica: 0,
    });
    render(<VistaPrevia cargando={false} error={null} datos={datos} />, { wrapper });

    expect(screen.queryByTestId('informe-area-preview-cuenca')).not.toBeInTheDocument();
  });
});
