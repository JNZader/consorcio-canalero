/**
 * useFichaInteraction — MULTI-PARCEL selection (T4).
 *
 * Pins the accumulate/replace contract without mounting a map:
 *   - a plain click REPLACES the selection (pre-T4 behaviour, unchanged);
 *   - a ctrl-click (`additive`) ADDS a parcel, and re-clicking a selected one
 *     REMOVES it — the only deselect affordance the map offers;
 *   - 2+ parcels fire `tipo=parcelas` with SORTED nomenclaturas, 1 falls back to
 *     `tipo=parcela`, so there is never a one-element multi request;
 *   - the touch "selección múltiple" mode makes every tap additive;
 *   - identity/BPA fields are single-parcel only — a union has no account;
 *   - entering draw/canal mode discards the whole selection.
 *
 * SETTLING (fix round). A multi-parcel request is DEBOUNCED: the selection (and
 * therefore the map highlight) moves on every click, but the wire REQUEST only
 * advances once the selection has been idle for `FICHA_PARCELAS_SETTLE_MS`.
 * Every assertion about `request` in a multi selection therefore has to say WHEN
 * it is being made — which is the point: before this, six ctrl-clicks bought six
 * server-side unions and threw five of them away.
 */

import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
	FICHA_PARCELAS_SETTLE_MS,
	useFichaInteraction,
} from "../../src/components/map2d/useFichaInteraction";
import { FICHA_PARCELAS_MAX } from "../../src/lib/api/ficha";
import type { ParcelaResuelta } from "../../src/components/map2d/useMapInteractionEffects";

function parcela(nomenclatura: string, nroCuenta = "110123"): ParcelaResuelta {
	return {
		nomenclatura,
		nroCuenta,
		props: {
			nomenclatura,
			nroCuenta,
			desigOficial: "Lote 4",
			superficieHa: "25.4",
			departamento: "General San Martín",
			pedania: "Arroyo Algodón",
			tipoParcela: "rural",
		},
	};
}

const A = parcela("13-06-01-0201");
const B = parcela("13-06-01-0202", "110222");
const C = parcela("13-06-01-0203");
const D = parcela("13-06-01-0204");

function setup(onCapReached?: () => void) {
	return renderHook(() => useFichaInteraction("idle", vi.fn(), onCapReached));
}

/** Let a multi-parcel selection settle so its request is derived. */
function settle() {
	act(() => {
		vi.advanceTimersByTime(FICHA_PARCELAS_SETTLE_MS);
	});
}

beforeEach(() => {
	vi.useFakeTimers();
});

afterEach(() => {
	vi.useRealTimers();
});

