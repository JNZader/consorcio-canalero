/**
 * MapPanelMinimizePill.test.tsx
 *
 * Minimize-to-pill + auto-minimize-on-drag (T3a, fix 2).
 *
 * With a panel open the user was panning AROUND a card instead of panning a map.
 * Both panels now minimize — explicitly, or automatically the moment a map DRAG
 * starts — into a pill that keeps the selection alive. Restoring is always an
 * explicit tap on the pill; a NEW selection always comes back expanded.
 */

import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen } from "@testing-library/react";
import type { Feature } from "geojson";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
	MapUiPanels,
	type MapUiPanelsProps,
} from "../../src/components/map2d/MapUiPanels";
import { MAP_VIEW_MODE } from "../../src/components/map2d/ViewModePanel";
import { fichaPillLabel } from "../../src/components/map2d/FichaTerritorialPanel";
import { infoPillLabel } from "../../src/components/map2d/InfoPanel";
import type {
	FichaPoligonoRequest,
	FichaRequest,
	FichaResponse,
} from "../../src/lib/api/ficha";
import {
	FICHA_IDLE_SELECTION_KEY,
	fichaSelectionKey,
} from "../../src/hooks/useFichaTerritorial";

/**
 * Selection keys as the container computes them (`fichaSelectionKey(request)`).
 * Two parcels with NO nro_cuenta, two polygons and two same-named canals — every
 * pair that the old display-field key collapsed into one key.
 */
const PARCELA_A_KEY = "parcela|19-01-001";
const PARCELA_B_KEY = "parcela|19-01-002";
const POLIGONO_A_KEY = 'poligono|{"type":"Polygon","coordinates":[[[0,0]]]}';
const POLIGONO_B_KEY = 'poligono|{"type":"Polygon","coordinates":[[[5,5]]]}';
const CANAL_A_KEY = "canal_cuenca|canal-7:natural";
const CANAL_B_KEY = "canal_cuenca|canal-9:natural";

