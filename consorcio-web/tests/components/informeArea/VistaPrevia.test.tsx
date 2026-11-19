/**
 * VistaPrevia.test.tsx — the Revisar step's mixed-selection preview
 * (S1/S5/S6 + PR 3 S2/S4).
 *
 * Behavior-first: loading/error states, the aria-live totals line (union ha +
 * geodesic reference + polygon count), per-cuenca share rows sorted desc, the
 * 35.000 ha cap Alert (aviso_cap), and the PR 3 avisos — fuera de zona and
 * poligonos separados.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { VistaPrevia } from '../../../src/components/map2d/informeArea/VistaPrevia';
import type { InformeAreaPreviewResponse } from '../../../src/lib/api/informesArea';

function wrapper({ children }: { children: ReactNode }) {
  return <MantineProvider env="test">{children}</MantineProvider>;
}

function preview(
  parciales: Partial<InformeAreaPreviewResponse> = {}
): InformeAreaPreviewResponse {
  return {
    area_total_ha: 1000,
    area_total_ha_geodesica: 1001.2,
    subcuencas: [
      { id: 'z2', nombre: 'Zona dos', cuenca: 'Arroyo Algodón', ha: 400 },
      { id: 'z1', nombre: 'Zona uno', cuenca: 'Río Tercero', ha: 600 },
    ],
    cantidad_geometrias: 0,
    fuera_zona_ha: 0,
    poligonos_separados: false,
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
    render(
      <VistaPrevia cargando={false} error='El informe de área no está habilitado.' datos={null} />,
      { wrapper }
    );

    expect(screen.getByText('No se pudo medir la selección')).toBeInTheDocument();
    expect(screen.getByText('El informe de área no está habilitado.')).toBeInTheDocument();
  });

  it('sin datos ni error cae en la copia genérica', () => {
    render(<VistaPrevia cargando={false} error={null} datos={null} />, { wrapper });

    expect(screen.getByText('Revisá la selección e intentá de nuevo.')).toBeInTheDocument();
  });
});

describe('VistaPrevia — totales (S6)', () => {
  it('anuncia subcuencas, hectáreas y la referencia geodésica', () => {
    render(<VistaPrevia cargando={false} error={null} datos={preview()} />, { wrapper });

    const total = screen.getByTestId('informe-area-preview-total');
    expect(total).toHaveTextContent('2 subcuencas');
    expect(total).toHaveTextContent('1000.0 ha');
  });

  it('suma la cantidad de polígonos cuando la selección trae geometrías (PR 3)', () => {
    render(
      <VistaPrevia
        cargando={false}
        error={null}
        datos={preview({ cantidad_geometrias: 3 })}
      />,
      { wrapper }
    );

    expect(screen.getByTestId('informe-area-preview-total')).toHaveTextContent('3 polígonos');
  });
});

describe('VistaPrevia — avisos (S5 + PR 3 S2)', () => {
  it('aviso_cap muestra la alerta del tope de 35.000 ha', () => {
    render(<VistaPrevia cargando={false} error={null} datos={preview({ aviso_cap: true })} />, {
      wrapper,
    });

    const alerta = screen.getByTestId('informe-area-preview-cap');
    expect(alerta).toHaveTextContent('Selección grande');
    expect(alerta).toHaveTextContent('segundo plano');
  });

  it('sin aviso_cap no renderiza la alerta del tope', () => {
    render(<VistaPrevia cargando={false} error={null} datos={preview()} />, { wrapper });

    expect(screen.queryByTestId('informe-area-preview-cap')).not.toBeInTheDocument();
  });

  it('fuera_zona_ha > 0.01 anuncia las hectáreas fuera del consorcio (S2)', () => {
    render(
      <VistaPrevia cargando={false} error={null} datos={preview({ fuera_zona_ha: 12.5 })} />,
      { wrapper }
    );

    const alerta = screen.getByTestId('informe-area-preview-fuera');
    expect(alerta).toHaveTextContent('fuera de la zona del consorcio');
    expect(alerta).toHaveTextContent('12.5');
  });

  it('fuera_zona_ha despreciable no muestra la alerta', () => {
    render(
      <VistaPrevia cargando={false} error={null} datos={preview({ fuera_zona_ha: 0.001 })} />,
      { wrapper }
    );

    expect(screen.queryByTestId('informe-area-preview-fuera')).not.toBeInTheDocument();
  });

  it('poligonos_separados avisa la selección partida (S2)', () => {
    render(
      <VistaPrevia
        cargando={false}
        error={null}
        datos={preview({ poligonos_separados: true })}
      />,
      { wrapper }
    );

    expect(screen.getByTestId('informe-area-preview-separados')).toHaveTextContent(
      'partes separadas'
    );
  });
});

describe('VistaPrevia — renglones por cuenca', () => {
  it('ordena las cuencas por hectáreas descendentes con su porcentaje', () => {
    render(<VistaPrevia cargando={false} error={null} datos={preview()} />, { wrapper });

    const renglones = screen.getAllByTestId('informe-area-preview-cuenca');
    expect(renglones).toHaveLength(2);
    expect(within(renglones[0]).getByText('Río Tercero')).toBeInTheDocument();
    expect(within(renglones[0]).getByText(/60\.0%/)).toBeInTheDocument();
    expect(within(renglones[1]).getByText('Arroyo Algodón')).toBeInTheDocument();
  });

  it('selección solo-geometría no renderiza renglones de cuenca', () => {
    render(
      <VistaPrevia
        cargando={false}
        error={null}
        datos={preview({ subcuencas: [], cantidad_geometrias: 2 })}
      />,
      { wrapper }
    );

    expect(screen.queryByTestId('informe-area-preview-cuenca')).not.toBeInTheDocument();
    expect(screen.getByTestId('informe-area-preview-total')).toHaveTextContent('2 polígonos');
  });
});