describe("useFichaInteraction — multi-parcel selection (T4)", () => {
	it("a plain click selects ONE parcel and fires tipo=parcela IMMEDIATELY", () => {
		const { result } = setup();
		act(() => result.current.resolveParcela(A));

		// No timer advance: a single parcel is the pre-T4 interaction and one cheap
		// analysis, so debouncing it would only make the map feel slower.
		expect(result.current.state.parcelas).toEqual([A.nomenclatura]);
		expect(result.current.tipo).toBe("parcela");
		expect(result.current.request).toEqual({
			tipo: "parcela",
			nomenclatura: A.nomenclatura,
		});
	});

	it("a ctrl-click ACCUMULATES and fires tipo=parcelas with sorted nomenclaturas", () => {
		const { result } = setup();
		// Click the LATER one first: the request must still come out sorted, because
		// the identity of a selection is its set, not the order it was built in.
		act(() => result.current.resolveParcela(C));
		act(() => result.current.resolveParcela(A, true));
		settle();

		expect(result.current.state.parcelas).toEqual([
			A.nomenclatura,
			C.nomenclatura,
		]);
		expect(result.current.tipo).toBe("parcelas");
		expect(result.current.request).toEqual({
			tipo: "parcelas",
			nomenclaturas: [A.nomenclatura, C.nomenclatura],
		});
	});

	it("a ctrl-click on an ALREADY selected parcel removes it", () => {
		const { result } = setup();
		act(() => result.current.resolveParcela(A));
		act(() => result.current.resolveParcela(B, true));
		act(() => result.current.resolveParcela(C, true));
		expect(result.current.state.parcelas).toHaveLength(3);

		act(() => result.current.resolveParcela(B, true));
		settle();

		expect(result.current.state.parcelas).toEqual([
			A.nomenclatura,
			C.nomenclatura,
		]);
		expect(result.current.tipo).toBe("parcelas");
	});

	it("removing down to ONE parcel falls back to tipo=parcela", () => {
		const { result } = setup();
		act(() => result.current.resolveParcela(A));
		act(() => result.current.resolveParcela(B, true));
		act(() => result.current.resolveParcela(B, true));

		expect(result.current.state.parcelas).toEqual([A.nomenclatura]);
		expect(result.current.request).toEqual({
			tipo: "parcela",
			nomenclatura: A.nomenclatura,
		});
	});

	it("removing the LAST parcel leaves no request at all", () => {
		const { result } = setup();
		act(() => result.current.resolveParcela(A));
		act(() => result.current.resolveParcela(A, true));

		expect(result.current.state.parcelas).toEqual([]);
		expect(result.current.request).toBeNull();
	});

	it("a PLAIN click after accumulating RESETS to a single selection", () => {
		const { result } = setup();
		act(() => result.current.resolveParcela(A));
		act(() => result.current.resolveParcela(B, true));

		act(() => result.current.resolveParcela(C));

		expect(result.current.state.parcelas).toEqual([C.nomenclatura]);
		expect(result.current.request).toEqual({
			tipo: "parcela",
			nomenclatura: C.nomenclatura,
		});
	});

	it("the selection REQUEST changes on every add and every remove", () => {
		// The panels reset off the selection key, which is derived from the request;
		// an add/remove that produced the same request would leave the panel showing
		// the previous area's numbers.
		const { result } = setup();
		act(() => result.current.resolveParcela(A));
		const uno = JSON.stringify(result.current.request);
		act(() => result.current.resolveParcela(B, true));
		settle();
		const dos = JSON.stringify(result.current.request);
		act(() => result.current.resolveParcela(C, true));
		settle();
		const tres = JSON.stringify(result.current.request);
		act(() => result.current.resolveParcela(C, true));
		settle();
		const otraVezDos = JSON.stringify(result.current.request);

		expect(new Set([uno, dos, tres]).size).toBe(3);
		expect(otraVezDos).toBe(dos);
	});

	// ── settling: one analysis per BURST, not per click ───────────────────────

	it("a burst of ctrl-clicks advances the request ONCE, after the selection is idle", () => {
		const { result } = setup();
		act(() => result.current.resolveParcela(A));
		const inicial = JSON.stringify(result.current.request);

		const vistos: string[] = [];
		for (const parcelaClickeada of [B, C, D]) {
			act(() => result.current.resolveParcela(parcelaClickeada, true));
			// Well inside the settle window: this is the "quick clicks" pattern that
			// used to fire one full ST_Union + raster analysis per click.
			act(() => {
				vi.advanceTimersByTime(FICHA_PARCELAS_SETTLE_MS / 3);
			});
			vistos.push(JSON.stringify(result.current.request));
		}

		// Nothing moved during the burst — the previous (single-parcel) request is
		// still the one on the wire.
		expect(new Set(vistos)).toEqual(new Set([inicial]));

		settle();
		expect(result.current.request).toEqual({
			tipo: "parcelas",
			nomenclaturas: [A, B, C, D].map((p) => p.nomenclatura).sort(),
		});
		// Exactly two request identities across the whole gesture: the single-parcel
		// one and the settled union.
		expect(
			new Set([inicial, JSON.stringify(result.current.request)]).size,
		).toBe(2);
	});

	it("the SELECTION (what the map highlights) moves on every click regardless", () => {
		const { result } = setup();
		act(() => result.current.resolveParcela(A));
		act(() => result.current.resolveParcela(B, true));
		expect(result.current.state.parcelas).toEqual([
			A.nomenclatura,
			B.nomenclatura,
		]);

		act(() => result.current.resolveParcela(C, true));
		// Still inside the settle window: the highlight already shows three parcels
		// while the analysis has not been asked for yet.
		expect(result.current.state.parcelas).toEqual([
			A.nomenclatura,
			B.nomenclatura,
			C.nomenclatura,
		]);
		expect(result.current.parcelasAnalizadas).not.toEqual(
			result.current.state.parcelas,
		);
	});

	it("a REMOVAL is debounced too (ctrl-clicking several off is one analysis)", () => {
		const { result } = setup();
		act(() => result.current.resolveParcela(A));
		act(() => result.current.resolveParcela(B, true));
		act(() => result.current.resolveParcela(C, true));
		settle();
		const union3 = JSON.stringify(result.current.request);

		act(() => result.current.resolveParcela(C, true));

		expect(result.current.state.parcelas).toEqual([
			A.nomenclatura,
			B.nomenclatura,
		]);
		expect(JSON.stringify(result.current.request)).toBe(union3);

		settle();
		expect(result.current.request).toEqual({
			tipo: "parcelas",
			nomenclaturas: [A.nomenclatura, B.nomenclatura],
		});
	});

	it("does not leave a timer armed after unmount", () => {
		const { result, unmount } = setup();
		act(() => result.current.resolveParcela(A));
		act(() => result.current.resolveParcela(B, true));

		unmount();
		// A pending settle firing against an unmounted hook would be a React warning
		// at best and a leak at worst.
		expect(() =>
			vi.advanceTimersByTime(FICHA_PARCELAS_SETTLE_MS * 2),
		).not.toThrow();
	});

	// ── touch mode ────────────────────────────────────────────────────────────

	it("with multi-select ON every plain tap accumulates (no ctrl on touch)", () => {
		const { result } = setup();
		act(() => result.current.setMultiSelect(true));
		act(() => result.current.resolveParcela(A));
		act(() => result.current.resolveParcela(B));
		settle();

		expect(result.current.state.multiSelect).toBe(true);
		expect(result.current.request).toEqual({
			tipo: "parcelas",
			nomenclaturas: [A.nomenclatura, B.nomenclatura],
		});
	});

	it("multi-select mode survives a tap-MISS, and the miss keeps the selection", () => {
		// The sticky mode is not one-shot, and a tap that lands on a road is not a
		// reset: wiping a five-parcel selection because the user missed would be
		// unrecoverable (the tap-miss rule).
		const { result } = setup();
		act(() => result.current.setMultiSelect(true));
		act(() => result.current.resolveParcela(A));
		act(() => result.current.resolveParcela(null));

		expect(result.current.state.multiSelect).toBe(true);
		expect(result.current.state.parcelas).toEqual([A.nomenclatura]);
	});

	it("a MODE TRANSITION clears the selection even with multi-select ON", () => {
		// What `clearParcelas` is for: starting a measurement is a mode transition
		// (design §6.5 — "switching modes discards the previous result"), which is a
		// different event from a tap that missed. The touch mode itself survives, so
		// the user comes back to the same tool they left.
		const { result } = setup();
		act(() => result.current.setMultiSelect(true));
		act(() => result.current.resolveParcela(A));
		act(() => result.current.resolveParcela(B));
		settle();
		expect(result.current.request).not.toBeNull();

		act(() => result.current.clearParcelas());

		expect(result.current.state.parcelas).toEqual([]);
		expect(result.current.request).toBeNull();
		expect(result.current.state.multiSelect).toBe(true);
	});

	it("turning multi-select OFF keeps the parcels already picked", () => {
		const { result } = setup();
		act(() => result.current.setMultiSelect(true));
		act(() => result.current.resolveParcela(A));
		act(() => result.current.resolveParcela(B));
		act(() => result.current.setMultiSelect(false));

		expect(result.current.state.parcelas).toEqual([
			A.nomenclatura,
			B.nomenclatura,
		]);
	});

	// ── misses, caps and identity ─────────────────────────────────────────────

	it("an ADDITIVE click that hits nothing does NOT wipe the selection", () => {
		const { result } = setup();
		act(() => result.current.resolveParcela(A));
		act(() => result.current.resolveParcela(B, true));

		act(() => result.current.resolveParcela(null, true));

		expect(result.current.state.parcelas).toEqual([
			A.nomenclatura,
			B.nomenclatura,
		]);
	});

	it("a PLAIN click that hits nothing still clears the ficha", () => {
		const { result } = setup();
		act(() => result.current.resolveParcela(A));
		act(() => result.current.resolveParcela(null));

		expect(result.current.state.parcelas).toEqual([]);
		expect(result.current.request).toBeNull();
	});

	it("stops growing at FICHA_PARCELAS_MAX instead of building a 422", () => {
		const { result } = setup();
		act(() => result.current.setMultiSelect(true));
		for (let i = 0; i < FICHA_PARCELAS_MAX + 5; i += 1) {
			const nomenclatura = `13-06-01-${String(i).padStart(4, "0")}`;
			act(() => result.current.resolveParcela(parcela(nomenclatura)));
		}

		expect(result.current.state.parcelas).toHaveLength(FICHA_PARCELAS_MAX);
	});

	it("REPORTS every click dropped by the cap (it is not a silent no-op)", () => {
		// A click that changes nothing and says nothing reads as a broken map; the
		// container turns this into a notification.
		const onCapReached = vi.fn();
		const { result } = setup(onCapReached);
		act(() => result.current.setMultiSelect(true));
		for (let i = 0; i < FICHA_PARCELAS_MAX; i += 1) {
			act(() =>
				result.current.resolveParcela(
					parcela(`13-06-01-${String(i).padStart(4, "0")}`),
				),
			);
		}
		expect(onCapReached).not.toHaveBeenCalled();

		act(() => result.current.resolveParcela(parcela("13-06-01-9001")));
		expect(onCapReached).toHaveBeenCalledTimes(1);

		// A SECOND dropped click is reported too — the user tapping again deserves
		// the same answer, not silence.
		act(() => result.current.resolveParcela(parcela("13-06-01-9002")));
		expect(onCapReached).toHaveBeenCalledTimes(2);
	});

	it("does not report the cap for a click that DESELECTS while at the cap", () => {
		const onCapReached = vi.fn();
		const { result } = setup(onCapReached);
		act(() => result.current.setMultiSelect(true));
		for (let i = 0; i < FICHA_PARCELAS_MAX; i += 1) {
			act(() =>
				result.current.resolveParcela(
					parcela(`13-06-01-${String(i).padStart(4, "0")}`),
				),
			);
		}

		act(() => result.current.resolveParcela(parcela("13-06-01-0000")));

		expect(result.current.state.parcelas).toHaveLength(FICHA_PARCELAS_MAX - 1);
		expect(onCapReached).not.toHaveBeenCalled();
	});

	it("identity props and the BPA account are dropped for a multi selection", () => {
		const { result } = setup();
		act(() => result.current.resolveParcela(A));
		expect(result.current.nroCuenta).toBe("110123");
		expect(result.current.parcelaProps).not.toBeNull();

		act(() => result.current.resolveParcela(B, true));
		settle();

		// A union has no account and no single nomenclatura; showing the last-clicked
		// parcel's would misattribute the analysis to it.
		expect(result.current.nroCuenta).toBeNull();
		expect(result.current.parcelaProps).toBeNull();
	});

	it("deselecting back down to ONE parcel RESTORES the survivor identity header", () => {
		// The bug: the guard compared the CLICKED parcel, which on a removal is the
		// one leaving. [A, B] minus B left a single-parcel ficha with no
		// nomenclatura, no account and therefore no BPA badge.
		const { result } = setup();
		act(() => result.current.resolveParcela(A));
		act(() => result.current.resolveParcela(B, true));
		settle();
		expect(result.current.parcelaProps).toBeNull();

		act(() => result.current.resolveParcela(B, true));

		expect(result.current.state.parcelas).toEqual([A.nomenclatura]);
		expect(result.current.tipo).toBe("parcela");
		expect(result.current.nroCuenta).toBe("110123");
		expect(result.current.parcelaProps?.nomenclatura).toBe(A.nomenclatura);
	});

	it("the restored header describes the SURVIVOR, not the parcel removed", () => {
		const { result } = setup();
		act(() => result.current.resolveParcela(B)); // B first: different account
		act(() => result.current.resolveParcela(A, true));
		settle();

		act(() => result.current.resolveParcela(A, true));

		expect(result.current.state.parcelas).toEqual([B.nomenclatura]);
		expect(result.current.nroCuenta).toBe("110222");
		expect(result.current.parcelaProps?.nomenclatura).toBe(B.nomenclatura);
	});

	// ── recovering from a stale parcel (404 parcela_no_encontrada) ────────────

	it("removeParcelas drops the named parcels and re-derives the request", () => {
		const { result } = setup();
		act(() => result.current.resolveParcela(A));
		act(() => result.current.resolveParcela(B, true));
		act(() => result.current.resolveParcela(C, true));
		settle();

		// The server named B as missing from the catastro — it is not on the map to
		// ctrl-click away, so this is the only way back to a workable selection.
		act(() => result.current.removeParcelas([B.nomenclatura]));
		settle();

		expect(result.current.state.parcelas).toEqual([
			A.nomenclatura,
			C.nomenclatura,
		]);
		expect(result.current.request).toEqual({
			tipo: "parcelas",
			nomenclaturas: [A.nomenclatura, C.nomenclatura],
		});
	});

	it("removeParcelas down to one parcel restores that parcel identity header", () => {
		const { result } = setup();
		act(() => result.current.resolveParcela(A));
		act(() => result.current.resolveParcela(B, true));
		settle();

		act(() => result.current.removeParcelas([B.nomenclatura]));

		expect(result.current.tipo).toBe("parcela");
		expect(result.current.parcelaProps?.nomenclatura).toBe(A.nomenclatura);
	});

	it("removeParcelas ignores nomenclaturas that are not selected", () => {
		const { result } = setup();
		act(() => result.current.resolveParcela(A));
		act(() => result.current.resolveParcela(B, true));
		settle();
		const antes = result.current.state;

		act(() => result.current.removeParcelas(["99-99-99-9999"]));

		expect(result.current.state).toBe(antes);
	});

	// ── mode transitions ──────────────────────────────────────────────────────

	it("entering draw mode discards the accumulated selection and the mode", () => {
		const onEnterDraw = vi.fn();
		const { result } = renderHook(() =>
			useFichaInteraction("idle", onEnterDraw),
		);
		act(() => result.current.setMultiSelect(true));
		act(() => result.current.resolveParcela(A));
		act(() => result.current.resolveParcela(B));

		act(() => result.current.startDraw());

		expect(result.current.state.parcelas).toEqual([]);
		// Documented exception to the sticky mode: a full reset from IDLE turns the
		// touch toggle off along with everything else.
		expect(result.current.state.multiSelect).toBe(false);
		expect(onEnterDraw).toHaveBeenCalledTimes(1);
	});

	it("entering canal mode discards the accumulated selection", () => {
		const { result } = setup();
		act(() => result.current.resolveParcela(A));
		act(() => result.current.resolveParcela(B, true));
		settle();

		act(() => result.current.startCanal());

		expect(result.current.state.parcelas).toEqual([]);
		expect(result.current.request).toBeNull();
	});

	it("a ctrl-click is IGNORED while drawing (DrawControl owns clicks)", () => {
		const { result } = setup();
		act(() => result.current.startDraw());
		act(() => result.current.resolveParcela(A, true));

		expect(result.current.state.parcelas).toEqual([]);
	});
});
