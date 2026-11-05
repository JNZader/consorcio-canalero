import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { PuntoInteresCard } from '../../src/components/map2d/PuntoInteresCard';
import { PUNTO_INTERES_TIPOS } from '../../src/lib/api/puntosInteres';

describe('PuntoInteresCard', () => {
  it('pide confirmación antes de borrar', async () => {
    const user = userEvent.setup();
    const onDelete = vi.fn();
    render(
      <MantineProvider env="test">
        <PuntoInteresCard
          properties={{
            id: 'poi-1',
            titulo: 'Alcantarilla norte',
            nota: null,
            tipo: PUNTO_INTERES_TIPOS.ALCANTARILLA,
          }}
          onDelete={onDelete}
        />
      </MantineProvider>
    );

    await user.click(screen.getByRole('button', { name: 'Borrar punto de interés' }));
    expect(onDelete).not.toHaveBeenCalled();
    expect(screen.getByRole('dialog', { name: 'Borrar punto de interés' })).toHaveTextContent(
      'Alcantarilla norte'
    );

    await user.click(screen.getByRole('button', { name: 'Cancelar' }));
    expect(onDelete).not.toHaveBeenCalled();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Borrar punto de interés' }));
    await user.click(screen.getByRole('button', { name: 'Borrar' }));
    expect(onDelete).toHaveBeenCalledOnce();
    expect(onDelete).toHaveBeenCalledWith('poi-1');
  });
});
