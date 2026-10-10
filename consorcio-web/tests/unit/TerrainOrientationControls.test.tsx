import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { TerrainOrientationControls } from '../../src/components/terrain/TerrainOrientationControls';

function wrap(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

describe('TerrainOrientationControls', () => {
  it('resets north, nadir, and both', async () => {
    const user = userEvent.setup();
    const onNorth = vi.fn();
    const onNadir = vi.fn();
    const onOblique = vi.fn();
    const onLookWest = vi.fn();
    const onReset = vi.fn();
    wrap(
      <TerrainOrientationControls
        onNorth={onNorth}
        onNadir={onNadir}
        onOblique={onOblique}
        onLookWest={onLookWest}
        onReset={onReset}
      />,
    );
    await user.click(screen.getByRole('button', { name: 'Norte' }));
    await user.click(screen.getByRole('button', { name: 'Cenital' }));
    await user.click(screen.getByRole('button', { name: 'Oblicua' }));
    await user.click(screen.getByRole('button', { name: 'Desde el oeste' }));
    await user.click(screen.getByRole('button', { name: 'Reset' }));
    expect(onNorth).toHaveBeenCalledOnce();
    expect(onNadir).toHaveBeenCalledOnce();
    expect(onOblique).toHaveBeenCalledOnce();
    expect(onLookWest).toHaveBeenCalledOnce();
    expect(onReset).toHaveBeenCalledOnce();
  });
});
