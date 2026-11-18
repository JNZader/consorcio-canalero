/**
 * SeleccionChips.test.tsx — the removable Pills of the Elegir step (S5).
 *
 * Behavior-first: the empty state copy, one Pill per selected zona (catalog
 * order), Mantine's remove button firing `onRemove` with the zona id, and the
 * "Quitar todas" action appearing only when more than one zona is selected.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { SeleccionChips } from '../../../src/components/map2d/informeArea/SeleccionChips';
import type { ZonaRef } from '../../../src/components/map2d/informeArea/useSeleccionArea';

function wrapper({ children }: { children: ReactNode }) {
  return <MantineProvider env="test">{children}</MantineProvider>;
}

const ZONAS: ZonaRef[] = [
  { id: 'a1', nombre: 'Alta 1', cuenca: 'Río Tercero' },
  { id: 'b1', nombre: 'Baja 1', cuenca: 'Arroyo Algodón' },
];

describe('SeleccionChips', () => {
  it('sin selección muestra el texto de estado vacío y ningún chip', () => {
    render(<SeleccionChips zonas={[]} onRemove={vi.fn()} onClear={vi.fn()} />, { wrapper });

    expect(screen.getByTestId('informe-area-chips-vacio')).toHaveTextContent(
      'Todavía no elegiste subcuencas.'
    );
    expect(screen.queryByTestId('informe-area-chip')).not.toBeInTheDocument();
  });

  it('renderiza un chip por zona en orden de catálogo', () => {
    render(<SeleccionChips zonas={ZONAS} onRemove={vi.fn()} onClear={vi.fn()} />, { wrapper });

    const chips = screen.getAllByTestId('informe-area-chip');
    expect(chips).toHaveLength(2);
    expect(chips[0]).toHaveTextContent('Alta 1');
    expect(chips[1]).toHaveTextContent('Baja 1');
  });

  it('el botón de quitar del chip dispara onRemove con el id de la zona', async () => {
    const user = userEvent.setup();
    const onRemove = vi.fn();
    render(<SeleccionChips zonas={ZONAS} onRemove={onRemove} onClear={vi.fn()} />, { wrapper });

    // Mantine marca el botón de remove aria-hidden + tabIndex -1: hay que
    // buscarlo con hidden para clickearlo como lo haría un pointer.
    const quitar = within(screen.getAllByTestId('informe-area-chip')[0]).getByRole('button', {
      hidden: true,
    });
    await user.click(quitar);

    expect(onRemove).toHaveBeenCalledWith('a1');
    expect(onRemove).toHaveBeenCalledTimes(1);
  });

  it('con más de una zona ofrece "Quitar todas" y dispara onClear', async () => {
    const user = userEvent.setup();
    const onClear = vi.fn();
    render(<SeleccionChips zonas={ZONAS} onRemove={vi.fn()} onClear={onClear} />, { wrapper });

    await user.click(screen.getByRole('button', { name: 'Quitar todas' }));
    expect(onClear).toHaveBeenCalledTimes(1);
  });

  it('con una sola zona no ofrece "Quitar todas"', () => {
    render(<SeleccionChips zonas={[ZONAS[0]]} onRemove={vi.fn()} onClear={vi.fn()} />, {
      wrapper,
    });

    expect(screen.queryByRole('button', { name: 'Quitar todas' })).not.toBeInTheDocument();
  });
});
