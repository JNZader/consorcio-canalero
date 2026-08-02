/**
 * FichaClassToggle.test.tsx
 *
 * Class rows are TOGGLES for the painted overlay (T3b, fix 3).
 *
 * The tables were already the overlay's legend (T3a); now they are also its
 * control. Clicking a class row turns that class off on the map — a pure filter
 * over the FeatureCollection already loaded, no refetch — and the row goes
 * dimmed with a hollow chip so the panel keeps telling the truth about what is
 * painted. The row is a real button: `aria-pressed` announces "painted / not
 * painted" and Enter/Space work.
 *
 * Without an `onToggleClase` the tables stay exactly as they were, static.
 */

import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { RiesgoBins } from "../../src/components/map2d/RiesgoBins";
import { SuelosBreakdown } from "../../src/components/map2d/SuelosBreakdown";
import { riesgoClassColor } from "../../src/components/map2d/fichaOverlayLayers";
import { getSoilColor } from "../../src/hooks/useSoilMap";
import type { FichaDataset } from "../../src/lib/api/ficha";

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

const RIESGO = dataset([
	{ clase: "Bajo", ha: 30, pct: 30 },
	{ clase: "Alto", ha: 70, pct: 70 },
]);

const SUELOS = dataset([
	{ clase: "II", ha: 40, pct: 40 },
	{ clase: "IV", ha: 60, pct: 60 },
]);

describe("RiesgoBins · class rows as overlay toggles", () => {
	it("renders plain, non-interactive rows when no handler is wired", () => {
		renderWithMantine(
			<RiesgoBins
				label="Riesgo"
				dataset={RIESGO}
				legendKey="flood_risk"
				testId="ficha-riesgo"
			/>,
		);

		expect(screen.queryByTestId("ficha-riesgo-row-Alto")).toBeNull();
		expect(screen.queryByRole("button", { name: /Alto/ })).toBeNull();
		// The legend chip is unaffected — it never depended on interactivity.
		expect(screen.getByTestId("ficha-riesgo-chip-Alto")).toBeInTheDocument();
	});

	it("reports the clicked class to the container", async () => {
		const user = userEvent.setup();
		const onToggleClase = vi.fn();
		renderWithMantine(
			<RiesgoBins
				label="Riesgo"
				dataset={RIESGO}
				legendKey="flood_risk"
				testId="ficha-riesgo"
				onToggleClase={onToggleClase}
			/>,
		);

		await user.click(screen.getByTestId("ficha-riesgo-row-Alto"));

		expect(onToggleClase).toHaveBeenCalledTimes(1);
		expect(onToggleClase).toHaveBeenCalledWith("Alto");
	});

	it("announces painted / not painted through aria-pressed", () => {
		const { rerender } = renderWithMantine(
			<RiesgoBins
				label="Riesgo"
				dataset={RIESGO}
				legendKey="flood_risk"
				testId="ficha-riesgo"
				onToggleClase={() => {}}
			/>,
		);
		// All classes painted by default.
		expect(screen.getByTestId("ficha-riesgo-row-Alto")).toHaveAttribute(
			"aria-pressed",
			"true",
		);
		expect(screen.getByTestId("ficha-riesgo-row-Bajo")).toHaveAttribute(
			"aria-pressed",
			"true",
		);

		rerender(
			<MantineProvider env="test">
				<RiesgoBins
					label="Riesgo"
					dataset={RIESGO}
					legendKey="flood_risk"
					testId="ficha-riesgo"
					hiddenClases={["Alto"]}
					onToggleClase={() => {}}
				/>
			</MantineProvider>,
		);

		expect(screen.getByTestId("ficha-riesgo-row-Alto")).toHaveAttribute(
			"aria-pressed",
			"false",
		);
		// Only the toggled class changes — this is per-class, not a master switch.
		expect(screen.getByTestId("ficha-riesgo-row-Bajo")).toHaveAttribute(
			"aria-pressed",
			"true",
		);
	});

	it("dims a hidden row and hollows its chip, keeping the class color", () => {
		renderWithMantine(
			<RiesgoBins
				label="Riesgo"
				dataset={RIESGO}
				legendKey="flood_risk"
				testId="ficha-riesgo"
				hiddenClases={["Alto"]}
				onToggleClase={() => {}}
			/>,
		);

		const row = screen.getByTestId("ficha-riesgo-row-Alto");
		expect(row).toHaveAttribute("data-hidden", "true");
		expect(Number(row.style.opacity)).toBeLessThan(1);

		const chip = screen.getByTestId("ficha-riesgo-chip-Alto");
		expect(chip).toHaveAttribute("data-chip-hollow", "true");
		// Hollow = outlined in its own color, not repainted grey: the row is still
		// the legend entry for that class.
		expect(chip).toHaveAttribute(
			"data-chip-color",
			riesgoClassColor("flood_risk", "Alto"),
		);
		expect(chip.style.backgroundColor).toBe("transparent");

		// The visible row stays solid.
		const visibleChip = screen.getByTestId("ficha-riesgo-chip-Bajo");
		expect(visibleChip).not.toHaveAttribute("data-chip-hollow");
		expect(screen.getByTestId("ficha-riesgo-row-Bajo")).toHaveAttribute(
			"data-hidden",
			"false",
		);
	});

	it("keeps the ha / % figures on a hidden row (they are facts, not paint)", () => {
		renderWithMantine(
			<RiesgoBins
				label="Riesgo"
				dataset={RIESGO}
				legendKey="flood_risk"
				testId="ficha-riesgo"
				hiddenClases={["Alto"]}
				onToggleClase={() => {}}
			/>,
		);

		expect(screen.getByText("70.0 ha")).toBeInTheDocument();
		expect(screen.getByText("70.0%")).toBeInTheDocument();
	});

	it.each([
		["{Enter}", "Enter"],
		[" ", "Space"],
	])("activates with the keyboard (%s)", async (key) => {
		const user = userEvent.setup();
		const onToggleClase = vi.fn();
		renderWithMantine(
			<RiesgoBins
				label="Riesgo"
				dataset={RIESGO}
				legendKey="flood_risk"
				testId="ficha-riesgo"
				onToggleClase={onToggleClase}
			/>,
		);

		screen.getByTestId("ficha-riesgo-row-Bajo").focus();
		await user.keyboard(key);

		expect(onToggleClase).toHaveBeenCalledWith("Bajo");
	});

	it("reaches the rows by tabbing (they are real buttons, in table order)", async () => {
		const user = userEvent.setup();
		renderWithMantine(
			<RiesgoBins
				label="Riesgo"
				dataset={RIESGO}
				legendKey="flood_risk"
				testId="ficha-riesgo"
				onToggleClase={() => {}}
			/>,
		);

		await user.tab();
		expect(screen.getByTestId("ficha-riesgo-row-Bajo")).toHaveFocus();
		await user.tab();
		expect(screen.getByTestId("ficha-riesgo-row-Alto")).toHaveFocus();
	});

	it("fades the complement bar segment of a hidden class", () => {
		renderWithMantine(
			<RiesgoBins
				label="Riesgo"
				dataset={RIESGO}
				legendKey="flood_risk"
				testId="ficha-riesgo"
				hiddenClases={["Alto"]}
				onToggleClase={() => {}}
			/>,
		);

		const segments = Array.from(
			screen.getByTestId("riesgo-severity-bar").children,
		) as HTMLElement[];
		// Order follows `dataset.clases`: Bajo, then the hidden Alto.
		expect(Number(segments[0].style.opacity)).toBe(1);
		expect(Number(segments[1].style.opacity)).toBeLessThan(1);
		// The widths never move: percentages describe the analysis, not the paint.
		expect(segments[1].style.width).toBe("70%");
	});
});

