/**
 * LeyendaPanelCollapse.test.tsx
 *
 * Collapsible Leyenda block inside `<LeyendaPanel />`. Click the "Leyenda"
 * header (or press Enter/Space) to hide all legend items; click again to
 * re-show them. State is local and ephemeral (useState).
 */

import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { LeyendaPanel } from '../../src/components/map2d/LeyendaPanel';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

describe('<LeyendaPanel /> — collapsible Leyenda block', () => {
  it('renders legend items visible by default (expanded)', () => {
    renderWithMantine(<LeyendaPanel pilarVerdeBpaHistoricoVisible />);

    // Default item + BPA histórico block render.
    expect(screen.getByText('Zona Consorcio')).toBeInTheDocument();
    expect(screen.getByTestId('bpa-historico-legend')).toBeInTheDocument();
  });

  it('hides legend items when the header is clicked, keeps title visible', () => {
    renderWithMantine(<LeyendaPanel pilarVerdeBpaHistoricoVisible />);

    const header = screen.getByTestId('leyenda-header');
    fireEvent.click(header);

    expect(screen.queryByText('Zona Consorcio')).not.toBeInTheDocument();
    expect(screen.queryByTestId('bpa-historico-legend')).not.toBeInTheDocument();
    // Title still visible.
    expect(screen.getByText('Leyenda')).toBeInTheDocument();
    expect(header).toHaveAttribute('aria-expanded', 'false');
  });

  it('re-shows legend items after a second click', () => {
    renderWithMantine(<LeyendaPanel pilarVerdeBpaHistoricoVisible />);

    const header = screen.getByTestId('leyenda-header');
    fireEvent.click(header);
    fireEvent.click(header);

    expect(screen.getByText('Zona Consorcio')).toBeInTheDocument();
    expect(screen.getByTestId('bpa-historico-legend')).toBeInTheDocument();
    expect(header).toHaveAttribute('aria-expanded', 'true');
  });

  it('toggles via Enter key on the header', () => {
    renderWithMantine(<LeyendaPanel pilarVerdeBpaHistoricoVisible />);

    const header = screen.getByTestId('leyenda-header');
    fireEvent.keyDown(header, { key: 'Enter' });

    expect(screen.queryByText('Zona Consorcio')).not.toBeInTheDocument();
    expect(header).toHaveAttribute('aria-expanded', 'false');
  });
});
