import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ActiveLayersSection } from '../../src/components/map2d/ActiveLayersSection';

describe('ActiveLayersSection', () => {
  it('lists on layers and removes one', async () => {
    const user = userEvent.setup();
    const onRemove = vi.fn();
    render(
      <MantineProvider env="test">
        <ActiveLayersSection
          rows={[
            { id: 'roads', label: 'Red Vial' },
            { id: 'waterways', label: 'Hidrografía' },
          ]}
          onRemove={onRemove}
          onClearAll={() => {}}
          onRestore={() => {}}
        />
      </MantineProvider>
    );
    expect(screen.getByText('En el mapa (2)')).toBeInTheDocument();
    await user.click(screen.getByTestId('map-active-remove-roads'));
    expect(onRemove).toHaveBeenCalledWith('roads');
  });

  it('clears and restores', async () => {
    const user = userEvent.setup();
    const onClearAll = vi.fn();
    const onRestore = vi.fn();
    render(
      <MantineProvider env="test">
        <ActiveLayersSection
          rows={[{ id: 'roads', label: 'Red Vial' }]}
          onRemove={() => {}}
          onClearAll={onClearAll}
          onRestore={onRestore}
        />
      </MantineProvider>
    );
    await user.click(screen.getByTestId('map-active-clear'));
    await user.click(screen.getByTestId('map-active-restore'));
    expect(onClearAll).toHaveBeenCalledOnce();
    expect(onRestore).toHaveBeenCalledOnce();
  });
});
