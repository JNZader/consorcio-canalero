/**
 * useFichaInteraction — the ONE interaction-mode coordinator (A5.2, JDB-012).
 *
 * Pins the invariants the design mandates without mounting a map:
 *   - starting a drawing DISCARDS the previous parcel ficha (spec "Switching
 *     modes discards previous result") and cancels measurement (mutual exclusion);
 *   - a completed polygon fires a `tipo=poligono` request and stays in draw mode;
 *   - the derived `interactionMode` is the single machine: `ficha-dibujo` while
 *     drawing, otherwise it passes the measurement mode straight through;
 *   - a parcel click is ignored WHILE drawing (DrawControl owns clicks) and
 *     supersedes a drawn ficha otherwise.
 */

import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { DrawnPolygon } from "../../src/components/map/DrawControl";
import { useFichaInteraction } from "../../src/components/map2d/useFichaInteraction";

const PARCELA = {
	nomenclatura: "13-06-01-0203",
	nroCuenta: "110123",
	props: {
		nomenclatura: "13-06-01-0203",
		nroCuenta: "110123",
		desigOficial: "Lote 4",
		superficieHa: "25.4",
		departamento: "General San Martín",
		pedania: "Arroyo Algodón",
		tipoParcela: "rural",
	},
};
const POLY: DrawnPolygon = {
	type: "Polygon",
	coordinates: [
		[
			[-62, -32],
			[-62, -32.1],
			[-61.9, -32.1],
			[-62, -32],
		],
	],
};

