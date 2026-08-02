/**
 * fichaOverlayClassFilter.test.ts
 *
 * `setFichaOverlayClassFilter` + the `visibleClases` param of
 * `syncFichaOverlayLayers` (T3b, fix 3).
 *
 * Turning a class off on the map is a pure STYLE operation over the
 * FeatureCollection already on the source: a MapLibre filter on
 * `properties.clase`, no refetch and no re-add. The invariants that matter:
 *   - `null` REMOVES the filter (the untouched path writes nothing);
 *   - an EMPTY list is honored (every class off paints nothing) — it is NOT
 *     silently treated as "show everything";
 *   - both the fill AND the line layer are filtered, or the outlines of hidden
 *     classes would keep drawing ghost boundaries;
 *   - the filter survives a re-sync that RE-CREATES the layers, which is the
 *     ordering bug a separate second effect would have.
 */

import type maplibregl from "maplibre-gl";
import type { FeatureCollection } from "geojson";
import { describe, expect, it, vi } from "vitest";

import {
	FICHA_OVERLAY_FILL_LAYER,
	FICHA_OVERLAY_LINE_LAYER,
	setFichaOverlayClassFilter,
	syncFichaOverlayLayers,
} from "../../src/components/map2d/fichaOverlayLayers";

interface FakeLayer {
	id: string;
	type: string;
	source?: string;
	paint?: Record<string, unknown>;
	filter?: unknown;
}

function createFakeMap() {
	const sources = new Map<
		string,
		{ data: unknown; setData: (next: unknown) => void }
	>();
	const layers = new Map<string, FakeLayer>();
	const setFilter = vi.fn((id: string, filter: unknown) => {
		const layer = layers.get(id);
		if (layer) layer.filter = filter;
	});

	const map = {
		getSource: (id: string) => sources.get(id),
		addSource: (id: string, source: { data: unknown }) => {
			sources.set(id, {
				data: source.data,
				setData: (next: unknown) => {
					const existing = sources.get(id);
					if (existing) existing.data = next;
				},
			});
		},
		removeSource: (id: string) => sources.delete(id),
		getLayer: (id: string) => layers.get(id),
		addLayer: (layer: FakeLayer) => {
			layers.set(layer.id, layer);
		},
		removeLayer: (id: string) => layers.delete(id),
		setPaintProperty: (id: string, prop: string, value: unknown) => {
			const layer = layers.get(id);
			if (layer) layer.paint = { ...(layer.paint ?? {}), [prop]: value };
		},
		setFilter,
	} as unknown as maplibregl.Map;

	return { map, sources, layers, setFilter };
}

const FC: FeatureCollection = {
	type: "FeatureCollection",
	features: [
		{
			type: "Feature",
			properties: { clase: "Alto" },
			geometry: { type: "Point", coordinates: [-62, -32] },
		},
		{
			type: "Feature",
			properties: { clase: "Bajo" },
			geometry: { type: "Point", coordinates: [-61.9, -32] },
		},
	],
};

function paint(map: maplibregl.Map, visibleClases?: readonly string[] | null) {
	syncFichaOverlayLayers(map, {
		featureCollection: FC,
		dataset: "flood_risk",
		visible: true,
		visibleClases,
	});
}

