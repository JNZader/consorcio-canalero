/**
 * MapPanelBottomSheet.test.tsx
 *
 * Mobile bottom sheet for the two floating map panels (map-fluidity T2, fix 1).
 *
 * On a ~390px phone the floating cards covered essentially the whole canvas.
 * Below 62em both panels now render as a bottom sheet: full width, anchored to
 * the bottom edge, capped at 45% of the canvas, with a handle that toggles
 * 45% ⇄ 85%. Desktop keeps the T1 floating cards (right:56 + the 45/55 compact
 * split when both are open).
 *
 * BOTH-OPEN MODEL ON MOBILE — "the ficha wins, the InfoPanel queues": only ONE
 * sheet is ever rendered; closing the ficha surfaces the InfoPanel sheet for the
 * same click.
 */

import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen } from "@testing-library/react";
import type { Feature } from "geojson";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { InfoPanel } from "../../src/components/map2d/InfoPanel";
import { MapPanelShell } from "../../src/components/map2d/MapPanelShell";
import {
	MapUiPanels,
	type MapUiPanelsProps,
} from "../../src/components/map2d/MapUiPanels";
import { MAP_VIEW_MODE } from "../../src/components/map2d/ViewModePanel";

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
		selectedFeatures: [feature],
		onCloseInfoPanel: () => {},
		fichaActive: false,
		fichaTipo: "parcela",
		fichaNroCuenta: null,
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

