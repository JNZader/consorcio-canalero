/**
 * SeleccionLista.test.tsx — the Lista tab of the Elegir step (S3/S5/S6).
 *
 * Behavior-first: the empty-catalog copy, the diacritics-insensitive search
 * filter, one Accordion per cuenca with its selection counter, the "Toda la
 * cuenca" checkbox states (ninguna / parcial indeterminada / toda), the
 * per-zona toggles, and the 60-zona cap disabling unchecked boxes.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { SeleccionLista } from '../../../src/components/map2d/informeArea/SeleccionLista';
import type { ZonaRef } from '../../../src/components/map2d/informeArea/useSeleccionArea';

function wrapper({ children }: { children: ReactNode }) {
  return <MantineProvider env="test">{children}</MantineProvider>;
}

const CATALOGO: ZonaRef[] = [
  { id: 'b1', nombre: 'Baja 1', cuenca: 'Arroyo Algodón' },
  { id: 'a1', nombre: 'Alta 1', cuenca: 'Río Tercero' },
  { id: 'a2', nombre: 'Alta 2', cuenca: 'Río Tercero' },
];

const CUENCAS = ['Arroyo Algodón', 'Río Tercero'];

type Props = Partial<Parameters<typeof SeleccionLista>[0]>;

function renderLista(props: Props = {}) {
  const onToggleZona = vi.fn();
  const onToggleCuenca = vi.fn();
  render(
    <SeleccionLista
      catalog={CATALOGO}
      cuencas={CUENCAS}
      seleccion={new Set<string>()}
      onToggleZona={onToggleZona}
      onToggleCuenca={onToggleCuenca}
      cupoLleno={false}
      {...props}
    />,
    { wrapper }
  );
  return { onToggleZona, onToggleCuenca };
}

/** Abre el accordion de una cuenca y devuelve su panel expandido. */
async function abrirCuenca(user: ReturnType<typeof userEvent.setup>, cuenca: RegExp) {
  const control = screen.getByRole('button', { name: cuenca });
  await user.click(control);
  // happy-dom no computa el nombre accesible del panel desde su
  // aria-labelledby: el panel se resuelve por el aria-controls del control.
  const panel = document.getElementById(control.getAttribute('aria-controls') ?? '');
  expect(panel).not.toBeNull();
  return panel as HTMLElement;
}

describe('SeleccionLista — estados', () => {
  it('catálogo vacío muestra la copia de catálogo no disponible', () => {
    render(
      <SeleccionLista
        catalog={[]}
        cuencas={[]}
        seleccion={new Set()}
        onToggleZona={vi.fn()}
        onToggleCuenca={vi.fn()}
        cupoLleno={false}
      />,
      { wrapper }
    );

    expect(screen.getByTestId('informe-area-lista-vacia')).toHaveTextContent(
      'No se pudieron cargar las subcuencas operativas.'
    );
  });

  it('renderiza un accordion por cuenca con su contador de selección', () => {
    renderLista();

    expect(screen.getByRole('button', { name: /Arroyo Algodón/ })).toHaveTextContent('0/1');
    expect(screen.getByRole('button', { name: /Río Tercero/ })).toHaveTextContent('0/2');
  });
});

describe('SeleccionLista — búsqueda', () => {
  it('filtra zonas por nombre y deja solo las cuencas con coincidencias', async () => {
    const user = userEvent.setup();
    renderLista();

    await user.type(screen.getByLabelText('Buscar subcuenca o cuenca'), 'baja');

    expect(screen.getByRole('button', { name: /Arroyo Algodón/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Río Tercero/ })).not.toBeInTheDocument();
  });

  it('la búsqueda ignora mayúsculas y tildes', async () => {
    const user = userEvent.setup();
    renderLista();

    // "algodon" sin tilde tiene que encontrar "Arroyo Algodón".
    await user.type(screen.getByLabelText('Buscar subcuenca o cuenca'), 'algodon');

    expect(screen.getByRole('button', { name: /Arroyo Algodón/ })).toBeInTheDocument();
  });

  it('sin coincidencias avisa y no ofrece cuencas', async () => {
    const user = userEvent.setup();
    renderLista();

    await user.type(screen.getByLabelText('Buscar subcuenca o cuenca'), 'inexistente');

    expect(screen.getByText(/Ninguna subcuenca coincide con “inexistente”/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Río Tercero/ })).not.toBeInTheDocument();
  });
});