describe("useFichaInteraction", () => {
	it("starts idle: no request, mode mirrors the measurement mode", () => {
		const { result } = renderHook(() => useFichaInteraction("idle", vi.fn()));
		expect(result.current.request).toBeNull();
		expect(result.current.interactionMode).toBe("idle");
		expect(result.current.state.drawing).toBe(false);
	});

	it("passes the measurement mode through when not drawing (one machine)", () => {
		const { result } = renderHook(() =>
			useFichaInteraction("measuring-area", vi.fn()),
		);
		expect(result.current.interactionMode).toBe("measuring-area");
	});

	it("starting a drawing DISCARDS the previous parcel ficha and cancels measurement", () => {
		const onEnterDraw = vi.fn();
		const { result } = renderHook(() =>
			useFichaInteraction("idle", onEnterDraw),
		);

		// A parcel is selected first (a prior click).
		act(() => result.current.resolveParcela(PARCELA));
		expect(result.current.request).toEqual({
			tipo: "parcela",
			nomenclatura: PARCELA.nomenclatura,
		});

		// Entering draw mode wipes it and cancels any live measurement.
		act(() => result.current.startDraw());
		expect(onEnterDraw).toHaveBeenCalledTimes(1);
		expect(result.current.state.drawing).toBe(true);
		expect(result.current.interactionMode).toBe("ficha-dibujo");
		expect(result.current.request).toBeNull(); // previous parcel ficha discarded
		expect(result.current.nroCuenta).toBeNull();
	});

	it("a completed polygon fires a tipo=poligono request and keeps the draw session", () => {
		const { result } = renderHook(() => useFichaInteraction("idle", vi.fn()));
		act(() => result.current.startDraw());
		act(() => result.current.completePolygon(POLY));

		expect(result.current.request).toEqual({
			tipo: "poligono",
			geometry: POLY,
		});
		expect(result.current.tipo).toBe("poligono");
		expect(result.current.state.drawing).toBe(true); // shape stays visible while its ficha shows
		// T4 — MapboxDraw already went back to `simple_select`, so click ownership
		// is released too and the map stops being dead.
		expect(result.current.state.tracing).toBe(false);
		expect(result.current.interactionMode).toBe("idle");
	});

	it("ignores a parcel click WHILE TRACING (DrawControl owns clicks)", () => {
		const { result } = renderHook(() => useFichaInteraction("idle", vi.fn()));
		act(() => result.current.startDraw());

		act(() => result.current.resolveParcela(PARCELA)); // a stray click mid-trace
		expect(result.current.state.parcelas).toEqual([]);
		expect(result.current.request).toBeNull();
	});

	it("T4 — a parcel click AFTER the polygon is finished supersedes it and ends the session", () => {
		const { result } = renderHook(() => useFichaInteraction("idle", vi.fn()));
		act(() => result.current.startDraw());
		act(() => result.current.completePolygon(POLY));

		act(() => result.current.resolveParcela(PARCELA));

		expect(result.current.request).toEqual({
			tipo: "parcela",
			nomenclatura: PARCELA.nomenclatura,
		});
		expect(result.current.state.drawing).toBe(false);
		expect(result.current.state.poligono).toBeNull();
	});

	it("T4 — redrawPolygon re-arms tracing while keeping the current ficha on screen", () => {
		const { result } = renderHook(() => useFichaInteraction("idle", vi.fn()));
		act(() => result.current.startDraw());
		act(() => result.current.completePolygon(POLY));

		act(() => result.current.redrawPolygon());

		expect(result.current.state.tracing).toBe(true);
		expect(result.current.interactionMode).toBe("ficha-dibujo");
		// The previous polygon (and its ficha) survives until `draw.create` replaces it.
		expect(result.current.request).toEqual({ tipo: "poligono", geometry: POLY });

		// And clicks are owned by MapboxDraw again.
		act(() => result.current.resolveParcela(PARCELA));
		expect(result.current.request).toEqual({ tipo: "poligono", geometry: POLY });
	});

	it("T4 — an ADDITIVE click after the polygon is finished also closes the session", () => {
		// Regression: the additive branch dropped `poligono` but kept
		// `drawing: true`, so DrawControl stayed mounted and MapboxDraw went on
		// painting a polygon nothing in React owned.
		const { result } = renderHook(() => useFichaInteraction("idle", vi.fn()));
		act(() => result.current.startDraw());
		act(() => result.current.completePolygon(POLY));

		act(() => result.current.resolveParcela(PARCELA, true));

		expect(result.current.state.poligono).toBeNull();
		expect(result.current.state.drawing).toBe(false);
		expect(result.current.state.tracing).toBe(false);
		expect(result.current.state.parcelas).toEqual([PARCELA.nomenclatura]);
	});

	it("T4 — the sticky multiSelect toggle closes the session too (no ctrl on touch)", () => {
		const { result } = renderHook(() => useFichaInteraction("idle", vi.fn()));
		act(() => result.current.setMultiSelect(true));
		act(() => result.current.startDraw());
		act(() => result.current.completePolygon(POLY));

		// `startDraw` rebuilds from IDLE, so re-arm the touch toggle first.
		act(() => result.current.setMultiSelect(true));
		act(() => result.current.resolveParcela(PARCELA));

		expect(result.current.state.poligono).toBeNull();
		expect(result.current.state.drawing).toBe(false);
	});

	it("T4 — redrawPolygon is a no-op outside a draw session", () => {
		const { result } = renderHook(() => useFichaInteraction("idle", vi.fn()));
		act(() => result.current.redrawPolygon());
		expect(result.current.state.tracing).toBe(false);
		expect(result.current.interactionMode).toBe("idle");
	});

	it("a fresh parcel click supersedes a drawn ficha once drawing has stopped", () => {
		const { result } = renderHook(() => useFichaInteraction("idle", vi.fn()));
		act(() => result.current.startDraw());
		act(() => result.current.completePolygon(POLY));
		act(() => result.current.stopDraw()); // leave draw mode → everything cleared

		expect(result.current.request).toBeNull();

		act(() => result.current.resolveParcela(PARCELA));
		expect(result.current.request).toEqual({
			tipo: "parcela",
			nomenclatura: PARCELA.nomenclatura,
		});
		expect(result.current.nroCuenta).toBe("110123");
	});

	it("exposes the parcel display props (for the ficha identity header)", () => {
		const { result } = renderHook(() => useFichaInteraction("idle", vi.fn()));
		expect(result.current.parcelaProps).toBeNull();

		act(() => result.current.resolveParcela(PARCELA));
		expect(result.current.parcelaProps).toEqual(PARCELA.props);

		act(() => result.current.clearFicha());
		expect(result.current.parcelaProps).toBeNull();
	});

	it("stopDraw and clearFicha reset to idle", () => {
		const { result } = renderHook(() => useFichaInteraction("idle", vi.fn()));
		act(() => result.current.startDraw());
		act(() => result.current.stopDraw());
		expect(result.current.state.drawing).toBe(false);
		expect(result.current.request).toBeNull();

		act(() => result.current.resolveParcela(PARCELA));
		act(() => result.current.clearFicha());
		expect(result.current.request).toBeNull();
	});

	it("deletePolygon clears the drawn ficha without leaving draw mode", () => {
		const { result } = renderHook(() => useFichaInteraction("idle", vi.fn()));
		act(() => result.current.startDraw());
		act(() => result.current.completePolygon(POLY));
		act(() => result.current.deletePolygon());
		expect(result.current.request).toBeNull();
		expect(result.current.state.drawing).toBe(true);
	});
});

