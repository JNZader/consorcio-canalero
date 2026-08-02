/**
 * useFichaOverlayTabs.test.tsx
 *
 * The state behind the ficha dataset tabs and the class filter (T3b).
 *
 * These rules are only correct together, which is why they live in one hook:
 *   - the tab drives the painted dataset, and "Lluvia" pauses the paint WITHOUT
 *     discarding the user's ON/OFF intent;
 *   - class visibility is per-dataset and per-selection, so it RESETS on a tab
 *     change and on a new analyzed zone;
 *   - toggling a class while the overlay is off turns it on (clicking a class is
 *     an unambiguous "show me this");
 *   - `visibleClases` is `null` while nothing is hidden, so the untouched path
 *     writes no filter at all.
 */

import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useFichaOverlayTabs } from "../../src/components/map2d/useFichaOverlayTabs";
import type { FichaDataset, FichaResponse } from "../../src/lib/api/ficha";

function dataset(clases: FichaDataset["clases"]): FichaDataset {
	return {
		cobertura: "total",
		clases,
		pixel_count: 5000,
		low_confidence: false,
		cobertura_ratio: 1,
	};
}

const FICHA: FichaResponse = {
	tipo: "parcela",
	area_ha: 100,
	suelos: dataset([
		{ clase: "II", ha: 40, pct: 40 },
		{ clase: "IV", ha: 60, pct: 60 },
	]),
	flood_risk: dataset([
		{ clase: "Bajo", ha: 30, pct: 30 },
		{ clase: "Alto", ha: 70, pct: 70 },
	]),
	drainage_need: dataset([{ clase: "Bajo", ha: 100, pct: 100 }]),
	precipitacion_mensual: {
		cobertura: "total",
		low_confidence: false,
		pixel_count: 10,
		cobertura_ratio: 1,
		unidad: "mm",
		serie: [],
		anual_mm: 800,
	},
};

function setup(selectionKey = "parcela|110123") {
	return renderHook(
		({ key }: { key: string }) =>
			useFichaOverlayTabs({ selectionKey: key, ficha: FICHA }),
		{ initialProps: { key: selectionKey } },
	);
}

describe("useFichaOverlayTabs · the tab drives the paint", () => {
	it("starts on soils, overlay off, nothing filtered", () => {
		const { result } = setup();

		expect(result.current.tab).toBe("suelos");
		expect(result.current.overlayDataset).toBe("suelos");
		expect(result.current.overlayVisible).toBe(false);
		expect(result.current.overlayEnabled).toBe(false);
		expect(result.current.hiddenClases).toEqual([]);
		// `null`, not an all-inclusive list: the map gets no filter written at all.
		expect(result.current.visibleClases).toBeNull();
	});

	it("follows the tab into the other class datasets", () => {
		const { result } = setup();

		act(() => result.current.changeTab("flood_risk"));

		expect(result.current.tab).toBe("flood_risk");
		expect(result.current.overlayDataset).toBe("flood_risk");
	});

	it("KEEPS the last painted dataset while the rainfall tab is open", () => {
		const { result } = setup();
		act(() => result.current.setOverlayVisible(true));
		act(() => result.current.changeTab("drainage_need"));

		act(() => result.current.changeTab("precipitacion"));

		// Nothing is painted…
		expect(result.current.overlayEnabled).toBe(false);
		// …but the intent AND the dataset survive, so going back repaints what was
		// painted instead of silently falling back to soils.
		expect(result.current.overlayVisible).toBe(true);
		expect(result.current.overlayDataset).toBe("drainage_need");

		act(() => result.current.changeTab("drainage_need"));
		expect(result.current.overlayEnabled).toBe(true);
	});
});