describe('SeleccionLista — selección por zona', () => {
  it('el checkbox de zona dispara onToggleZona con su id', async () => {
    const user = userEvent.setup();
    const { onToggleZona } = renderLista();

    const region = await abrirCuenca(user, /Río Tercero/);
    await user.click(within(region).getByRole('checkbox', { name: 'Alta 2' }));

    expect(onToggleZona).toHaveBeenCalledWith('a2');
  });

  it('marca como checked las zonas que ya están en la selección', async () => {
    const user = userEvent.setup();
    renderLista({ seleccion: new Set(['a1']) });

    const region = await abrirCuenca(user, /Río Tercero/);
    expect(within(region).getByRole('checkbox', { name: 'Alta 1' })).toBeChecked();
    expect(within(region).getByRole('checkbox', { name: 'Alta 2' })).not.toBeChecked();
  });
});

describe('SeleccionLista — "Toda la cuenca"', () => {
  it('sin zonas elegidas queda unchecked y dispara incluir=true', async () => {
    const user = userEvent.setup();
    const { onToggleCuenca } = renderLista();

    const region = await abrirCuenca(user, /Río Tercero/);
    const toda = within(region).getByRole('checkbox', { name: 'Toda la cuenca' });
    expect(toda).not.toBeChecked();
    expect(toda).not.toHaveAttribute('data-indeterminate');

    await user.click(toda);
    expect(onToggleCuenca).toHaveBeenCalledWith('Río Tercero', true);
  });

  it('con todas las zonas de la cuenca queda checked y dispara incluir=false', async () => {
    const user = userEvent.setup();
    const { onToggleCuenca } = renderLista({ seleccion: new Set(['a1', 'a2']) });

    const region = await abrirCuenca(user, /Río Tercero/);
    const toda = within(region).getByRole('checkbox', { name: 'Toda la cuenca' });
    expect(toda).toBeChecked();
    expect(toda).not.toHaveAttribute('data-indeterminate');

    await user.click(toda);
    expect(onToggleCuenca).toHaveBeenCalledWith('Río Tercero', false);
  });

  it('con algunas zonas queda indeterminada y no checked', async () => {
    const user = userEvent.setup();
    renderLista({ seleccion: new Set(['a1']) });

    const region = await abrirCuenca(user, /Río Tercero/);
    const toda = within(region).getByRole('checkbox', { name: 'Toda la cuenca' });

    expect(toda).not.toBeChecked();
    expect(toda).toHaveAttribute('data-indeterminate', 'true');
  });

  it('el contador de la cabecera refleja cuántas zonas de la cuenca están elegidas', () => {
    renderLista({ seleccion: new Set(['a1']) });

    expect(screen.getByRole('button', { name: /Río Tercero/ })).toHaveTextContent('1/2');
  });
});

describe('SeleccionLista — tope de 60 (cupo lleno)', () => {
  it('deshabilita los checkbox de zonas no elegidas', async () => {
    const user = userEvent.setup();
    renderLista({ seleccion: new Set(['a1']), cupoLleno: true });

    const region = await abrirCuenca(user, /Río Tercero/);
    expect(within(region).getByRole('checkbox', { name: 'Alta 2' })).toBeDisabled();
    // La zona ya elegida sigue operable (sacar siempre se puede).
    expect(within(region).getByRole('checkbox', { name: 'Alta 1' })).toBeEnabled();
  });

  it('deshabilita "Toda la cuenca" solo cuando la cuenca no tiene nada elegido', async () => {
    const user = userEvent.setup();
    renderLista({ seleccion: new Set(['a1']), cupoLleno: true });

    const tercero = await abrirCuenca(user, /Río Tercero/);
    expect(within(tercero).getByRole('checkbox', { name: 'Toda la cuenca' })).toBeEnabled();

    const algodon = await abrirCuenca(user, /Arroyo Algodón/);
    expect(within(algodon).getByRole('checkbox', { name: 'Toda la cuenca' })).toBeDisabled();
  });
});
