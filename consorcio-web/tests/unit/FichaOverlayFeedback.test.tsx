/**
 * FichaOverlayFeedback.test.tsx
 *
 * Loading / error feedback for the "Ver recortado en el mapa" toggle
 * (T3a, fix 4).
 *
 * The container consumed only `.data` from `useFichaOverlay`, so flipping the
 * switch was silent: an in-flight request and an outright failure looked exactly
 * like "there is nothing to paint here". No retry button is offered on purpose —
 * toggling the switch off and on re-issues the query.
 */

import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";

import { FichaTerritorialPanel } from "../../src/components/map2d/FichaTerritorialPanel";
import type { FichaDataset, FichaResponse } from "../../src/lib/api/ficha";

function renderWithMantine(ui: ReactNode) {
	return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

const emptyDataset: FichaDataset = {
	cobertura: "sin_cobertura",
	clases: [],
	pixel_count: 0,
	low_confidence: false,
	cobertura_ratio: 0,
};

const data: FichaResponse = {
	tipo: "parcela",
	area_ha: 116.8,
	suelos: emptyDataset,
	flood_risk: emptyDataset,
	drainage_need: emptyDataset,
	precipitacion_mensual: {
		cobertura: "sin_cobertura",
		low_confidence: false,
		pixel_count: 0,
		cobertura_ratio: 0,
		unidad: "mm",
		serie: [],
		anual_mm: null,
	},
};

function panel(props: {
	overlayVisible?: boolean;
	overlayLoading?: boolean;
	overlayError?: boolean;
}) {
	return (
		<FichaTerritorialPanel
			active
			tipo="parcela"
			nroCuenta="123"
			bpaEnriched={null}
			isLoading={false}
			isError={false}
			error={null}
			data={data}
			onClose={() => {}}
			onToggleOverlay={() => {}}
			{...props}
		/>
	);
}

describe("ficha overlay · loading and error feedback", () => {
	it("shows an inline loader while the overlay query is in flight", () => {
		renderWithMantine(panel({ overlayVisible: true, overlayLoading: true }));

		expect(screen.getByTestId("ficha-overlay-loading")).toBeInTheDocument();
		expect(screen.queryByTestId("ficha-overlay-error")).toBeNull();
	});

	it("shows a compact failure line when the overlay query errors", () => {
		renderWithMantine(panel({ overlayVisible: true, overlayError: true }));

		const error = screen.getByTestId("ficha-overlay-error");
		expect(error).toHaveTextContent("No se pudo pintar el recorte");
		expect(screen.queryByTestId("ficha-overlay-loading")).toBeNull();
		// Toggling off/on refetches — no retry button is rendered.
		expect(screen.queryByRole("button", { name: /reintentar/i })).toBeNull();
	});

	it("prefers the loader over the stale error while a refetch runs", () => {
		renderWithMantine(
			panel({ overlayVisible: true, overlayLoading: true, overlayError: true }),
		);

		expect(screen.getByTestId("ficha-overlay-loading")).toBeInTheDocument();
		expect(screen.queryByTestId("ficha-overlay-error")).toBeNull();
	});

	it("shows nothing while the toggle is OFF, whatever the query state", () => {
		renderWithMantine(
			panel({
				overlayVisible: false,
				overlayLoading: true,
				overlayError: true,
			}),
		);

		expect(screen.getByTestId("ficha-overlay-toggle")).toBeInTheDocument();
		expect(screen.queryByTestId("ficha-overlay-loading")).toBeNull();
		expect(screen.queryByTestId("ficha-overlay-error")).toBeNull();
	});

	it("stays silent by default (no feedback props wired)", () => {
		renderWithMantine(panel({ overlayVisible: true }));

		expect(screen.queryByTestId("ficha-overlay-loading")).toBeNull();
		expect(screen.queryByTestId("ficha-overlay-error")).toBeNull();
	});
});
