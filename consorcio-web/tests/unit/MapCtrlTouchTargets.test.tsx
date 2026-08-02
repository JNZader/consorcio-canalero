/**
 * MapCtrlTouchTargets.test.tsx
 *
 * Touch targets + labels on the custom map controls (map-fluidity T2, fix 2).
 *
 * The buttons used to hard-code `width: 29, height: 29` INLINE, which no media
 * query can reach: they were stuck under the 44px WCAG 2.5.5 target on touch,
 * and their only label was a hover-only tooltip. Sizing, the dock offsets and
 * the coarse-pointer label now live in `map.module.css`, so these assertions are
 * class-level (happy-dom does not evaluate `@media (pointer: coarse)`).
 */

import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";

import { MapActionsPanel } from "../../src/components/map2d/MapActionsPanel";
import { MeasurementToolbar } from "../../src/components/map2d/measurement/MeasurementToolbar";

/** The stylesheet source. happy-dom evaluates no `@media`, and CSS Modules give
 * the test no computed geometry at all, so the coarse-pointer LAYOUT contract is
 * asserted against the source text + arithmetic instead of a rendered box. */
const MAP_CSS = readFileSync(
	resolve(process.cwd(), "src/styles/components/map.module.css"),
	"utf-8",
);

/** The `@media (pointer: coarse)` block (the one WITHOUT a width qualifier). */
function coarseBlock(): string {
	const start = MAP_CSS.indexOf("@media (pointer: coarse) {");
	expect(start).toBeGreaterThan(-1);
	let depth = 0;
	for (let i = MAP_CSS.indexOf("{", start); i < MAP_CSS.length; i += 1) {
		if (MAP_CSS[i] === "{") depth += 1;
		if (MAP_CSS[i] === "}") {
			depth -= 1;
			if (depth === 0) return MAP_CSS.slice(start, i + 1);
		}
	}
	throw new Error("unterminated @media (pointer: coarse) block");
}

/** `.selector { … prop: 123px … }` → 123, inside the given CSS text. */
function pxOf(css: string, selector: string, prop: string): number {
	const rule = new RegExp(`\\.${selector}\\s*\\{([^}]*)\\}`).exec(css);
	expect(rule, `${selector} rule`).not.toBeNull();
	const value = new RegExp(`${prop}:\\s*(-?[\\d.]+)px`).exec(
		rule?.[1] ?? "",
	)?.[1];
	expect(value, `${selector}.${prop}`).toBeDefined();
	return Number(value);
}

