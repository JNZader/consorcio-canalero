/**
 * CollapsibleSection.test.tsx
 *
 * Base-behavior tests for the shared `<CollapsibleSection />` primitive used
 * by the 2D + 3D map panels (Capas, Leyenda, 3D toggles, 3D legends).
 *
 * Contract:
 *   1. Children render by default (expanded).
 *   2. Title is a native button carrying `aria-expanded` and `aria-controls`.
 *   3. Body region is labelled by the title button.
 *   4. Clicking the title button toggles visibility and flips `aria-expanded`.
 *   5. Pressing Enter or Space on the focused title button toggles.
 *   6. `defaultOpen={false}` renders collapsed on first render.
 *   7. Chevron icon swaps (up when open, down when closed).
 *   8. `rightAccessory` renders beside, not inside, the title button.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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

  it('connects the native title button to the labelled body region when open', () => {
    renderWithMantine(
      <CollapsibleSection title="Capas" testId="capas">
        <p>contenido</p>
      </CollapsibleSection>,
    );

    const header = screen.getByTestId('capas-header');
    expect(header).toBe(screen.getByRole('button', { name: 'Capas' }));
    expect(header.tagName).toBe('BUTTON');
    expect(header).toHaveAttribute('aria-expanded', 'true');
    expect(header).toHaveAttribute('aria-controls', 'capas-body');

    const region = screen.getByRole('region', { name: /capas/i });
    expect(region).toHaveAttribute('id', 'capas-body');
    expect(region).toHaveAttribute('aria-labelledby', 'capas-header');
  });

  it('hides children after clicking the title button and flips aria-expanded to false', async () => {
    const user = userEvent.setup();
    renderWithMantine(
      <CollapsibleSection title="Capas" testId="capas">
        <p data-testid="content">contenido</p>
      </CollapsibleSection>,
    );

    const header = screen.getByTestId('capas-header');
    await user.click(header);

    expect(screen.queryByTestId('content')).not.toBeInTheDocument();
    expect(header).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByText('Capas')).toBeInTheDocument();
  });

  it('re-shows children after clicking twice', async () => {
    const user = userEvent.setup();
    renderWithMantine(
      <CollapsibleSection title="Capas" testId="capas">
        <p data-testid="content">contenido</p>
      </CollapsibleSection>,
    );

    const header = screen.getByTestId('capas-header');
    await user.click(header);
    await user.click(header);

    expect(screen.getByTestId('content')).toBeInTheDocument();
    expect(header).toHaveAttribute('aria-expanded', 'true');
  });

  it('toggles when Enter is pressed on the title button', async () => {
    const user = userEvent.setup();
    renderWithMantine(
      <CollapsibleSection title="Capas" testId="capas">
        <p data-testid="content">contenido</p>
      </CollapsibleSection>,
    );

    const header = screen.getByTestId('capas-header');
    header.focus();
    await user.keyboard('{Enter}');

    expect(screen.queryByTestId('content')).not.toBeInTheDocument();
    expect(header).toHaveAttribute('aria-expanded', 'false');
  });

  it('toggles when Space is pressed on the title button', async () => {
    const user = userEvent.setup();
    renderWithMantine(
      <CollapsibleSection title="Capas" testId="capas">
        <p data-testid="content">contenido</p>
      </CollapsibleSection>,
    );

    const header = screen.getByTestId('capas-header');
    header.focus();
    await user.keyboard('[Space]');

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

  it('renders the rightAccessory beside the title button without blocking the toggle', async () => {
    const user = userEvent.setup();
    const handleAccessoryClick = vi.fn();
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

    const accessory = screen.getByTestId('accessory');
    expect(accessory).toBeInTheDocument();
    const header = screen.getByTestId('capas-header');
    expect(header).not.toContainElement(accessory);

    await user.click(accessory);
    expect(handleAccessoryClick).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('content')).toBeInTheDocument();

    await user.click(header);
    expect(screen.queryByTestId('content')).not.toBeInTheDocument();
  });
});
