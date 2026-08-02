/**
 * FichaClassColorChips.test.tsx
 *
 * The ficha tables ARE the overlay's legend (T3a, fix 1a).
 *
 * The owner reported the on-map percentages as wrong. They were not: the numbers
 * matched the tables exactly. What was missing was any way to tell WHICH painted
 * color meant which class. Each class row now leads with a color chip, and the
 * chip's color must come from the SAME source the overlay paints with —
 * `riesgoClassColor` for flood/drainage, `getSoilColor` for soils — so the two
 * can never disagree.
 */

import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";

import { riesgoClassColor } from "../../src/components/map2d/fichaOverlayLayers";
import { RiesgoBins } from "../../src/components/map2d/RiesgoBins";
import { SuelosBreakdown } from "../../src/components/map2d/SuelosBreakdown";
import { getSoilColor } from "../../src/hooks/useSoilMap";
import { LAYER_LEGEND_CONFIG } from "../../src/config/rasterLegend";
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

const RIESGO_CLASES: FichaDataset["clases"] = [
	{ clase: "Bajo", ha: 10, pct: 25 },
	{ clase: "Medio", ha: 10, pct: 25 },
	{ clase: "Alto", ha: 10, pct: 25 },
	{ clase: "Crítico", ha: 10, pct: 25 },
];

describe("RiesgoBins · class color chips", () => {
	it.each(["flood_risk", "drainage_need"] as const)(
		"paints every %s chip with the exact color the overlay uses",
		(legendKey) => {
			renderWithMantine(
				<RiesgoBins
					label="Riesgo"
					dataset={dataset(RIESGO_CLASES)}
					legendKey={legendKey}
					testId="ficha-riesgo"
				/>,
			);

			for (const range of LAYER_LEGEND_CONFIG[legendKey]?.ranges ?? []) {
				const chip = screen.getByTestId(`ficha-riesgo-chip-${range.label}`);
				// The chip reads from the shared lookup, and that lookup returns the
				// rasterLegend color — the exact value painted on the map.
				expect(chip).toHaveAttribute("data-chip-color", range.color);
				expect(riesgoClassColor(legendKey, range.label)).toBe(range.color);
			}
		},
	);

	it("uses the legend colors for the complement bar too (no second palette)", () => {
		const { container } = renderWithMantine(
			<RiesgoBins
				label="Riesgo"
				dataset={dataset(RIESGO_CLASES)}
				legendKey="flood_risk"
				testId="ficha-riesgo"
			/>,
		);

		const bar = screen.getByTestId("riesgo-severity-bar");
		const segments = Array.from(bar.children) as HTMLElement[];
		expect(segments).toHaveLength(RIESGO_CLASES.length);
		segments.forEach((segment, index) => {
			const expected = riesgoClassColor(
				"flood_risk",
				RIESGO_CLASES[index].clase,
			);
			expect(segment.style.backgroundColor).toBe(expected);
		});
		// The retired green→red SEVERITY_RAMP must not survive anywhere in the tree.
		expect(container.innerHTML).not.toContain("#2e7d32");
		expect(container.innerHTML).not.toContain("#e53935");
	});

	/**
	 * R4-003 — an unbordered segment whose color is near-white (drainage "Bajo"
	 * is #fff7ec) rendered as a BLANK HOLE against the near-white panel: the bar
	 * looked broken exactly where it carried the most common class. The chips
	 * already had a hairline; the bar segments now carry the same one, as an
	 * INSET shadow so it never widens the boxes (their widths must sum to 100%).
	 */
	it.each(["flood_risk", "drainage_need"] as const)(
		"gives every %s bar segment the chips' hairline (no white-on-white hole)",
		(legendKey) => {
			renderWithMantine(
				<RiesgoBins
					label="Riesgo"
					dataset={dataset(RIESGO_CLASES)}
					legendKey={legendKey}
					testId="ficha-riesgo"
				/>,
			);

			const segments = Array.from(
				screen.getByTestId("riesgo-severity-bar").children,
			) as HTMLElement[];
			expect(segments).toHaveLength(RIESGO_CLASES.length);
			for (const segment of segments) {
				expect(segment.style.boxShadow).toBe(
					"inset 0 0 0 1px rgba(0, 0, 0, 0.2)",
				);
				// Inset, not a border: a border would add to each segment's box.
				expect(segment.style.border).toBe("");
			}
		},
	);

	it("falls back to the shared neutral grey for a class outside the legend", () => {
		renderWithMantine(
			<RiesgoBins
				label="Riesgo"
				dataset={dataset([{ clase: "Desconocido", ha: 1, pct: 100 }])}
				legendKey="flood_risk"
				testId="ficha-riesgo"
			/>,
		);

		expect(screen.getByTestId("ficha-riesgo-chip-Desconocido")).toHaveAttribute(
			"data-chip-color",
			riesgoClassColor("flood_risk", "Desconocido"),
		);
	});

	it("renders no chips at all when the dataset has no coverage", () => {
		renderWithMantine(
			<RiesgoBins
				label="Riesgo"
				dataset={{ ...dataset([]), cobertura: "sin_cobertura" }}
				legendKey="flood_risk"
				testId="ficha-riesgo"
			/>,
		);

		expect(
			screen.getByTestId("ficha-riesgo-sin-cobertura"),
		).toBeInTheDocument();
		expect(screen.queryByTestId(/ficha-riesgo-chip-/)).toBeNull();
	});
});

describe("SuelosBreakdown · class color chips", () => {
	it("paints each soil chip with getSoilColor, the overlay's palette", () => {
		renderWithMantine(
			<SuelosBreakdown
				dataset={dataset([
					{ clase: "II", ha: 30, pct: 50 },
					{ clase: "IV", ha: 20, pct: 30 },
					{ clase: "sin clasificar", ha: 10, pct: 20 },
				])}
			/>,
		);

		for (const clase of ["II", "IV", "sin clasificar"]) {
			expect(screen.getByTestId(`ficha-suelos-chip-${clase}`)).toHaveAttribute(
				"data-chip-color",
				getSoilColor(clase),
			);
		}
	});

	it("keeps the detalle tooltip trigger next to the chip", () => {
		renderWithMantine(
			<SuelosBreakdown
				dataset={dataset([
					{ clase: "III", ha: 10, pct: 100, detalle: "Suelo franco" },
				])}
			/>,
		);

		expect(screen.getByTestId("ficha-suelos-chip-III")).toBeInTheDocument();
		expect(screen.getByText("III")).toBeInTheDocument();
	});
});