function renderWithMantine(ui: ReactNode) {
	return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

const toolbarProps = {
	mode: "idle" as const,
	hasMeasurements: false,
	onStartDistance: () => {},
	onStartArea: () => {},
	onClear: () => {},
};

describe("map control touch targets", () => {
	it("MapActionsPanel: the Exportar button opts into the coarse-pointer sizing class", () => {
		renderWithMantine(
			<MapActionsPanel
				hasApprovedZones={false}
				onOpenExportPng={() => {}}
				onExportApprovedZonesPdf={() => {}}
			/>,
		);

		const button = screen.getByRole("button", { name: "Exportar" });
		expect(button.className).toContain("mapCtrlButton");
		// The inline 29×29 box is gone — CSS owns the size at both pointer types.
		expect(button.style.width).toBe("");
		expect(button.style.height).toBe("");
	});

	it("MapActionsPanel: the dock offset is a class, so the coarse column can shift", () => {
		const { container } = renderWithMantine(
			<MapActionsPanel
				hasApprovedZones={false}
				onOpenExportPng={() => {}}
				onExportApprovedZonesPdf={() => {}}
			/>,
		);

		const dock = container.querySelector(
			".maplibregl-ctrl-group",
		) as HTMLElement;
		expect(dock.className).toContain("mapCtrlDock");
		expect(dock.className).toContain("mapActionsDock");
		expect(dock.style.top).toBe("");
	});

	it("MeasurementToolbar: every button opts into the coarse-pointer sizing class", () => {
		renderWithMantine(
			<MeasurementToolbar
				{...toolbarProps}
				hasMeasurements
				onToggleFichaDraw={() => {}}
				onToggleFichaCanal={() => {}}
			/>,
		);

		for (const name of [
			"Medir",
			"Dibujar polígono",
			"Seleccionar canal",
			"Limpiar mediciones",
		]) {
			const button = screen.getByRole("button", { name });
			expect(button.className).toContain("mapCtrlButton");
			expect(button.style.width).toBe("");
			expect(button.style.height).toBe("");
		}
	});

	it("MeasurementToolbar: the dock offset is a class", () => {
		const { container } = renderWithMantine(
			<MeasurementToolbar {...toolbarProps} />,
		);

		const dock = container.querySelector(
			".maplibregl-ctrl-group",
		) as HTMLElement;
		expect(dock.className).toContain("mapCtrlDock");
		expect(dock.className).toContain("measurementDock");
		expect(dock.style.top).toBe("");
	});

	it("renders a compact text label per button, revealed only on coarse pointers", () => {
		renderWithMantine(
			<MeasurementToolbar
				{...toolbarProps}
				hasMeasurements
				onToggleFichaDraw={() => {}}
				onToggleFichaCanal={() => {}}
			/>,
		);

		const expected: Array<[string, string]> = [
			["Medir", "Medir"],
			["Dibujar polígono", "Dibujar"],
			["Seleccionar canal", "Canal"],
			["Limpiar mediciones", "Limpiar"],
		];

		for (const [accessibleName, labelText] of expected) {
			const label = screen
				.getByRole("button", { name: accessibleName })
				.querySelector('[class*="mapCtrlButtonLabel"]') as HTMLElement;
			expect(label).not.toBeNull();
			expect(label.textContent).toBe(labelText);
		}
	});

	it("the exit button label follows its dual meaning (limpiar vs cancelar)", () => {
		renderWithMantine(
			<MeasurementToolbar
				{...toolbarProps}
				mode="measuring-distance"
				hasMeasurements={false}
				onCancel={() => {}}
			/>,
		);

		const label = screen
			.getByRole("button", { name: "Cancelar medición" })
			.querySelector('[class*="mapCtrlButtonLabel"]') as HTMLElement;
		expect(label.textContent).toBe("Cancelar");
	});

	it("MeasurementToolbar: the stack direction is a class, not an inline style", () => {
		const { container } = renderWithMantine(
			<MeasurementToolbar {...toolbarProps} />,
		);

		// It has to be a class: the coarse breakpoint flips it column → row, and a
		// media query cannot reach an inline `flexDirection`.
		const group = container.querySelector(
			'[class*="measurementGroup"]',
		) as HTMLElement;
		expect(group).not.toBeNull();
		expect(group.style.flexDirection).toBe("");
	});

	it("MapActionsPanel: the Exportar button carries its coarse-pointer label", () => {
		renderWithMantine(
			<MapActionsPanel
				hasApprovedZones={false}
				onOpenExportPng={() => {}}
				onExportApprovedZonesPdf={() => {}}
			/>,
		);

		const label = screen
			.getByRole("button", { name: "Exportar" })
			.querySelector('[class*="mapCtrlButtonLabel"]') as HTMLElement;
		expect(label.textContent).toBe("Exportar");
	});
});

/**
 * Coarse-pointer LAYOUT contract (fixes R3-001 / R3-002).
 *
 * Growing every control to 44px pushed the right-hand column past the canvas:
 * the narrow-viewport canvas floor is 380px with `overflow: hidden`, and a
 * measurement toolbar stacked at top:260 with four 44px buttons ends at 436 —
 * the last two clipped off-canvas entirely. These assertions pin the arithmetic
 * so a future offset bump cannot silently re-introduce the clip.
 */
describe("coarse-pointer control layout fits the 380px canvas", () => {
	/** `clamp(380px, …)` — the narrow-viewport canvas floor, `overflow: hidden`. */
	const CANVAS_FLOOR = 380;
	/** WCAG 2.5.5 target size, what every control grows to on a coarse pointer. */
	const TOUCH = 44;

	it("declares the 380px floor this budget is derived from", () => {
		expect(MAP_CSS).toContain("--map-canvas-height: clamp(380px");
		expect(MAP_CSS).toMatch(/\.mapCanvasWrapper\s*\{[^}]*overflow:\s*hidden/);
	});

	it("the right-hand column ends above the floor", () => {
		const coarse = coarseBlock();
		// nav 3×44 from top:10 → 142 · +10 → fullscreen 152–196 · +10 → actions.
		const navBottom = 10 + 3 * TOUCH;
		const fullscreenBottom = navBottom + 10 + TOUCH;
		const actionsTop = pxOf(coarse, "mapActionsDock", "top");

		expect(actionsTop).toBeGreaterThanOrEqual(fullscreenBottom + 10);
		expect(actionsTop + TOUCH).toBeLessThanOrEqual(CANVAS_FLOOR);
	});

	it("the measurement toolbar leaves the column for a horizontal bottom row", () => {
		const coarse = coarseBlock();
		const dock = /\.measurementDock\s*\{([^}]*)\}/.exec(coarse)?.[1] ?? "";

		// Unpinned from the top/right column…
		expect(dock).toMatch(/top:\s*auto/);
		expect(dock).toMatch(/right:\s*auto/);
		// …and re-anchored bottom-left, above the scale/attribution strip.
		const bottom = pxOf(coarse, "measurementDock", "bottom");
		const left = pxOf(coarse, "measurementDock", "left");
		expect(bottom).toBeGreaterThan(0);
		expect(left).toBeGreaterThanOrEqual(0);

		// Laid out as a ROW, so its 4 buttons consume width, not the vertical
		// budget. Had it stayed a column at its old top:260 the stack would end at
		// 260 + 4×44 = 436 > 380 — two buttons clipped.
		expect(/\.measurementGroup\s*\{[^}]*flex-direction:\s*row/.test(coarse)).toBe(
			true,
		);
		expect(260 + 4 * TOUCH).toBeGreaterThan(CANVAS_FLOOR); // the bug being fixed
		expect(bottom + TOUCH).toBeLessThanOrEqual(CANVAS_FLOOR);
	});

	it("sits BELOW the bottom sheet, which is the documented collision choice", () => {
		// `.panelSheet` (z-index 1000) also anchors bottom and covers this toolbar
		// while a sheet is open. Accepted: the modes it drives need map
		// interaction, which the open sheet already blocks.
		expect(/\.mapCtrlDock\s*\{[^}]*z-index:\s*16/.test(MAP_CSS)).toBe(true);
		expect(/\.panelSheet\s*\{[^}]*z-index:\s*1000/.test(MAP_CSS)).toBe(true);
	});

	it("MapLibre's 44px square rule EXCLUDES our labeled custom buttons", () => {
		const coarse = coarseBlock();
		// The `:global(...) button` selector outspecifies `.mapCtrlButton`, so
		// without `:not(.mapCtrlButton)` it pinned width:44px and the visible
		// touch labels ("Exportar", "Cancelar"…) overflowed a fixed box.
		expect(coarse).toContain(
			":global(.maplibregl-ctrl-group) button:not(.mapCtrlButton)",
		);
		// The old, over-broad selector is gone.
		expect(coarse).not.toContain(":global(.maplibregl-ctrl-group button)");
		// …and our own buttons keep their content-driven width.
		expect(coarse).toMatch(
			/\.mapCtrlButton\s*\{[^}]*width:\s*auto[^}]*min-width:\s*44px/,
		);
	});
});
