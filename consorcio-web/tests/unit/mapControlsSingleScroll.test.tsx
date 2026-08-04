/**
 * mapControlsSingleScroll.test.tsx
 *
 * AUD-005 (T5) — ONE scroll inside the map controls shell.
 *
 * The sidebar body (desktop) and the layers Drawer (mobile) already own a
 * scroll area. `LayerControlsPanel` (maxHeight `calc(100vh - 180px)`) and
 * `LeyendaPanel` (maxHeight `80vh`) each added another one, so with several
 * toggles active the legend ended up below the fold of a viewport-tall box
 * nested inside another scroller, and the wheel/touch gesture was trapped by
 * whichever container sat under the pointer.
 *
 * `insideScrollContainer` opts a panel OUT of bounding itself. The floating
 * variant (`MapUiPanels`, no scrolling ancestor) keeps its own bound — that is
 * the default and it is asserted here too, because removing it there would let
 * the panels run off the canvas.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { LayerControlsPanel } from '../../src/components/map2d/LayerControlsPanel';
import { LeyendaPanel } from '../../src/components/map2d/LeyendaPanel';

function renderWithMantine(ui: ReactNode) {
	return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

const layerControlsProps = {
	baseLayer: 'osm' as const,
	onBaseLayerChange: () => {},
	layerItems: [{ id: 'waterways', label: 'Hidrografía', category: 'hidrografia' as const }],
	onLayerVisibilityChange: () => {},
	showIGNOverlay: false,
	onShowIGNOverlayChange: () => {},
	demEnabled: false,
	showDemOverlay: false,
	onShowDemOverlayChange: () => {},
	activeDemLayerId: null,
	onActiveDemLayerIdChange: () => {},
	demOptions: [],
	vectorVisibility: {},
};

describe('map controls — single scroll container (T5)', () => {
	it('LayerControlsPanel bounds ITSELF by default (floating variant has no scrolling ancestor)', () => {
		renderWithMantine(<LayerControlsPanel {...layerControlsProps} />);

		const root = screen.getByTestId('layer-controls-panel-scroll');
		expect(root.style.maxHeight).toBe('calc(100vh - 180px)');
		expect(root.style.overflowY).toBe('auto');
		expect(root.dataset.insideScrollContainer).toBe('false');
	});

	it('LayerControlsPanel renders UNBOUNDED inside a scrolling container', () => {
		renderWithMantine(<LayerControlsPanel {...layerControlsProps} insideScrollContainer />);

		const root = screen.getByTestId('layer-controls-panel-scroll');
		expect(root.style.maxHeight).toBe('');
		expect(root.style.overflowY).toBe('');
		expect(root.style.overflow).toBe('visible');
		expect(root.dataset.insideScrollContainer).toBe('true');
	});

	it('LeyendaPanel bounds ITSELF by default', () => {
		renderWithMantine(<LeyendaPanel embedded data-testid="leyenda" />);

		const [root] = screen.getAllByTestId('leyenda');
		expect(root.style.maxHeight).toBe('80vh');
		expect(root.style.overflowY).toBe('auto');
	});

	it('LeyendaPanel renders UNBOUNDED inside a scrolling container', () => {
		renderWithMantine(<LeyendaPanel embedded insideScrollContainer data-testid="leyenda" />);

		const [root] = screen.getAllByTestId('leyenda');
		expect(root.style.maxHeight).toBe('');
		expect(root.style.overflowY).toBe('');
		expect(root.style.overflow).toBe('visible');
	});

	it('LeyendaPanel unbounds the FLOATING shape too when asked (drawer edge case)', () => {
		renderWithMantine(<LeyendaPanel insideScrollContainer data-testid="leyenda" />);

		const [root] = screen.getAllByTestId('leyenda');
		expect(root.style.maxHeight).toBe('');
		expect(root.style.overflow).toBe('visible');
	});
});
