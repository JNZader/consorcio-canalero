/**
 * SuggestionGeometrySectionErrorPath.test.tsx
 *
 * The map engine is loaded lazily (PERF-005). A chunk that never arrives — CDN
 * hiccup, offline, blocked request — used to leave `aria-busy="true"` on an
 * empty box forever: no message, no retry, and no hint that the trace is
 * OPTIONAL (`buildSugerenciaPayload` sends `geometry ?? undefined`), so the user
 * had no reason to believe the form could still be submitted.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { SuggestionGeometrySection } from '../../src/components/suggestion-form/SuggestionGeometrySection';

const { loadMapLibreMock, MockMap } = vi.hoisted(() => {
	class MockMap {
		readonly handlers = new Map<string, (event?: unknown) => void>();
		readonly remove = vi.fn();

		on(event: string, handler: (event?: unknown) => void) {
			this.handlers.set(event, handler);
			if (event === 'load') handler();
			return this;
		}

		isStyleLoaded() {
			return true;
		}
	}

	return { loadMapLibreMock: vi.fn(), MockMap };
});

vi.mock('../../src/lib/maplibreLoader', () => ({
	loadMapLibre: () => loadMapLibreMock(),
}));

vi.mock('../../src/hooks/useFormMapLayers', () => ({
	addReferenceLayers: vi.fn(),
	useFormMapLayers: () => ({ zonaGeoJson: null, caminosGeoJson: null, waterways: null }),
}));

vi.mock('../../src/components/map/SuggestionGeometryControl', () => ({
	default: () => <button type="button">geometry-control</button>,
}));

vi.mock('../../src/lib/logger', () => ({
	logger: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
}));

function renderSection() {
	return render(
		<MantineProvider env="test">
			<SuggestionGeometrySection geometry={null} onChange={() => {}} />
		</MantineProvider>,
	);
}

describe('<SuggestionGeometrySection /> — lazy engine failure', () => {
	beforeEach(() => {
		loadMapLibreMock.mockReset();
	});

	it('surfaces an actionable message instead of an eternal busy box', async () => {
		loadMapLibreMock.mockRejectedValue(new Error('chunk load failed'));

		renderSection();

		const map = screen.getByRole('application', { name: /canal en mapa/i });
		expect(map).toHaveAttribute('aria-busy', 'true');

		await waitFor(() => expect(screen.getByText(/no se pudo cargar el mapa/i)).toBeInTheDocument());

		// Busy is released — the wait is OVER, it just did not succeed.
		expect(map).toHaveAttribute('aria-busy', 'false');
		// And the copy tells the user the suggestion is still submittable.
		expect(screen.getByText(/el trazo es opcional/i)).toBeInTheDocument();
		expect(screen.getByText(/recargar la página/i)).toBeInTheDocument();
		// The status notice is part of the map's accessible description.
		expect(map.getAttribute('aria-describedby')).toContain('sugerencia-geometria-estado');
	});

	it('logs the failure so it is diagnosable', async () => {
		const { logger } = await import('../../src/lib/logger');
		loadMapLibreMock.mockRejectedValue(new Error('chunk load failed'));

		renderSection();

		await waitFor(() => expect(logger.error).toHaveBeenCalled());
	});

	it('shows the loading notice first and drops it once the engine resolves', async () => {
		loadMapLibreMock.mockResolvedValue({ Map: MockMap });

		renderSection();

		expect(screen.getByText(/cargando mapa/i)).toBeInTheDocument();

		await waitFor(() =>
			expect(screen.queryByText(/cargando mapa/i)).not.toBeInTheDocument(),
		);
		const map = screen.getByRole('application', { name: /canal en mapa/i });
		expect(map).toHaveAttribute('aria-busy', 'false');
		expect(map.getAttribute('aria-describedby')).not.toContain('sugerencia-geometria-estado');
	});
});
