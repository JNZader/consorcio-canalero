/**
 * FichaDatasetTabs.test.tsx
 *
 * The ficha body is TABBED (T3b, fixes 1 + 2).
 *
 * It used to stack all four dataset blocks — a sheet the owner had to scroll
 * through — and the on-map overlay had its OWN dataset picker further down, so
 * two controls answered the same question and could disagree. There is now ONE
 * segmented control at the top: it selects the visible table AND the dataset the
 * map paints. The visible table IS the legend of what is painted.
 *
 * The rainfall tab has no clipped overlay, so the "Ver recortado en el mapa"
 * toggle is HIDDEN there (not disabled — a disabled switch is a control the user
 * has to reason about, in the tightest strip of the panel).
 */

import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { type ReactNode, useState } from "react";
import { describe, expect, it, vi } from "vitest";

import {
	type FichaPanelTab,
	FichaTerritorialPanel,
} from "../../src/components/map2d/FichaTerritorialPanel";
import type { FichaDataset, FichaResponse } from "../../src/lib/api/ficha";

function renderWithMantine(ui: ReactNode) {
	return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

function dataset(clases: FichaDataset["clases"]): FichaDataset {
	return {
		cobertura: "total",
		clases,
		pixel_count: 5000,
		low_confidence: false,
		cobertura_ratio: 1,
	};
}

const DATA: FichaResponse = {
	tipo: "parcela",
	area_ha: 100,
	suelos: dataset([{ clase: "IV", ha: 60, pct: 60 }]),
	flood_risk: dataset([{ clase: "Alto", ha: 40, pct: 40 }]),
	drainage_need: dataset([{ clase: "Bajo", ha: 100, pct: 100 }]),
	precipitacion_mensual: {
		cobertura: "total",
		low_confidence: false,
		pixel_count: 100,
		cobertura_ratio: 1,
		unidad: "mm",
		serie: [{ mes: 1, mm: 120 }],
		anual_mm: 800,
	},
};

const BASE = {
	active: true as const,
	tipo: "parcela" as const,
	nroCuenta: null,
	bpaEnriched: null,
	isLoading: false,
	isError: false,
	error: null,
	data: DATA,
	onClose: () => {},
};

/**
 * The panel is CONTROLLED — the container owns the tab because it also owns the
 * overlay query key. This harness plays that container, and `onChangeTab` is the
 * exact signal the container turns into the painted dataset.
 */
function ControlledPanel({
	onChangeTab,
	initialTab = "suelos",
	onToggleOverlay = () => {},
	...rest
}: {
	onChangeTab?: (tab: FichaPanelTab) => void;
	initialTab?: FichaPanelTab;
	onToggleOverlay?: (visible: boolean) => void;
	overlayVisible?: boolean;
}) {
	const [tab, setTab] = useState<FichaPanelTab>(initialTab);
	return (
		<FichaTerritorialPanel
			{...BASE}
			{...rest}
			tab={tab}
			onChangeTab={(next) => {
				setTab(next);
				onChangeTab?.(next);
			}}
			onToggleOverlay={onToggleOverlay}
		/>
	);
}

describe("ficha dataset tabs · one table at a time", () => {
	it("shows only the soils table on the default tab", () => {
		renderWithMantine(<ControlledPanel />);

		expect(screen.getByTestId("ficha-dataset-tabs")).toBeInTheDocument();
		expect(screen.getByTestId("ficha-suelos")).toBeInTheDocument();
		expect(screen.queryByTestId("ficha-flood-risk")).toBeNull();
		expect(screen.queryByTestId("ficha-drainage-need")).toBeNull();
		expect(screen.queryByTestId("ficha-precipitacion")).toBeNull();
	});

	it.each([
		["Riesgo", "ficha-flood-risk", "flood_risk"],
		["Drenaje", "ficha-drainage-need", "drainage_need"],
	])(
		"switching to %s renders that table and nothing else",
		async (label, testId, wireValue) => {
			const user = userEvent.setup();
			const onChangeTab = vi.fn();
			renderWithMantine(<ControlledPanel onChangeTab={onChangeTab} />);

			await user.click(screen.getByRole("radio", { name: label }));

			// The SAME selector drives the overlay: the container receives the wire
			// value it uses as the overlay dataset / query key.
			expect(onChangeTab).toHaveBeenCalledWith(wireValue);
			expect(screen.getByTestId(testId)).toBeInTheDocument();
			expect(screen.queryByTestId("ficha-suelos")).toBeNull();
		},
	);

	it("switching back to Suelos restores the soils table", async () => {
		const user = userEvent.setup();
		renderWithMantine(<ControlledPanel initialTab="flood_risk" />);
		expect(screen.getByTestId("ficha-flood-risk")).toBeInTheDocument();

		await user.click(screen.getByRole("radio", { name: "Suelos" }));

		expect(screen.getByTestId("ficha-suelos")).toBeInTheDocument();
		expect(screen.queryByTestId("ficha-flood-risk")).toBeNull();
	});

	it("the header stays fixed above the selector on every tab", async () => {
		const user = userEvent.setup();
		renderWithMantine(<ControlledPanel />);

		for (const label of ["Riesgo", "Drenaje", "Lluvia", "Suelos"]) {
			await user.click(screen.getByRole("radio", { name: label }));
			expect(screen.getByTestId("ficha-resumen")).toBeInTheDocument();
			expect(screen.getByText("Superficie analizada:")).toBeInTheDocument();
		}
	});
});

describe("ficha dataset tabs · the Lluvia tab has no overlay", () => {
	it("renders the precipitation chart and HIDES the overlay toggle", async () => {
		const user = userEvent.setup();
		renderWithMantine(<ControlledPanel />);
		// Present on a dataset tab…
		expect(screen.getByTestId("ficha-overlay-toggle")).toBeInTheDocument();

		await user.click(screen.getByRole("radio", { name: "Lluvia" }));

		expect(screen.getByTestId("ficha-precipitacion")).toBeInTheDocument();
		// …and gone on Lluvia: there is no rainfall overlay to paint.
		expect(screen.queryByTestId("ficha-overlay-toggle")).toBeNull();
	});

	it("brings the toggle back — still ON — when leaving Lluvia", async () => {
		const user = userEvent.setup();
		renderWithMantine(<ControlledPanel overlayVisible />);

		await user.click(screen.getByRole("radio", { name: "Lluvia" }));
		expect(screen.queryByTestId("ficha-overlay-toggle")).toBeNull();

		await user.click(screen.getByRole("radio", { name: "Drenaje" }));

		// The user's ON/OFF intent survived the round trip — hiding the control
		// never cleared it.
		expect(screen.getByTestId("ficha-overlay-toggle")).toBeChecked();
	});

	it("offers no class toggles on the chart tab", async () => {
		const user = userEvent.setup();
		renderWithMantine(<ControlledPanel />);

		await user.click(screen.getByRole("radio", { name: "Lluvia" }));

		expect(screen.queryByRole("button", { name: /en el mapa$/ })).toBeNull();
	});
});

describe("ficha dataset tabs · BPA badges survive the redesign", () => {
	it("keeps the Pilar Verde block in the fixed header, compact", () => {
		renderWithMantine(<ControlledPanel />);

		// Shrunk into the header, not dropped: the block is still there.
		const pilar = screen.getByTestId("ficha-pilar-verde");
		expect(pilar).toBeInTheDocument();
		expect(pilar).toHaveTextContent("Pilar Verde");
	});

	it("stays visible on every tab (it describes the parcel, not the dataset)", async () => {
		const user = userEvent.setup();
		renderWithMantine(<ControlledPanel />);

		for (const label of ["Riesgo", "Lluvia"]) {
			await user.click(screen.getByRole("radio", { name: label }));
			expect(screen.getByTestId("ficha-pilar-verde")).toBeInTheDocument();
		}
	});
});
