import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { TerrainExaggerationControls } from '../../src/components/terrain/TerrainExaggerationControls';
import { exaggerationCanvasLabel } from '../../src/components/terrain/terrainExaggeration';

function wrap(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

describe('TerrainExaggerationControls', () => {
  it('sets a preset', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    wrap(
      <TerrainExaggerationControls
        value={200}
        onChange={onChange}
        min={1}
        max={200}
      />,
    );
    await user.click(screen.getByRole('button', { name: '×20' }));
    expect(onChange).toHaveBeenCalledWith(20);
  });

  it('keeps the slider for in-between values', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    wrap(
      <TerrainExaggerationControls
        value={200}
        onChange={onChange}
        min={1}
        max={200}
      />,
    );
    expect(screen.getByRole('slider')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '×1' }));
    expect(onChange).toHaveBeenCalledWith(1);
  });
});

describe('exaggerationCanvasLabel', () => {
  it('names the live multiplier on the canvas', () => {
    expect(exaggerationCanvasLabel(200)).toBe('Relieve exagerado ×200');
  });
});
