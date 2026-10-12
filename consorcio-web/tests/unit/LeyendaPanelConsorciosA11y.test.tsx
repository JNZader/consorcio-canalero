import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { LeyendaPanel } from '../../src/components/map2d/LeyendaPanel';

function wrap(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

const CONSORCIOS = [
  { codigo: 'A', nombre: 'Consorcio A', color: '#111', tramos: 1, longitud_km: 1 },
  { codigo: 'B', nombre: 'Consorcio B', color: '#222', tramos: 1, longitud_km: 1 },
];

describe('LeyendaPanel consorcios (A11Y-02)', () => {
  it('toggles the consorcios list with a real button and aria-expanded', async () => {
    const user = userEvent.setup();
    wrap(<LeyendaPanel consorcios={CONSORCIOS} />);
    const toggle = screen.getByRole('button', { name: /Red Vial/i });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(toggle).toHaveAttribute('aria-controls', 'leyenda-consorcios');
    expect(screen.queryByTitle('Consorcio A - 1 km')).not.toBeInTheDocument();

    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByTitle('Consorcio A - 1 km')).toBeInTheDocument();
    expect(document.getElementById('leyenda-consorcios')).not.toBeNull();

    await user.keyboard('{Enter}');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
  });
});
