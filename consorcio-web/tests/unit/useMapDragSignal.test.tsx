/**
 * useMapDragSignal.test.tsx
 *
 * The auto-minimize trigger (T3a, fix 2). It must fire on a map DRAG and on
 * nothing else: subscribing to `click` would collapse the panel the very click
 * that opened it, and subscribing to `zoom` would collapse it on every wheel
 * tick and on every programmatic `fitBounds` the app itself runs.
 */

import { act, renderHook } from "@testing-library/react";
import type maplibregl from "maplibre-gl";
import { createRef } from "react";
import { describe, expect, it } from "vitest";

import {
	MAP_DRAG_EVENT,
	useMapDragSignal,
} from "../../src/components/map2d/useMapDragSignal";

interface FakeMap {
	map: maplibregl.Map;
	handlers: Map<string, Set<() => void>>;
	emit: (event: string) => void;
}

function createFakeMap(): FakeMap {
	const handlers = new Map<string, Set<() => void>>();
	const map = {
		on: (event: string, handler: () => void) => {
			const set = handlers.get(event) ?? new Set<() => void>();
			set.add(handler);
			handlers.set(event, set);
		},
		off: (event: string, handler: () => void) => {
			handlers.get(event)?.delete(handler);
		},
	} as unknown as maplibregl.Map;

	return {
		map,
		handlers,
		emit: (event: string) => {
			for (const handler of handlers.get(event) ?? []) handler();
		},
	};
}

function mapRefFor(map: maplibregl.Map | null) {
	const ref = createRef<maplibregl.Map | null>() as {
		current: maplibregl.Map | null;
	};
	ref.current = map;
	return ref;
}

describe("useMapDragSignal", () => {
	it("subscribes to dragstart and to NOTHING else", () => {
		const fake = createFakeMap();
		renderHook(() => useMapDragSignal(mapRefFor(fake.map), true));

		expect([...fake.handlers.keys()]).toEqual([MAP_DRAG_EVENT]);
		expect(MAP_DRAG_EVENT).toBe("dragstart");
	});

	it("bumps the counter once per dragstart", () => {
		const fake = createFakeMap();
		const { result } = renderHook(() =>
			useMapDragSignal(mapRefFor(fake.map), true),
		);

		expect(result.current).toBe(0);

		act(() => fake.emit("dragstart"));
		expect(result.current).toBe(1);

		act(() => fake.emit("dragstart"));
		expect(result.current).toBe(2);
	});

	it("does NOT bump on click or zoom", () => {
		const fake = createFakeMap();
		const { result } = renderHook(() =>
			useMapDragSignal(mapRefFor(fake.map), true),
		);

		act(() => {
			fake.emit("click");
			fake.emit("zoom");
			fake.emit("zoomstart");
			fake.emit("move");
			fake.emit("moveend");
		});

		expect(result.current).toBe(0);
	});

	it("subscribes nothing while the map is not ready", () => {
		const fake = createFakeMap();
		renderHook(() => useMapDragSignal(mapRefFor(fake.map), false));

		expect(fake.handlers.size).toBe(0);
	});

	it("tolerates a null map ref", () => {
		const { result } = renderHook(() =>
			useMapDragSignal(mapRefFor(null), true),
		);
		expect(result.current).toBe(0);
	});

	it("unsubscribes on unmount", () => {
		const fake = createFakeMap();
		const { unmount } = renderHook(() =>
			useMapDragSignal(mapRefFor(fake.map), true),
		);

		expect(fake.handlers.get(MAP_DRAG_EVENT)?.size).toBe(1);
		unmount();
		expect(fake.handlers.get(MAP_DRAG_EVENT)?.size).toBe(0);
	});
});