describe("SuelosBreakdown · class rows as overlay toggles", () => {
	it("reports the clicked soil class (the same labels the overlay carries)", async () => {
		const user = userEvent.setup();
		const onToggleClase = vi.fn();
		renderWithMantine(
			<SuelosBreakdown dataset={SUELOS} onToggleClase={onToggleClase} />,
		);

		await user.click(screen.getByTestId("ficha-suelos-row-IV"));

		expect(onToggleClase).toHaveBeenCalledWith("IV");
	});

	it("dims a hidden soil row and hollows its chip in the soils palette", () => {
		renderWithMantine(
			<SuelosBreakdown
				dataset={SUELOS}
				hiddenClases={["II"]}
				onToggleClase={() => {}}
			/>,
		);

		const row = screen.getByTestId("ficha-suelos-row-II");
		expect(row).toHaveAttribute("aria-pressed", "false");
		expect(Number(row.style.opacity)).toBeLessThan(1);
		expect(screen.getByTestId("ficha-suelos-chip-II")).toHaveAttribute(
			"data-chip-color",
			getSoilColor("II"),
		);
	});

	it("keeps the detalle tooltip trigger inside the toggle", () => {
		renderWithMantine(
			<SuelosBreakdown
				dataset={dataset([
					{ clase: "III", ha: 10, pct: 100, detalle: "Suelo franco" },
				])}
				onToggleClase={() => {}}
			/>,
		);

		const row = screen.getByTestId("ficha-suelos-row-III");
		expect(row).toContainElement(screen.getByText("III"));
		expect(row).toContainElement(screen.getByTestId("ficha-suelos-chip-III"));
	});

	it("stays static with no handler wired", () => {
		renderWithMantine(<SuelosBreakdown dataset={SUELOS} />);

		expect(screen.queryByTestId("ficha-suelos-row-IV")).toBeNull();
		expect(screen.getByTestId("ficha-suelos-chip-IV")).toBeInTheDocument();
	});
});