describe("map panels — mobile bottom sheet", () => {
	describe("narrow viewport (<= 62em)", () => {
		beforeEach(() => {
			mockViewport(true);
		});

		it("renders the InfoPanel as a bottom sheet, not a floating card", () => {
			renderWithMantine(<MapUiPanels {...panelProps()} />);

			const panel = screen.getByTestId("map-2d-info-panel");
			expect(panel.className).toContain("panelSheet");
			expect(panel.className).not.toContain("infoPanel");
			expect(panel).toHaveAttribute("data-sheet", "true");
			// Collapsed by default → the top ~55% of the map stays visible.
			expect(panel).toHaveAttribute("data-expanded", "false");
		});

		it("renders the ficha as a bottom sheet", () => {
			renderWithMantine(
				<MapUiPanels
					{...panelProps({ selectedFeatures: [], fichaActive: true })}
				/>,
			);

			const panel = screen.getByTestId("ficha-territorial-panel");
			expect(panel.className).toContain("panelSheet");
			expect(panel.className).not.toContain("fichaPanel");
			expect(panel).toHaveAttribute("data-sheet", "true");
		});

		// T3a, fix 3 — the sheet used to OPEN at its 45% cap and the handle was a
		// 45 ⇄ 85 toggle. It now opens at `peek` (~25%) and one handle tap CYCLES
		// peek → medio (45%) → alto (85%) → peek.
		it("the handle cycles the sheet peek → medio → alto → peek", () => {
			renderWithMantine(<MapUiPanels {...panelProps()} />);

			const panel = screen.getByTestId("map-2d-info-panel");
			const handle = screen.getByTestId("map-2d-info-panel-sheet-handle");

			// Opens at peek: the map stays ~75% visible until the user asks for more.
			expect(panel).toHaveAttribute("data-stage", "peek");
			expect(panel.className).toContain("panelSheetPeek");
			expect(panel.className).not.toContain("panelSheetExpanded");
			expect(handle).toHaveAttribute("aria-expanded", "false");

			fireEvent.click(handle);
			const medio = screen.getByTestId("map-2d-info-panel");
			expect(medio).toHaveAttribute("data-stage", "medio");
			// `medio` is the base 45% cap — no modifier class at all.
			expect(medio.className).not.toContain("panelSheetPeek");
			expect(medio.className).not.toContain("panelSheetExpanded");
			expect(
				screen.getByTestId("map-2d-info-panel-sheet-handle"),
			).toHaveAttribute("aria-expanded", "true");

			fireEvent.click(screen.getByTestId("map-2d-info-panel-sheet-handle"));
			const alto = screen.getByTestId("map-2d-info-panel");
			expect(alto).toHaveAttribute("data-stage", "alto");
			expect(alto.className).toContain("panelSheetExpanded");
			expect(alto).toHaveAttribute("data-expanded", "true");

			// …and back around to peek — one affordance, one direction.
			fireEvent.click(screen.getByTestId("map-2d-info-panel-sheet-handle"));
			const back = screen.getByTestId("map-2d-info-panel");
			expect(back).toHaveAttribute("data-stage", "peek");
			expect(back.className).toContain("panelSheetPeek");
		});

		it("a NEW selection reopens the sheet at peek", () => {
			const { rerender } = renderWithMantine(<MapUiPanels {...panelProps()} />);

			fireEvent.click(screen.getByTestId("map-2d-info-panel-sheet-handle"));
			fireEvent.click(screen.getByTestId("map-2d-info-panel-sheet-handle"));
			expect(screen.getByTestId("map-2d-info-panel")).toHaveAttribute(
				"data-stage",
				"alto",
			);

			// A fresh click on the map hands down a NEW `selectedFeatures` array.
			rerender(
				<MantineProvider env="test">
					<MapUiPanels
						{...panelProps({
							selectedFeatures: [
								{
									...feature,
									properties: { nombre: "Canal Oeste" },
								},
							],
						})}
					/>
				</MantineProvider>,
			);

			expect(screen.getByTestId("map-2d-info-panel")).toHaveAttribute(
				"data-stage",
				"peek",
			);
		});

		it("BOTH OPEN: the ficha wins and the InfoPanel is NOT stacked under it", () => {
			const { rerender } = renderWithMantine(
				<MapUiPanels {...panelProps({ fichaActive: true })} />,
			);

			expect(screen.getByTestId("ficha-territorial-panel")).toBeInTheDocument();
			expect(screen.queryByTestId("map-2d-info-panel")).toBeNull();

			// Closing the ficha surfaces the InfoPanel for the SAME click — the
			// selected features were never discarded.
			rerender(
				<MantineProvider env="test">
					<MapUiPanels {...panelProps({ fichaActive: false })} />
				</MantineProvider>,
			);
			expect(screen.queryByTestId("ficha-territorial-panel")).toBeNull();
			expect(screen.getByTestId("map-2d-info-panel")).toBeInTheDocument();
		});

		// R3-005: the panels' own `Title + CloseButton` row sits inside the
		// SCROLLABLE body, so on a tall ficha it scrolled out of reach. In sheet
		// mode the close control moves to the shell's pinned header instead —
		// exactly one close affordance, always reachable without scrolling.
		it("pins the close control OUTSIDE the scrollable body", () => {
			renderWithMantine(<MapUiPanels {...panelProps()} />);

			const close = screen.getByTestId("map-2d-info-panel-sheet-close");
			const header = close.closest('[class*="panelSheetHeader"]');
			expect(header).not.toBeNull();
			// The pinned header is a SIBLING of the scroll region, never inside it.
			expect(close.closest('[class*="panelSheetBody"]')).toBeNull();
			expect(
				header?.querySelector('[data-testid="map-2d-info-panel-sheet-handle"]'),
			).not.toBeNull();
		});

		it("renders exactly ONE close affordance per sheet", () => {
			renderWithMantine(
				<MapUiPanels
					{...panelProps({ selectedFeatures: [], fichaActive: true })}
				/>,
			);
			expect(
				screen.getAllByRole("button", { name: "Cerrar ficha territorial" }),
			).toHaveLength(1);
		});

		it("the pinned close button calls onClose", () => {
			const onCloseInfoPanel = vi.fn();
			renderWithMantine(<MapUiPanels {...panelProps({ onCloseInfoPanel })} />);

			fireEvent.click(screen.getByTestId("map-2d-info-panel-sheet-close"));
			expect(onCloseInfoPanel).toHaveBeenCalledTimes(1);
		});

		it("never applies the desktop 45/55 compact split in sheet mode", () => {
			renderWithMantine(<MapUiPanels {...panelProps({ fichaActive: true })} />);
			const panel = screen.getByTestId("ficha-territorial-panel");
			expect(panel.className).not.toContain("fichaPanelCompact");
		});
	});

	describe("wide viewport (> 62em) — T1 behaviour unchanged", () => {
		beforeEach(() => {
			mockViewport(false);
		});

		it("keeps the floating cards and renders NO sheet handle", () => {
			renderWithMantine(<MapUiPanels {...panelProps()} />);

			const panel = screen.getByTestId("map-2d-info-panel");
			expect(panel.className).toContain("infoPanel");
			expect(panel.className).not.toContain("panelSheet");
			expect(panel).not.toHaveAttribute("data-sheet");
			expect(screen.queryByTestId("map-2d-info-panel-sheet-handle")).toBeNull();
			// The floating card keeps its own inline close button in the (never
			// scrolled) card header — the shell renders none.
			expect(screen.queryByTestId("map-2d-info-panel-sheet-close")).toBeNull();
			expect(
				screen.getAllByRole("button", { name: "Cerrar panel de informacion" }),
			).toHaveLength(1);
		});

		it("BOTH OPEN: both panels render with the 45/55 compact modifiers", () => {
			renderWithMantine(<MapUiPanels {...panelProps({ fichaActive: true })} />);

			expect(screen.getByTestId("map-2d-info-panel").className).toContain(
				"infoPanelCompact",
			);
			expect(screen.getByTestId("ficha-territorial-panel").className).toContain(
				"fichaPanelCompact",
			);
		});
	});

	// R3-003: 45% / 85% are a CAP, not a size. With a fixed `height` a short
	// InfoPanel still ate 45% of the canvas and padded the rest with empty
	// backdrop; `max-height` lets it size to content and still stop at the cap.
	it("caps the sheet instead of forcing its height", () => {
		const css = readFileSync(
			resolve(process.cwd(), "src/styles/components/map.module.css"),
			"utf-8",
		);
		const sheet = /\.panelSheet\s*\{([^}]*)\}/.exec(css)?.[1] ?? "";
		const expanded = /\.panelSheetExpanded\s*\{([^}]*)\}/.exec(css)?.[1] ?? "";

		const peek = /\.panelSheetPeek\s*\{([^}]*)\}/.exec(css)?.[1] ?? "";

		expect(sheet).toMatch(/max-height:\s*45%/);
		expect(sheet).not.toMatch(/(^|[;{\s])height:/);
		expect(expanded).toMatch(/max-height:\s*85%/);
		expect(expanded).not.toMatch(/(^|[;{\s])height:/);
		// T3a, fix 3 — the new default stage is a cap too, never a fixed height.
		expect(peek).toMatch(/max-height:\s*25%/);
		expect(peek).not.toMatch(/(^|[;{\s])height:/);
		// The internal scroll region survives — a tall ficha still scrolls.
		expect(css).toMatch(/\.panelSheetBody\s*\{[^}]*overflow-y:\s*auto/);
	});

	it("InfoPanel: the sheet prop alone drives the shape (no viewport coupling)", () => {
		mockViewport(false);
		renderWithMantine(
			<InfoPanel features={[feature]} sheet onClose={() => {}} />,
		);

		const panel = screen.getByTestId("map-2d-info-panel");
		expect(panel).toHaveAttribute("data-sheet", "true");
		expect(panel.className).toContain("panelSheet");
	});
});

