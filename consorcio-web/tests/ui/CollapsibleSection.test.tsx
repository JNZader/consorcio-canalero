/**
 * CollapsibleSection.test.tsx
 *
 * Base-behavior tests for the shared `<CollapsibleSection />` primitive used
 * by the 2D + 3D map panels (Capas, Leyenda, 3D toggles, 3D legends).
 *
 * Contract:
 *   1. Children render by default (expanded).
 *   2. Title row carries `role="button"`, `aria-expanded`, `aria-controls`,
 *      and `tabIndex=0`.
 *   3. Body region is labelled by the title row.
 *   4. Clicking the title row toggles visibility and flips `aria-expanded`.
 *   5. Pressing Enter or Space on the focused title row toggles.
 *   6. `defaultOpen={false}` renders collapsed on first render.
 *   7. Chevron icon swaps (up when open, down when closed).
 *   8. `rightAccessory` renders inside the title row without eating clicks.
 */

import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { CollapsibleSection } from '../../src/components/ui/CollapsibleSection';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

describe('<CollapsibleSection />', () => {
  it('renders the title and children by default (expanded)', () => {
    renderWithMantine(
      <CollapsibleSection title="Capas" testId="capas">
        <p data-testid="content">contenido</p>
      </CollapsibleSection>,
    );

    expect(screen.getByText('Capas')).toBeInTheDocument();
    expect(screen.getByTestId('content')).toBeInTheDocument();
  });

  it('connects the title row button to the labelled body region when open', () => {
    renderWithMantine(
      <CollapsibleSection title="Capas" testId="capas">
        <p>contenido</p>
      </CollapsibleSection>,
    );

    const header = screen.getByTestId('capas-header');
    expect(header).toHaveAttribute('role', 'button');
    expect(header).toHaveAttribute('aria-expanded', 'true');
    expect(header).toHaveAttribute('aria-controls', 'capas-body');
    expect(header).toHaveAttribute('tabindex', '0');

    const region = screen.getByRole('region', { name: /capas/i });
    expect(region).toHaveAttribute('id', 'capas-body');
    expect(region).toHaveAttribute('aria-labelledby', 'capas-header');
  });

  it('hides children after clicking the title row and flips aria-expanded to false', () => {
    renderWithMantine(
      <CollapsibleSection title="Capas" testId="capas">
        <p data-testid="content">contenido</p>
      </CollapsibleSection>,
    );

    const header = screen.getByTestId('capas-header');
    fireEvent.click(header);

    expect(screen.queryByTestId('content')).not.toBeInTheDocument();
    expect(header).toHaveAttribute('aria-expanded', 'false');
    // Title stays visible
    expect(screen.getByText('Capas')).toBeInTheDocument();
  });

  it('re-shows children after clicking twice', () => {
    renderWithMantine(
      <CollapsibleSection title="Capas" testId="capas">
        <p data-testid="content">contenido</p>
      </CollapsibleSection>,
    );

    const header = screen.getByTestId('capas-header');
    fireEvent.click(header);
    fireEvent.click(header);

    expect(screen.getByTestId('content')).toBeInTheDocument();
    expect(header).toHaveAttribute('aria-expanded', 'true');
  });

  it('toggles when Enter is pressed on the title row', () => {
    renderWithMantine(
      <CollapsibleSection title="Capas" testId="capas">
        <p data-testid="content">contenido</p>
      </CollapsibleSection>,
    );

    const header = screen.getByTestId('capas-header');
    fireEvent.keyDown(header, { key: 'Enter' });

    expect(screen.queryByTestId('content')).not.toBeInTheDocument();
    expect(header).toHaveAttribute('aria-expanded', 'false');
  });

  it('toggles when Space is pressed on the title row', () => {
    renderWithMantine(
      <CollapsibleSection title="Capas" testId="capas">
        <p data-testid="content">contenido</p>
      </CollapsibleSection>,
    );

    const header = screen.getByTestId('capas-header');
    fireEvent.keyDown(header, { key: ' ' });

    expect(screen.queryByTestId('content')).not.toBeInTheDocument();
    expect(header).toHaveAttribute('aria-expanded', 'false');
  });

  it('respects defaultOpen={false} by rendering collapsed on first render', () => {
    renderWithMantine(
      <CollapsibleSection title="Capas" testId="capas" defaultOpen={false}>
        <p data-testid="content">contenido</p>
      </CollapsibleSection>,
    );

    expect(screen.queryByTestId('content')).not.toBeInTheDocument();
    const header = screen.getByTestId('capas-header');
    expect(header).toHaveAttribute('aria-expanded', 'false');
  });

  it('renders the rightAccessory inside the title row without blocking the toggle', () => {
    const handleAccessoryClick = vi.fn((e: React.MouseEvent) => e.stopPropagation());
    renderWithMantine(
      <CollapsibleSection
        title="Capas"
        testId="capas"
        rightAccessory={
          <button type="button" data-testid="accessory" onClick={handleAccessoryClick}>
            accion
          </button>
        }
      >
        <p data-testid="content">contenido</p>
      </CollapsibleSection>,
    );

    expect(screen.getByTestId('accessory')).toBeInTheDocument();

    // Clicking the title row (NOT the accessory button) still toggles.
    const header = screen.getByTestId('capas-header');
    fireEvent.click(header);
    expect(screen.queryByTestId('content')).not.toBeInTheDocument();
  });
});