describe("useFichaOverlayTabs · class visibility", () => {
	it("hides a class, then shows it again on a second toggle", () => {
		const { result } = setup();
		act(() => result.current.changeTab("flood_risk"));

		act(() => result.current.toggleClase("Alto"));
		expect(result.current.hiddenClases).toEqual(["Alto"]);
		expect(result.current.visibleClases).toEqual(["Bajo"]);

		act(() => result.current.toggleClase("Alto"));
		expect(result.current.hiddenClases).toEqual([]);
		expect(result.current.visibleClases).toBeNull();
	});

	it("turns the overlay ON when a class is toggled while it was off", () => {
		const { result } = setup();
		expect(result.current.overlayVisible).toBe(false);

		act(() => result.current.toggleClase("IV"));

		expect(result.current.overlayVisible).toBe(true);
		expect(result.current.overlayEnabled).toBe(true);
	});

	it("resolves visible classes against the ACTIVE dataset table", () => {
		const { result } = setup();
		act(() => result.current.changeTab("flood_risk"));

		act(() => result.current.toggleClase("Bajo"));

		// Soils classes (II / IV) never leak into a flood_risk filter.
		expect(result.current.visibleClases).toEqual(["Alto"]);
	});

	it("yields an EMPTY list when every class is off (paints nothing)", () => {
		const { result } = setup();
		act(() => result.current.changeTab("flood_risk"));

		act(() => result.current.toggleClase("Bajo"));
		act(() => result.current.toggleClase("Alto"));

		expect(result.current.visibleClases).toEqual([]);
		expect(result.current.overlayEnabled).toBe(true);
	});

	it("RESETS visibility on a tab change (classes are per-dataset)", () => {
		const { result } = setup();
		act(() => result.current.changeTab("flood_risk"));
		act(() => result.current.toggleClase("Alto"));
		expect(result.current.hiddenClases).toEqual(["Alto"]);

		act(() => result.current.changeTab("suelos"));

		// "Alto" means nothing among soil capability classes — carrying it over
		// would be a silent no-op filter at best.
		expect(result.current.hiddenClases).toEqual([]);
		expect(result.current.visibleClases).toBeNull();
	});

	it("RESETS visibility on a new selection, keeping tab and overlay intent", () => {
		const { result, rerender } = setup("parcela|110123");
		act(() => result.current.changeTab("flood_risk"));
		act(() => result.current.toggleClase("Alto"));

		rerender({ key: "parcela|999999" });

		// A new analysis has different classes over different areas: it must not
		// open with part of it already hidden.
		expect(result.current.hiddenClases).toEqual([]);
		expect(result.current.visibleClases).toBeNull();
		// The lens the user chose is theirs to keep, and so is the overlay switch.
		expect(result.current.tab).toBe("flood_risk");
		expect(result.current.overlayVisible).toBe(true);
	});

	it("writes NO filter when the active dataset has no class table", () => {
		const { result } = renderHook(() =>
			useFichaOverlayTabs({ selectionKey: "parcela|1", ficha: undefined }),
		);

		act(() => result.current.toggleClase("IV"));

		// No table = no legend = no filter. Deriving one would leave an empty
		// visible list, i.e. a blank map, from a label with no row on screen.
		expect(result.current.hiddenClases).toEqual(["IV"]);
		expect(result.current.visibleClases).toBeNull();
	});

	it("does NOT reset when the same selection re-renders", () => {
		const { result, rerender } = setup("parcela|110123");
		act(() => result.current.toggleClase("IV"));

		rerender({ key: "parcela|110123" });

		expect(result.current.hiddenClases).toEqual(["IV"]);
	});

	it("resets a SHARED label across datasets: Alto hidden on flood_risk is painted on drainage_need", () => {
		// Bajo/Medio/Alto/Critico exist in BOTH risk datasets. This pins the real
		// hazard: a future "keep hidden classes that exist in the new dataset"
		// refactor would silently carry flood's hidden Alto into drainage.
		const { result } = setup();
		act(() => result.current.changeTab("flood_risk"));
		act(() => result.current.toggleClase("Alto"));
		expect(result.current.hiddenClases).toContain("Alto");
		act(() => result.current.changeTab("drainage_need"));
		expect(result.current.hiddenClases).toHaveLength(0);
	});
});