// La ficha abre en "medio" (initialStage): un peek de una fila tras pedir la
// ficha explicitamente fue el reclamo #1 en dispositivo real. El reset por
// nueva seleccion vuelve al MISMO initialStage, no a "peek". El shell se monta
// directo (modo sheet): el consumidor que pasa "medio" es la ficha.
describe("initialStage", () => {
	const shell = (extra: { initialStage?: "peek" | "medio" | "alto"; resetKey?: string }) => (
		<MantineProvider env="test">
			<MapPanelShell
				sheet
				floatingClassName=""
				testId="shell-under-test"
				sheetLabel="Panel de prueba"
				{...extra}
			>
				<div>contenido</div>
			</MapPanelShell>
		</MantineProvider>
	);

	it('opens the sheet at the stage the consumer asks for', () => {
		render(shell({ initialStage: "medio" }));
		expect(screen.getByTestId("shell-under-test")).toHaveAttribute("data-stage", "medio");
	});

	it('defaults to peek when the consumer says nothing (InfoPanel contract)', () => {
		render(shell({}));
		expect(screen.getByTestId("shell-under-test")).toHaveAttribute("data-stage", "peek");
	});

	it('resets to the SAME initialStage on a new selection, not to peek', () => {
		const { rerender } = render(shell({ initialStage: "medio", resetKey: "a" }));
		fireEvent.click(screen.getByTestId("shell-under-test-sheet-handle"));
		expect(screen.getByTestId("shell-under-test")).toHaveAttribute("data-stage", "alto");
		rerender(shell({ initialStage: "medio", resetKey: "b" }));
		expect(screen.getByTestId("shell-under-test")).toHaveAttribute("data-stage", "medio");
	});
});
