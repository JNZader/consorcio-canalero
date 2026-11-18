/**
 * DesgloseTabla.test.tsx — the per-subcuenca breakdown of the Generar step
 * (S1/S6/S8).
 *
 * Behavior-first: one row per zona with the stored figures, an em dash for
 * null cells (never a fabricated zero), sort toggles per column header with
 * aria-sort, nulls sorting last in ascending order, and the legacy70
 * threshold note.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { DesgloseTabla } from '../../../src/components/map2d/informeArea/DesgloseTabla';
import type { FichaDesgloseSubcuenca } from '../../../src/lib/api/ficha';

function wrapper({ children }: { children: ReactNode }) {
  return <MantineProvider env="test">{children}</MantineProvider>;
}

/** Nombres desordenados: el orden por defecto (nombre asc) tiene que ordenarlos. */
const FILAS: FichaDesgloseSubcuenca[] = [
  {
    zona_id: 'z3',
    nombre: 'Cañada de la Leche',
    ha: 250.75,
    pct_alto_critico: null,
    clase_suelo_dominante: null,
    lluvia_anual_mm: null,
  },
  {
    zona_id: 'z1',
    nombre: 'Alta 1',
    ha: 600,
    pct_alto_critico: 12.5,
    clase_suelo_dominante: 'IIe',
    lluvia_anual_mm: 850,
  },
  {
    zona_id: 'z2',
    nombre: 'Baja 1',
    ha: 400,
    pct_alto_critico: 3.2,
    clase_suelo_dominante: 'IVws',
    lluvia_anual_mm: 720,
  },
];

function nombresDeFilas(): string[] {
  return screen
    .getAllByRole('row')
    .slice(1) // la primera fila es el encabezado
    .map((fila) => within(fila).getAllByRole('cell')[0]?.textContent ?? '');
}

function renderTabla(filas: readonly FichaDesgloseSubcuenca[] = FILAS, umbral?: 'legacy70' | null) {
  render(<DesgloseTabla filas={filas} umbral={umbral} />, { wrapper });
}

describe('DesgloseTabla — render', () => {
  it('muestra una fila por zona con las cifras guardadas', () => {
    renderTabla();

    expect(nombresDeFilas()).toEqual(['Alta 1', 'Baja 1', 'Cañada de la Leche']);

    const filaAlta1 = screen.getByText('Alta 1').closest('tr');
    expect(filaAlta1).not.toBeNull();
    const celdas = within(filaAlta1 as HTMLElement).getAllByRole('cell');
    expect(celdas[1]).toHaveTextContent('600.0 ha');
    expect(celdas[2]).toHaveTextContent('12.5%');
    expect(celdas[3]).toHaveTextContent('IIe');
    expect(celdas[4]).toHaveTextContent('850 mm');
  });

  it('las celdas sin cifra guardada son un guion, nunca un cero fabricado', () => {
    renderTabla();

    const filaSinCifras = screen.getByText('Cañada de la Leche').closest('tr');
    expect(filaSinCifras).not.toBeNull();
    const celdas = within(filaSinCifras as HTMLElement).getAllByRole('cell');
    expect(celdas[2]).toHaveTextContent('—');
    expect(celdas[3]).toHaveTextContent('—');
    expect(celdas[4]).toHaveTextContent('—');
    expect(celdas[2]).not.toHaveTextContent('0');
  });
});