function renderWithMantine(ui: ReactNode) {
	return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

/** `(max-width: 62em)` matches only when `narrow` is true. */
function mockViewport(narrow: boolean) {
	Object.defineProperty(window, "matchMedia", {
		writable: true,
		value: vi.fn().mockImplementation((query: string) => ({
			matches: query.includes("max-width") ? narrow : !narrow,
			media: query,
			onchange: null,
			addListener: vi.fn(),
			removeListener: vi.fn(),
			addEventListener: vi.fn(),
			removeEventListener: vi.fn(),
			dispatchEvent: vi.fn(),
		})),
	});
}

const feature: Feature = {
	type: "Feature",
	geometry: { type: "Point", coordinates: [-62.68, -32.62] },
	properties: { nombre: "Canal Este" },
};

/**
 * STABLE array identity. `selectedFeatures` is the reset trigger for the
 * InfoPanel's minimized state (a fresh array = a fresh click), so a rerender
 * that is NOT a new selection must reuse the same reference — exactly like the
 * container, which keeps the array in state.
 */
const FEATURES: readonly Feature[] = [feature];
const OTHER_FEATURES: readonly Feature[] = [
	{ ...feature, properties: { nombre: "Canal Oeste" } },
];
const NO_FEATURES: readonly Feature[] = [];

const emptyDataset = {
	cobertura: "sin_cobertura" as const,
	clases: [],
	pixel_count: 0,
	low_confidence: false,
	cobertura_ratio: 0,
};

const fichaData: FichaResponse = {
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

function panelProps(
	overrides: Partial<MapUiPanelsProps> = {},
): MapUiPanelsProps {
	return {
		baseLayer: "osm",
		onBaseLayerChange: () => {},
		viewMode: MAP_VIEW_MODE.BASE,
		onViewModeChange: () => {},
		hasSingleImage: false,
		hasComparison: false,
		singleImageInfo: null,
		comparisonInfo: null,
		layerItems: [],
		vectorVisibility: {},
		onLayerVisibilityChange: () => {},
		showIGNOverlay: false,
		onShowIGNOverlayChange: () => {},
		demEnabled: false,
		showDemOverlay: false,
		onShowDemOverlayChange: () => {},
		activeDemLayerId: null,
		onActiveDemLayerIdChange: () => {},
		demOptions: [],
		hasApprovedZones: false,
		onOpenExportPng: () => {},
		onExportApprovedZonesPdf: () => {},
		showLegend: false,
		consorcios: [],
		activeLegendItems: [],
		visibleRasterLayers: [],
		hiddenClasses: {},
		hiddenRanges: {},
		onClassToggle: () => {},
		onRangeToggle: () => {},
		selectedFeatures: FEATURES,
		onCloseInfoPanel: () => {},
		fichaActive: false,
		fichaTipo: "parcela",
		fichaNroCuenta: null,
		fichaSelectionKey: PARCELA_A_KEY,
		fichaLoading: false,
		fichaError: null,
		fichaData: undefined,
		onCloseFicha: () => {},
		exportPngModalOpen: false,
		onCloseExportPngModal: () => {},
		exportTitle: "Mapa",
		exportIncludeLegend: true,
		exportIncludeMetadata: true,
		onExportTitleChange: () => {},
		onExportIncludeLegendChange: () => {},
		onExportIncludeMetadataChange: () => {},
		onExportPng: () => {},
		...overrides,
	};
}

afterEach(() => {
	vi.restoreAllMocks();
});

describe("minimize-to-pill · desktop card", () => {
	beforeEach(() => {
		mockViewport(false);
	});

	it("minimize → pill → restore round-trips the InfoPanel", () => {
		renderWithMantine(<MapUiPanels {...panelProps()} />);

		expect(screen.getByTestId("map-2d-info-panel")).toBeInTheDocument();
		expect(screen.queryByTestId("map-2d-info-panel-pill")).toBeNull();

		fireEvent.click(screen.getByTestId("map-2d-info-panel-minimize"));

		// The card is gone; only the pill remains, carrying the summary.
		expect(screen.queryByTestId("map-2d-info-panel")).toBeNull();
		const pill = screen.getByTestId("map-2d-info-panel-pill");
		expect(pill).toHaveTextContent("Info · Canal Este");
		// Desktop pill is anchored where the card was, not as a bottom bar.
		expect(pill.className).toContain("panelPill");
		expect(pill.className).toContain("infoPanelPill");

		fireEvent.click(pill);
		expect(screen.getByTestId("map-2d-info-panel")).toBeInTheDocument();
		expect(screen.queryByTestId("map-2d-info-panel-pill")).toBeNull();
	});

	it("minimize → pill → restore round-trips the ficha", () => {
		renderWithMantine(
			<MapUiPanels
				{...panelProps({
					selectedFeatures: NO_FEATURES,
					fichaActive: true,
					fichaTipo: "parcela",
					fichaData,
				})}
			/>,
		);

		fireEvent.click(screen.getByTestId("ficha-territorial-panel-minimize"));

		const pill = screen.getByTestId("ficha-territorial-panel-pill");
		expect(pill).toHaveTextContent("Ficha · Parcela 116.8 ha");
		expect(pill.className).toContain("fichaPanelPill");

		fireEvent.click(pill);
		expect(screen.getByTestId("ficha-territorial-panel")).toBeInTheDocument();
	});
});

describe("minimize-to-pill · mobile sheet", () => {
	beforeEach(() => {
		mockViewport(true);
	});

	it("minimizes the sheet into a slim bottom bar and restores it", () => {
		renderWithMantine(<MapUiPanels {...panelProps()} />);

		fireEvent.click(screen.getByTestId("map-2d-info-panel-minimize"));

		const pill = screen.getByTestId("map-2d-info-panel-pill");
		expect(pill).toHaveAttribute("data-sheet", "true");
		expect(pill.className).toContain("panelSheetPill");
		expect(pill).toHaveTextContent("Info · Canal Este");
		// The sheet shape's pill is NOT the desktop chip.
		expect(pill.className).not.toContain("panelPill");

		fireEvent.click(pill);
		expect(screen.getByTestId("map-2d-info-panel")).toHaveAttribute(
			"data-sheet",
			"true",
		);
	});

	/**
	 * B2-2.2/RES-004 — la pildora del sheet pasa a `position: fixed` (anclada al
	 * viewport, no al canvas). Eso la deja tocable con la pagina scrolleada, pero
	 * el panel que restaura sigue anclado al CANVAS: sin traerlo a cuadro, tocar
	 * la pildora reabre un panel fuera de vista y se lee como "no pasó nada".
	 */
	it("restoring from the sheet pill brings the canvas back into view", () => {
		const scrollIntoView = vi.fn();
		const canvas = document.createElement("div");
		canvas.setAttribute("data-testid", "map-workspace-canvas");
		canvas.scrollIntoView = scrollIntoView;
		document.body.appendChild(canvas);

		try {
			renderWithMantine(<MapUiPanels {...panelProps()} />);
			fireEvent.click(screen.getByTestId("map-2d-info-panel-minimize"));
			fireEvent.click(screen.getByTestId("map-2d-info-panel-pill"));

			expect(scrollIntoView).toHaveBeenCalledWith({ block: "nearest" });
		} finally {
			canvas.remove();
		}
	});
});

describe("auto-minimize on map drag", () => {
	beforeEach(() => {
		mockViewport(false);
	});

	it("a drag signal bump minimizes BOTH open panels", () => {
		const { rerender } = renderWithMantine(
			<MapUiPanels {...panelProps({ fichaActive: true, mapDragSignal: 0 })} />,
		);

		expect(screen.getByTestId("map-2d-info-panel")).toBeInTheDocument();
		expect(screen.getByTestId("ficha-territorial-panel")).toBeInTheDocument();

		rerender(
			<MantineProvider env="test">
				<MapUiPanels {...panelProps({ fichaActive: true, mapDragSignal: 1 })} />
			</MantineProvider>,
		);

		expect(screen.getByTestId("map-2d-info-panel-pill")).toBeInTheDocument();
		expect(
			screen.getByTestId("ficha-territorial-panel-pill"),
		).toBeInTheDocument();
	});

	it("does NOT auto-restore when the drag ends (the signal stops changing)", () => {
		const { rerender } = renderWithMantine(
			<MapUiPanels {...panelProps({ mapDragSignal: 1 })} />,
		);
		// Mounting at 1 must not minimize — only a CHANGE does.
		expect(screen.getByTestId("map-2d-info-panel")).toBeInTheDocument();

		rerender(
			<MantineProvider env="test">
				<MapUiPanels {...panelProps({ mapDragSignal: 2 })} />
			</MantineProvider>,
		);
		expect(screen.getByTestId("map-2d-info-panel-pill")).toBeInTheDocument();

		// Same signal on a later render (drag over, nothing new) → still a pill.
		rerender(
			<MantineProvider env="test">
				<MapUiPanels {...panelProps({ mapDragSignal: 2 })} />
			</MantineProvider>,
		);
		expect(screen.getByTestId("map-2d-info-panel-pill")).toBeInTheDocument();
	});

	it("a NEW selection un-minimizes the panel (fresh content must show)", () => {
		const { rerender } = renderWithMantine(
			<MapUiPanels {...panelProps({ mapDragSignal: 1 })} />,
		);

		rerender(
			<MantineProvider env="test">
				<MapUiPanels {...panelProps({ mapDragSignal: 2 })} />
			</MantineProvider>,
		);
		expect(screen.getByTestId("map-2d-info-panel-pill")).toBeInTheDocument();

		rerender(
			<MantineProvider env="test">
				<MapUiPanels
					{...panelProps({
						mapDragSignal: 2,
						selectedFeatures: OTHER_FEATURES,
					})}
				/>
			</MantineProvider>,
		);

		expect(screen.getByTestId("map-2d-info-panel")).toBeInTheDocument();
		expect(screen.queryByTestId("map-2d-info-panel-pill")).toBeNull();
	});

	it("a NEW ficha target un-minimizes the ficha", () => {
		const { rerender } = renderWithMantine(
			<MapUiPanels
				{...panelProps({
					selectedFeatures: NO_FEATURES,
					fichaActive: true,
					fichaNroCuenta: "111",
					fichaSelectionKey: PARCELA_A_KEY,
					mapDragSignal: 1,
				})}
			/>,
		);

		rerender(
			<MantineProvider env="test">
				<MapUiPanels
					{...panelProps({
						selectedFeatures: NO_FEATURES,
						fichaActive: true,
						fichaNroCuenta: "111",
						fichaSelectionKey: PARCELA_A_KEY,
						mapDragSignal: 2,
					})}
				/>
			</MantineProvider>,
		);
		expect(
			screen.getByTestId("ficha-territorial-panel-pill"),
		).toBeInTheDocument();

		rerender(
			<MantineProvider env="test">
				<MapUiPanels
					{...panelProps({
						selectedFeatures: NO_FEATURES,
						fichaActive: true,
						fichaNroCuenta: "222",
						fichaSelectionKey: PARCELA_B_KEY,
						mapDragSignal: 2,
					})}
				/>
			</MantineProvider>,
		);
		expect(screen.getByTestId("ficha-territorial-panel")).toBeInTheDocument();
	});
});

/**
 * REGRESSION — the reset trigger is the SELECTION IDENTITY, not what the card
 * displays. It used to be `${tipo}|${nroCuenta}|${canalNombre}`, which collides
 * for selections the user reaches every day: parcels the catastro has no
 * `nro_cuenta` for, any two free-draw polygons ("poligono||" both times), two
 * canals sharing a display name. On a collision the new analysis rendered only
 * as a pill and the sheet kept the previous stage — the user's action produced
 * no visible result.
 *
 * The key now comes from `fichaSelectionKey(request)` (the same derivation the
 * query key uses), so these cases differ where they must and — deliberately —
 * still match when the target really is the same.
 */
describe("ficha reset key · selection identity, not display fields", () => {
	beforeEach(() => {
		mockViewport(false);
	});

	/** Minimizes the ficha, then re-renders it with `next` applied. */
	function minimizeThenRerender(
		first: Partial<MapUiPanelsProps>,
		next: Partial<MapUiPanelsProps>,
	) {
		const base = {
			selectedFeatures: NO_FEATURES,
			fichaActive: true,
			fichaData,
		} as const;
		const { rerender } = renderWithMantine(
			<MapUiPanels {...panelProps({ ...base, ...first })} />,
		);
		fireEvent.click(screen.getByTestId("ficha-territorial-panel-minimize"));
		expect(
			screen.getByTestId("ficha-territorial-panel-pill"),
		).toBeInTheDocument();

		rerender(
			<MantineProvider env="test">
				<MapUiPanels {...panelProps({ ...base, ...first, ...next })} />
			</MantineProvider>,
		);
	}

	it("two parcels WITHOUT nro_cuenta still reset (the old key was 'parcela||')", () => {
		minimizeThenRerender(
			{
				fichaTipo: "parcela",
				fichaNroCuenta: null,
				fichaSelectionKey: PARCELA_A_KEY,
			},
			{ fichaSelectionKey: PARCELA_B_KEY },
		);

		expect(screen.getByTestId("ficha-territorial-panel")).toBeInTheDocument();
		expect(screen.queryByTestId("ficha-territorial-panel-pill")).toBeNull();
	});

	it("two different free-draw polygons reset (the old key was 'poligono||')", () => {
		minimizeThenRerender(
			{
				fichaTipo: "poligono",
				fichaNroCuenta: null,
				fichaSelectionKey: POLIGONO_A_KEY,
			},
			{ fichaSelectionKey: POLIGONO_B_KEY },
		);

		expect(screen.getByTestId("ficha-territorial-panel")).toBeInTheDocument();
		expect(screen.queryByTestId("ficha-territorial-panel-pill")).toBeNull();
	});

	it("two canals sharing a display name reset (the old key used the name)", () => {
		minimizeThenRerender(
			{
				fichaTipo: "canal_cuenca",
				fichaCanalNombre: "Canal Norte",
				fichaSelectionKey: CANAL_A_KEY,
			},
			{ fichaSelectionKey: CANAL_B_KEY },
		);

		expect(screen.getByTestId("ficha-territorial-panel")).toBeInTheDocument();
	});

	it("re-selecting the SAME target does NOT reset (the pill survives)", () => {
		minimizeThenRerender(
			{
				fichaTipo: "parcela",
				fichaNroCuenta: null,
				fichaSelectionKey: PARCELA_A_KEY,
			},
			// Same key, unrelated prop churn: nothing new to show, so the user's
			// minimize must survive.
			{ fichaSelectionKey: PARCELA_A_KEY, fichaFetching: true },
		);

		expect(
			screen.getByTestId("ficha-territorial-panel-pill"),
		).toBeInTheDocument();
		expect(screen.queryByTestId("ficha-territorial-panel")).toBeNull();
	});
});

/**
 * The key the container actually threads. Pinned here so the panel contract and
 * the hook stay in sync: if `fichaSelectionKey` ever stopped distinguishing
 * these requests, the collisions above would come straight back.
 */
describe("fichaSelectionKey · request identity", () => {
	const parcelaA: FichaRequest = { tipo: "parcela", nomenclatura: "19-01-001" };
	const parcelaB: FichaRequest = { tipo: "parcela", nomenclatura: "19-01-002" };

	it("distinguishes two parcels (nro_cuenta plays no part)", () => {
		expect(fichaSelectionKey(parcelaA)).not.toBe(fichaSelectionKey(parcelaB));
	});

	it("distinguishes two polygons by geometry", () => {
		const a: FichaRequest = {
			tipo: "poligono",
			geometry: {
				type: "Polygon",
				coordinates: [
					[
						[0, 0],
						[0, 1],
						[1, 1],
						[0, 0],
					],
				],
			} as unknown as FichaPoligonoRequest["geometry"],
		};
		const b: FichaRequest = {
			tipo: "poligono",
			geometry: {
				type: "Polygon",
				coordinates: [
					[
						[5, 5],
						[5, 6],
						[6, 6],
						[5, 5],
					],
				],
			} as unknown as FichaPoligonoRequest["geometry"],
		};
		expect(fichaSelectionKey(a)).not.toBe(fichaSelectionKey(b));
	});

	it("distinguishes two canals by ref, and a buffer change on the same canal", () => {
		const norte: FichaRequest = {
			tipo: "canal_buffer",
			canal_ref: "canal-7",
			buffer_m: 500,
		};
		const otro: FichaRequest = {
			tipo: "canal_buffer",
			canal_ref: "canal-9",
			buffer_m: 500,
		};
		const norteAncho: FichaRequest = {
			tipo: "canal_buffer",
			canal_ref: "canal-7",
			buffer_m: 1000,
		};
		expect(fichaSelectionKey(norte)).not.toBe(fichaSelectionKey(otro));
		expect(fichaSelectionKey(norte)).not.toBe(fichaSelectionKey(norteAncho));
	});

	it("is a stable constant while nothing is selected", () => {
		expect(fichaSelectionKey(null)).toBe(FICHA_IDLE_SELECTION_KEY);
		expect(fichaSelectionKey(null)).toBe(fichaSelectionKey(null));
	});

	it("returns the SAME key for the same target (so a re-click never resets)", () => {
		expect(fichaSelectionKey(parcelaA)).toBe(
			fichaSelectionKey({ tipo: "parcela", nomenclatura: "19-01-001" }),
		);
	});
});

describe("pill summaries are meaningful", () => {
	it("infoPillLabel leads with the first feature's own title", () => {
		expect(infoPillLabel([feature])).toBe("Info · Canal Este");
		expect(
			infoPillLabel([feature, { ...feature, properties: { nombre: "Otro" } }]),
		).toBe("Info · Canal Este +1");
	});

	it("infoPillLabel degrades honestly when no title exists", () => {
		expect(infoPillLabel([{ ...feature, properties: { foo: "bar" } }])).toBe(
			"Información (1)",
		);
	});

	it("fichaPillLabel carries tipo + area, and the canal name for a canal", () => {
		expect(fichaPillLabel({ tipo: "parcela", areaHa: 116.8 })).toBe(
			"Ficha · Parcela 116.8 ha",
		);
		expect(
			fichaPillLabel({
				tipo: "canal_cuenca",
				canalNombre: "Canal Este",
				areaHa: 2450.15,
			}),
		).toBe("Ficha · Canal Este 2450.2 ha");
	});

	it("fichaPillLabel omits the area while the analysis has none yet", () => {
		expect(fichaPillLabel({ tipo: "poligono", areaHa: null })).toBe(
			"Ficha · Polígono",
		);
		expect(fichaPillLabel({ tipo: "poligono", areaHa: Number.NaN })).toBe(
			"Ficha · Polígono",
		);
	});
});
