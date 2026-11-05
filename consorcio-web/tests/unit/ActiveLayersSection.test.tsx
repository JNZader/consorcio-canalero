import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import {
  ACTIVE_LAYERS_MOBILE_QUERY,
  ActiveLayersSection,
} from '../../src/components/map2d/ActiveLayersSection';
import { readMapCss } from '../helpers/mapCss';

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

  it('exposes opacity and eye (UX-08)', async () => {
    const user = userEvent.setup();
    const onLayerOpacityChange = vi.fn();
    render(
      <MantineProvider env="test">
        <ActiveLayersSection
          rows={[{ id: 'roads', label: 'Red Vial' }]}
          onRemove={() => {}}
          onClearAll={() => {}}
          onRestore={() => {}}
          opacityByLayer={{ roads: 1 }}
          onLayerOpacityChange={onLayerOpacityChange}
        />
      </MantineProvider>,
    );
    await user.click(screen.getByTestId('map-active-eye-roads'));
    expect(onLayerOpacityChange).toHaveBeenCalledWith('roads', 0);
    expect(screen.getByTestId('map-active-opacity-roads')).toBeInTheDocument();
    expect(screen.getByRole('slider', { name: 'Opacidad Red Vial' })).toBeInTheDocument();
  });

  it('en el teléfono la barra queda abajo, con área segura y piso táctil', () => {
    const css = readMapCss();
    const rule = css.match(/\.activeLayers\s*\{([^}]*)\}/)?.[1] ?? '';
    expect(rule).toMatch(/position:\s*sticky/);
    expect(rule).toMatch(/bottom:\s*0/);
    expect(rule).toContain('env(safe-area-inset-bottom, 0px)');
    expect(css).toMatch(
      /\.activeLayersToggle\s*\{[^}]*min-height:\s*var\(--cc-touch-min,\s*44px\)/
    );
  });

  it('en teléfono grueso arranca colapsada y el botón la abre', async () => {
    const user = userEvent.setup();
    const original = window.matchMedia;
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query === ACTIVE_LAYERS_MOBILE_QUERY,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));

    render(
      <MantineProvider env="test">
        <ActiveLayersSection
          rows={[{ id: 'roads', label: 'Red Vial' }]}
          onRemove={() => {}}
          onClearAll={() => {}}
          onRestore={() => {}}
        />
      </MantineProvider>
    );

    const toggle = screen.getByTestId('map-active-layers-toggle');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByTestId('map-active-remove-roads')).not.toBeInTheDocument();
    expect(toggle.className).toContain('activeLayersToggle');

    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByTestId('map-active-remove-roads')).toBeInTheDocument();

    window.matchMedia = original;
  });
});