describe('DesgloseTabla — orden', () => {
  it('ordena por nombre ascendente por defecto y marca aria-sort', () => {
    renderTabla();

    expect(nombresDeFilas()).toEqual(['Alta 1', 'Baja 1', 'Cañada de la Leche']);
    expect(screen.getByRole('columnheader', { name: /Subcuenca/ })).toHaveAttribute(
      'aria-sort',
      'ascending'
    );
    expect(screen.getByRole('columnheader', { name: /Superficie/ })).toHaveAttribute(
      'aria-sort',
      'none'
    );
  });

  it('clic en Superficie ordena por hectáreas y el segundo clic invierte', async () => {
    const user = userEvent.setup();
    renderTabla();

    const botonSuperficie = screen.getByRole('button', { name: /Superficie/ });
    await user.click(botonSuperficie);
    // Ascendente por hectáreas: 250 < 400 < 600.
    expect(nombresDeFilas()).toEqual(['Cañada de la Leche', 'Baja 1', 'Alta 1']);
    expect(screen.getByRole('columnheader', { name: /Superficie/ })).toHaveAttribute(
      'aria-sort',
      'ascending'
    );

    await user.click(botonSuperficie);
    expect(nombresDeFilas()).toEqual(['Alta 1', 'Baja 1', 'Cañada de la Leche']);
    expect(screen.getByRole('columnheader', { name: /Superficie/ })).toHaveAttribute(
      'aria-sort',
      'descending'
    );
  });

  it('clic en % Alto+Crítico ordena por el valor guardado, no por nombre', async () => {
    const user = userEvent.setup();
    renderTabla();

    await user.click(screen.getByRole('button', { name: /% Alto\+Crítico/ }));
    expect(nombresDeFilas()).toEqual(['Baja 1', 'Alta 1', 'Cañada de la Leche']);

    // Descendente: 12.5 antes que 3.2. La posición de la fila sin cifra
    // guardada no se afirma acá (ver reporte: el reverse() del componente
    // pone los null al frente en desc, contradiciendo su propio comentario).
    await user.click(screen.getByRole('button', { name: /% Alto\+Crítico/ }));
    const nombres = nombresDeFilas();
    expect(nombres.indexOf('Alta 1')).toBeLessThan(nombres.indexOf('Baja 1'));
  });

  it('en orden ascendente las filas sin cifra quedan últimas', async () => {
    const user = userEvent.setup();
    renderTabla();

    await user.click(screen.getByRole('button', { name: /Lluvia anual/ }));
    expect(nombresDeFilas()).toEqual(['Baja 1', 'Alta 1', 'Cañada de la Leche']);
  });

  it('ordenar por Clase de suelo compara los textos y manda los null al final', async () => {
    const user = userEvent.setup();
    renderTabla();

    await user.click(screen.getByRole('button', { name: /Clase de suelo/ }));
    expect(nombresDeFilas()).toEqual(['Alta 1', 'Baja 1', 'Cañada de la Leche']);
  });

  it('dos filas sin cifra en la misma columna quedan estables entre sí', async () => {
    const user = userEvent.setup();
    const dosSinSuelo: FichaDesgloseSubcuenca[] = [
      { ...FILAS[0], nombre: 'Alpha', clase_suelo_dominante: null },
      { ...FILAS[1], nombre: 'Beta', clase_suelo_dominante: null },
    ];
    renderTabla(dosSinSuelo);

    await user.click(screen.getByRole('button', { name: /Clase de suelo/ }));
    expect(nombresDeFilas()).toEqual(['Alpha', 'Beta']);
  });

  it('cambiar de columna resetea la dirección a ascendente', async () => {
    const user = userEvent.setup();
    renderTabla();

    await user.click(screen.getByRole('button', { name: /Superficie/ }));
    await user.click(screen.getByRole('button', { name: /Superficie/ })); // desc
    await user.click(screen.getByRole('button', { name: /Lluvia anual/ })); // nueva clave → asc

    expect(screen.getByRole('columnheader', { name: /Lluvia anual/ })).toHaveAttribute(
      'aria-sort',
      'ascending'
    );
  });
});

describe('DesgloseTabla — nota del umbral', () => {
  it('con umbral legacy70 nombra el umbral histórico de la columna', () => {
    renderTabla(FILAS, 'legacy70');

    const nota = screen.getByText(/usa el umbral histórico guardado/);
    expect(nota).toHaveTextContent('puntaje > 70');
    expect(nota).toHaveTextContent('PR 2');
  });

  it('sin umbral no renderiza la nota', () => {
    renderTabla(FILAS, null);

    expect(screen.queryByText(/usa el umbral histórico guardado/)).not.toBeInTheDocument();
  });
});