describe("setFichaOverlayClassFilter", () => {
	it("filters BOTH the fill and the line layer by properties.clase", () => {
		const { map, layers, setFilter } = createFakeMap();
		paint(map);
		setFilter.mockClear();

		setFichaOverlayClassFilter(map, ["Bajo"]);

		const expected = ["in", ["get", "clase"], ["literal", ["Bajo"]]];
		expect(layers.get(FICHA_OVERLAY_FILL_LAYER)?.filter).toEqual(expected);
		// Without this the hidden class would keep drawing its outline.
		expect(layers.get(FICHA_OVERLAY_LINE_LAYER)?.filter).toEqual(expected);
		expect(setFilter).toHaveBeenCalledTimes(2);
	});

	it("removes the filter for null (all classes on writes no filter)", () => {
		const { map, layers, setFilter } = createFakeMap();
		paint(map, ["Bajo"]);

		setFichaOverlayClassFilter(map, null);

		expect(layers.get(FICHA_OVERLAY_FILL_LAYER)?.filter).toBeUndefined();
		expect(layers.get(FICHA_OVERLAY_LINE_LAYER)?.filter).toBeUndefined();
		expect(setFilter).toHaveBeenLastCalledWith(
			FICHA_OVERLAY_LINE_LAYER,
			undefined,
		);
	});

	it("honors an EMPTY list — every class off paints nothing", () => {
		const { map, layers } = createFakeMap();
		paint(map);

		setFichaOverlayClassFilter(map, []);

		// NOT collapsed to "no filter": the user turned everything off on purpose.
		expect(layers.get(FICHA_OVERLAY_FILL_LAYER)?.filter).toEqual([
			"in",
			["get", "clase"],
			["literal", []],
		]);
	});

	it("is a no-op when the layers are absent (overlay off / not yet added)", () => {
		const { map, setFilter } = createFakeMap();

		expect(() => setFichaOverlayClassFilter(map, ["Bajo"])).not.toThrow();
		expect(setFilter).not.toHaveBeenCalled();
	});

	it("copies the class list, so a later mutation cannot rewrite the filter", () => {
		const { map, layers } = createFakeMap();
		paint(map);
		const clases = ["Bajo"];

		setFichaOverlayClassFilter(map, clases);
		clases.push("Alto");

		expect(layers.get(FICHA_OVERLAY_FILL_LAYER)?.filter).toEqual([
			"in",
			["get", "clase"],
			["literal", ["Bajo"]],
		]);
	});

	it("survives a map with no setFilter (same guard setPaintProperty uses)", () => {
		const { map, layers } = createFakeMap();
		paint(map);
		(map as unknown as { setFilter?: unknown }).setFilter = undefined;

		expect(() => setFichaOverlayClassFilter(map, ["Bajo"])).not.toThrow();
		expect(layers.has(FICHA_OVERLAY_FILL_LAYER)).toBe(true);
	});
});

describe("syncFichaOverlayLayers · visibleClases", () => {
	it("applies the filter on the very first paint (layers created here)", () => {
		const { map, layers } = createFakeMap();

		paint(map, ["Bajo"]);

		expect(layers.get(FICHA_OVERLAY_FILL_LAYER)?.filter).toEqual([
			"in",
			["get", "clase"],
			["literal", ["Bajo"]],
		]);
	});

	it("re-applies the filter after a hide/show cycle re-CREATES the layers", () => {
		const { map, layers } = createFakeMap();
		paint(map, ["Bajo"]);

		// Toggling the overlay off removes source + layers…
		syncFichaOverlayLayers(map, {
			featureCollection: FC,
			dataset: "flood_risk",
			visible: false,
			visibleClases: ["Bajo"],
		});
		expect(layers.has(FICHA_OVERLAY_FILL_LAYER)).toBe(false);

		// …and turning it back on must not repaint the classes the user hid. A
		// fresh layer carries no filter, which is why the sync owns it.
		paint(map, ["Bajo"]);

		expect(layers.get(FICHA_OVERLAY_FILL_LAYER)?.filter).toEqual([
			"in",
			["get", "clase"],
			["literal", ["Bajo"]],
		]);
	});

	it("clears the filter when the classes go back to all-on", () => {
		const { map, layers } = createFakeMap();
		paint(map, ["Bajo"]);

		paint(map, null);

		expect(layers.get(FICHA_OVERLAY_FILL_LAYER)?.filter).toBeUndefined();
	});

	it("defaults to no filter when the param is omitted (pre-T3b behaviour)", () => {
		const { map, layers, setFilter } = createFakeMap();

		syncFichaOverlayLayers(map, {
			featureCollection: FC,
			dataset: "suelos",
			visible: true,
		});

		expect(layers.get(FICHA_OVERLAY_FILL_LAYER)?.filter).toBeUndefined();
		expect(setFilter).toHaveBeenCalledWith(FICHA_OVERLAY_FILL_LAYER, undefined);
	});
});