const CANAL_A = { ref: "canal-a", nombre: "Canal A" };
const CANAL_B = { ref: "canal-b", nombre: "Canal B" };

describe("useFichaInteraction · canal analysis (A6 + A7)", () => {
	it("entering canal mode derives ficha-canal and cancels measurement, no request yet", () => {
		const onEnterDraw = vi.fn();
		const { result } = renderHook(() =>
			useFichaInteraction("measuring-distance", onEnterDraw),
		);

		act(() => result.current.startCanal());
		expect(onEnterDraw).toHaveBeenCalledTimes(1); // measurement cancelled
		expect(result.current.state.canalMode).toBe(true);
		expect(result.current.interactionMode).toBe("ficha-canal");
		expect(result.current.request).toBeNull(); // no canal clicked yet
	});

	it("resolving a curated canal fires a tipo=canal_buffer request with canal_ref + default buffer", () => {
		const { result } = renderHook(() => useFichaInteraction("idle", vi.fn()));
		act(() => result.current.startCanal());
		act(() => result.current.resolveCanal(CANAL_A));

		expect(result.current.request).toEqual({
			tipo: "canal_buffer",
			canal_ref: "canal-a",
			buffer_m: 500,
		});
		expect(result.current.tipo).toBe("canal_buffer");
		expect(result.current.state.canal).toEqual({
			canalRef: "canal-a",
			canalNombre: "Canal A",
			bufferM: 500,
			analysisMode: "buffer",
		});
	});

	it("setBuffer re-fires the request with the new distance, keeping the canal", () => {
		const { result } = renderHook(() => useFichaInteraction("idle", vi.fn()));
		act(() => result.current.startCanal());
		act(() => result.current.resolveCanal(CANAL_A));
		act(() => result.current.setBuffer(1200));

		expect(result.current.request).toEqual({
			tipo: "canal_buffer",
			canal_ref: "canal-a",
			buffer_m: 1200,
		});
	});

	it("switching to Cuenca fires a tipo=canal_cuenca request (variante natural), same canal_ref", () => {
		const { result } = renderHook(() => useFichaInteraction("idle", vi.fn()));
		act(() => result.current.startCanal());
		act(() => result.current.resolveCanal(CANAL_A));
		act(() => result.current.setCanalAnalysisMode("cuenca"));

		expect(result.current.request).toEqual({
			tipo: "canal_cuenca",
			canal_ref: "canal-a",
			variante: "natural",
		});
		expect(result.current.tipo).toBe("canal_cuenca");
	});

	it("switching back to Zona de influencia restores the canal_buffer request", () => {
		const { result } = renderHook(() => useFichaInteraction("idle", vi.fn()));
		act(() => result.current.startCanal());
		act(() => result.current.resolveCanal(CANAL_A));
		act(() => result.current.setBuffer(900));
		act(() => result.current.setCanalAnalysisMode("cuenca"));
		act(() => result.current.setCanalAnalysisMode("buffer"));

		expect(result.current.request).toEqual({
			tipo: "canal_buffer",
			canal_ref: "canal-a",
			buffer_m: 900,
		});
	});

	it("picking another canal keeps the buffer AND the analysis mode the user chose", () => {
		const { result } = renderHook(() => useFichaInteraction("idle", vi.fn()));
		act(() => result.current.startCanal());
		act(() => result.current.resolveCanal(CANAL_A));
		act(() => result.current.setBuffer(800));
		act(() => result.current.setCanalAnalysisMode("cuenca"));
		act(() => result.current.resolveCanal(CANAL_B)); // click a different canal

		// Cuenca mode carries over → the new canal is analyzed as a catchment too.
		expect(result.current.request).toEqual({
			tipo: "canal_cuenca",
			canal_ref: "canal-b",
			variante: "natural",
		});
		expect(result.current.state.canal?.bufferM).toBe(800); // buffer preserved for a later switch
	});

	it("setBuffer / setCanalAnalysisMode are no-ops before any canal is selected", () => {
		const { result } = renderHook(() => useFichaInteraction("idle", vi.fn()));
		act(() => result.current.startCanal());
		act(() => result.current.setBuffer(1500));
		act(() => result.current.setCanalAnalysisMode("cuenca"));
		expect(result.current.request).toBeNull();
		expect(result.current.state.canal).toBeNull();
	});

	it("starting canal mode DISCARDS a previous parcel ficha", () => {
		const { result } = renderHook(() => useFichaInteraction("idle", vi.fn()));
		act(() => result.current.resolveParcela(PARCELA));
		expect(result.current.tipo).toBe("parcela");

		act(() => result.current.startCanal());
		expect(result.current.request).toBeNull(); // parcel ficha gone
		expect(result.current.state.parcela).toBeNull();
	});

	it("a parcel click is IGNORED while in canal mode (canal owns clicks)", () => {
		const { result } = renderHook(() => useFichaInteraction("idle", vi.fn()));
		act(() => result.current.startCanal());
		act(() => result.current.resolveCanal(CANAL_A));
		act(() => result.current.resolveParcela(PARCELA)); // stray parcel resolution
		expect(result.current.request).toEqual({
			tipo: "canal_buffer",
			canal_ref: "canal-a",
			buffer_m: 500,
		});
	});

	it("startDraw and startCanal are mutually exclusive (one machine)", () => {
		const { result } = renderHook(() => useFichaInteraction("idle", vi.fn()));
		act(() => result.current.startCanal());
		act(() => result.current.resolveCanal(CANAL_A));
		expect(result.current.interactionMode).toBe("ficha-canal");

		act(() => result.current.startDraw()); // switch to drawing
		expect(result.current.state.canalMode).toBe(false);
		expect(result.current.state.canal).toBeNull();
		expect(result.current.interactionMode).toBe("ficha-dibujo");
		expect(result.current.request).toBeNull();
	});

	it("stopCanal resets to idle", () => {
		const { result } = renderHook(() => useFichaInteraction("idle", vi.fn()));
		act(() => result.current.startCanal());
		act(() => result.current.resolveCanal(CANAL_A));
		act(() => result.current.stopCanal());
		expect(result.current.state.canalMode).toBe(false);
		expect(result.current.request).toBeNull();
		expect(result.current.interactionMode).toBe("idle");
	});

	it("resolveCanal(null) clears the selection but stays in canal mode", () => {
		const { result } = renderHook(() => useFichaInteraction("idle", vi.fn()));
		act(() => result.current.startCanal());
		act(() => result.current.resolveCanal(CANAL_A));
		act(() => result.current.resolveCanal(null)); // click missed a canal
		expect(result.current.request).toBeNull();
		expect(result.current.state.canalMode).toBe(true);
	});
});
