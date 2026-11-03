/**
 * MeasurementToolbar — progressive-disclosure floating control for the
 * measurement workflow (SDD map-measurement-tools, Batch-post refactor).
 *
 * The toolbar is a pure presentational component: it takes the current
 * mode + the "has any measurements?" flag, and wires 3 callbacks. State
 * lives in the `useMeasurement` hook that the parent owns.
 *
 * Contract pinned by these tests:
 * - Renders a SINGLE trigger ActionIcon "Medir" that opens a Mantine
 *   `Menu` with two items: "Medir distancia" and "Medir área".
 *   Mirrors the Exportar dropdown pattern from `MapActionsPanel`.
 * - When `mode !== 'idle'` the Medir trigger uses `variant="filled"`
 *   so the user has a clear visual cue that measuring mode is live.
 *   Mirrors the `#fd7e14` orange used by the draw modes in Batch B.
 * - The "Limpiar" ActionIcon is CONDITIONALLY rendered: shown ONLY
 *   when `hasMeasurements === true`. It is NOT disabled when there is
 *   nothing to clear — it is hidden entirely to reduce chrome.
 * - Clicking "Medir distancia" invokes `onStartDistance` exactly once
 *   and closes the dropdown.
 * - Clicking "Medir área" invokes `onStartArea` exactly once and
 *   closes the dropdown.
 * - Clicking "Limpiar" invokes `onClear` exactly once.
 */

import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { MeasurementToolbar } from "@/components/map2d/measurement/MeasurementToolbar";

function renderWithMantine(ui: ReactNode) {
	return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

describe("<MeasurementToolbar />", () => {
	it("shows only the measuring bar while measuring", () => {
		renderWithMantine(
			<MeasurementToolbar
				mode="measuring-distance"
				hasMeasurements={false}
				onStartDistance={() => {}}
				onStartArea={() => {}}
				onClear={() => {}}
				onCancel={() => {}}
				onUndo={() => {}}
			/>,
		);
		expect(screen.getByTestId("measurement-action-bar")).toBeInTheDocument();
		expect(screen.queryByRole("button", { name: "Herramientas" })).not.toBeInTheDocument();
		expect(screen.getByRole("button", { name: "Deshacer vértice" })).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "Cancelar medición" })).toBeInTheDocument();
	});

	it("shows the live distance while measuring", () => {
		renderWithMantine(
			<MeasurementToolbar
				mode="measuring-distance"
				hasMeasurements={false}
				liveLabel="1.2 km"
				onStartDistance={() => {}}
				onStartArea={() => {}}
				onClear={() => {}}
				onCancel={() => {}}
			/>,
		);
		expect(screen.getByTestId("measurement-live")).toHaveTextContent("1.2 km");
	});

	it("renders only the Medir trigger when idle and nothing has been measured", () => {
		renderWithMantine(
			<MeasurementToolbar
				mode="idle"
				hasMeasurements={false}
				onStartDistance={() => {}}
				onStartArea={() => {}}
				onClear={() => {}}
			/>,
		);

		// Medir trigger is present.
		expect(screen.getByRole("button", { name: "Herramientas" })).toBeInTheDocument();

		// Limpiar is NOT rendered when there's nothing to clear.
		expect(
			screen.queryByRole("button", { name: /limpiar/i }),
		).not.toBeInTheDocument();

		// Exactly ONE toolbar button rendered in this state.
		expect(screen.getAllByRole("button")).toHaveLength(1);
	});

	it("keeps Limpiar inside Herramientas when hasMeasurements is true", async () => {
		const user = userEvent.setup();
		renderWithMantine(
			<MeasurementToolbar
				mode="idle"
				hasMeasurements={true}
				onStartDistance={() => {}}
				onStartArea={() => {}}
				onClear={() => {}}
			/>,
		);

		expect(screen.getAllByRole("button")).toHaveLength(1);
		await user.click(screen.getByRole("button", { name: "Herramientas" }));
		expect(screen.getByRole("menuitem", { name: /limpiar mediciones/i })).toBeInTheDocument();
	});

	it('opens a dropdown with "Medir distancia" and "Medir área" when Medir is clicked', async () => {
		const user = userEvent.setup();

		renderWithMantine(
			<MeasurementToolbar
				mode="idle"
				hasMeasurements={false}
				onStartDistance={() => {}}
				onStartArea={() => {}}
				onClear={() => {}}
			/>,
		);

		await user.click(screen.getByRole("button", { name: "Herramientas" }));

		expect(screen.getByText("Medir distancia")).toBeInTheDocument();
		expect(screen.getByText("Medir área")).toBeInTheDocument();
	});

	it('calls onStartDistance when "Medir distancia" is selected from the dropdown', async () => {
		const user = userEvent.setup();
		const onStartDistance = vi.fn();

		renderWithMantine(
			<MeasurementToolbar
				mode="idle"
				hasMeasurements={false}
				onStartDistance={onStartDistance}
				onStartArea={() => {}}
				onClear={() => {}}
			/>,
		);

		await user.click(screen.getByRole("button", { name: "Herramientas" }));
		await user.click(screen.getByText("Medir distancia"));

		expect(onStartDistance).toHaveBeenCalledTimes(1);
	});

	it('calls onStartArea when "Medir área" is selected from the dropdown', async () => {
		const user = userEvent.setup();
		const onStartArea = vi.fn();

		renderWithMantine(
			<MeasurementToolbar
				mode="idle"
				hasMeasurements={false}
				onStartDistance={() => {}}
				onStartArea={onStartArea}
				onClear={() => {}}
			/>,
		);

		await user.click(screen.getByRole("button", { name: "Herramientas" }));
		await user.click(screen.getByText("Medir área"));

		expect(onStartArea).toHaveBeenCalledTimes(1);
	});

	it("calls onClear when the Limpiar button is clicked", async () => {
		const user = userEvent.setup();
		const onClear = vi.fn();

		renderWithMantine(
			<MeasurementToolbar
				mode="idle"
				hasMeasurements={true}
				onStartDistance={() => {}}
				onStartArea={() => {}}
				onClear={onClear}
			/>,
		);

		await user.click(screen.getByRole("button", { name: "Herramientas" }));
		await user.click(screen.getByRole("menuitem", { name: /limpiar mediciones/i }));
		expect(onClear).toHaveBeenCalledTimes(1);
	});

	it("replaces Herramientas with the Deshacer/Cancelar bar while measuring distance", () => {
		renderWithMantine(
			<MeasurementToolbar
				mode="measuring-distance"
				hasMeasurements={false}
				onStartDistance={() => {}}
				onStartArea={() => {}}
				onClear={() => {}}
				onUndo={() => {}}
			/>,
		);

		expect(screen.queryByRole("button", { name: "Herramientas" })).not.toBeInTheDocument();
		expect(screen.getByTestId("measurement-action-bar")).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "Deshacer vértice" })).toBeInTheDocument();
		expect(screen.getByRole("button", { name: /cancelar medición/i })).toBeInTheDocument();
	});

	it("shows Guardar on the bar once a measurement exists", () => {
		renderWithMantine(
			<MeasurementToolbar
				mode="measuring-area"
				hasMeasurements
				onStartDistance={() => {}}
				onStartArea={() => {}}
				onClear={() => {}}
				onSavePersonal={() => {}}
			/>,
		);

		expect(screen.getByRole("button", { name: "Guardar medición" })).toBeInTheDocument();
		expect(screen.queryByRole("button", { name: "Herramientas" })).not.toBeInTheDocument();
	});

	it("does NOT mark Herramientas as a filled action while idle", () => {
		renderWithMantine(
			<MeasurementToolbar
				mode="idle"
				hasMeasurements={false}
				onStartDistance={() => {}}
				onStartArea={() => {}}
				onClear={() => {}}
			/>,
		);

		const tools = screen.getByRole("button", { name: "Herramientas" });
		expect(tools).toHaveAttribute("aria-pressed", "false");
	});

	// ── A5.3 — ficha free-draw toggle beside the measurement buttons ──────────

	it("does NOT render the draw button when onToggleFichaDraw is omitted (3D viewer)", () => {
		renderWithMantine(
			<MeasurementToolbar
				mode="idle"
				hasMeasurements={false}
				onStartDistance={() => {}}
				onStartArea={() => {}}
				onClear={() => {}}
			/>,
		);
		expect(
			screen.queryByRole("button", { name: /dibujar polígono/i }),
		).not.toBeInTheDocument();
	});

	it("renders the draw toggle and calls onToggleFichaDraw on click", async () => {
		const user = userEvent.setup();
		const onToggleFichaDraw = vi.fn();
		renderWithMantine(
			<MeasurementToolbar
				mode="idle"
				hasMeasurements={false}
				onStartDistance={() => {}}
				onStartArea={() => {}}
				onClear={() => {}}
				onToggleFichaDraw={onToggleFichaDraw}
			/>,
		);
		await user.click(screen.getByRole("button", { name: "Herramientas" }));
		const drawBtn = screen.getByRole("menuitem", { name: /dibujar polígono/i });
		expect(drawBtn).not.toHaveAttribute("aria-pressed", "true");
		await user.click(drawBtn);
		expect(onToggleFichaDraw).toHaveBeenCalledTimes(1);
	});

	it("marks the draw toggle pressed + orange when fichaDrawActive (mode ficha-dibujo)", () => {
		renderWithMantine(
			<MeasurementToolbar
				mode="ficha-dibujo"
				hasMeasurements={false}
				onStartDistance={() => {}}
				onStartArea={() => {}}
				onClear={() => {}}
				fichaDrawActive
				onToggleFichaDraw={() => {}}
			/>,
		);
		const drawBtn = screen.getByRole("button", { name: /dibujar polígono/i });
		expect(drawBtn).toHaveAttribute("aria-pressed", "true");
		expect(drawBtn.getAttribute("style") ?? "").toContain("#fb923c");
		// The "Medir" cue must NOT light while drawing (single machine, distinct cues).
		const tools = screen.getByRole("button", { name: "Herramientas" });
		expect(tools.getAttribute("style") ?? "").not.toContain("#fb923c");
	});

	// ── A6 — ficha canal-select toggle beside the draw button ────────────────

	it("does NOT render the canal button when onToggleFichaCanal is omitted", () => {
		renderWithMantine(
			<MeasurementToolbar
				mode="idle"
				hasMeasurements={false}
				onStartDistance={() => {}}
				onStartArea={() => {}}
				onClear={() => {}}
			/>,
		);
		expect(
			screen.queryByRole("button", { name: /seleccionar canal/i }),
		).not.toBeInTheDocument();
	});

	it("renders the canal toggle and calls onToggleFichaCanal on click", async () => {
		const user = userEvent.setup();
		const onToggleFichaCanal = vi.fn();
		renderWithMantine(
			<MeasurementToolbar
				mode="idle"
				hasMeasurements={false}
				onStartDistance={() => {}}
				onStartArea={() => {}}
				onClear={() => {}}
				onToggleFichaCanal={onToggleFichaCanal}
			/>,
		);
		await user.click(screen.getByRole("button", { name: "Herramientas" }));
		const canalBtn = screen.getByRole("menuitem", { name: /seleccionar canal/i });
		expect(canalBtn).not.toHaveAttribute("aria-pressed", "true");
		await user.click(canalBtn);
		expect(onToggleFichaCanal).toHaveBeenCalledTimes(1);
	});

	it("marks the canal toggle pressed + cyan when fichaCanalActive (mode ficha-canal)", () => {
		renderWithMantine(
			<MeasurementToolbar
				mode="ficha-canal"
				hasMeasurements={false}
				onStartDistance={() => {}}
				onStartArea={() => {}}
				onClear={() => {}}
				fichaCanalActive
				onToggleFichaCanal={() => {}}
			/>,
		);
		const canalBtn = screen.getByRole("button", { name: /seleccionar canal/i });
		expect(canalBtn).toHaveAttribute("aria-pressed", "true");
		expect(canalBtn.getAttribute("style") ?? "").toContain("#06b6d4");
		// The "Medir" cue must NOT light while selecting a canal.
		const tools = screen.getByRole("button", { name: "Herramientas" });
		expect(tools.getAttribute("style") ?? "").not.toContain("#fb923c");
	});

	// ── map-fluidity T1 — measuring mode must always offer a way OUT ──────────
	//
	// The trash button used to be gated on `hasMeasurements` alone, so a user who
	// started measuring and drew nothing had NO visible exit at all (and the
	// hook's `cancel()` was wired to nothing). Measuring mode is now always
	// escapable from the toolbar itself.

	it('shows a "Cancelar medición" exit while measuring with ZERO measurements', () => {
		renderWithMantine(
			<MeasurementToolbar
				mode="measuring-distance"
				hasMeasurements={false}
				onStartDistance={() => {}}
				onStartArea={() => {}}
				onClear={() => {}}
				onCancel={() => {}}
			/>,
		);

		expect(
			screen.getByRole("button", { name: /cancelar medición/i }),
		).toBeInTheDocument();
	});

	it("calls onCancel (NOT onClear) from the exit button when nothing was measured", async () => {
		const user = userEvent.setup();
		const onCancel = vi.fn();
		const onClear = vi.fn();

		renderWithMantine(
			<MeasurementToolbar
				mode="measuring-area"
				hasMeasurements={false}
				onStartDistance={() => {}}
				onStartArea={() => {}}
				onClear={onClear}
				onCancel={onCancel}
			/>,
		);

		await user.click(
			screen.getByRole("button", { name: /cancelar medición/i }),
		);

		expect(onCancel).toHaveBeenCalledTimes(1);
		expect(onClear).not.toHaveBeenCalled();
	});

	it("Cancelar exits the mode and keeps saved measurements", async () => {
		const user = userEvent.setup();
		const onCancel = vi.fn();
		const onClear = vi.fn();

		renderWithMantine(
			<MeasurementToolbar
				mode="measuring-distance"
				hasMeasurements={true}
				onStartDistance={() => {}}
				onStartArea={() => {}}
				onClear={onClear}
				onCancel={onCancel}
			/>,
		);

		await user.click(screen.getByRole("button", { name: /cancelar medición/i }));

		expect(onCancel).toHaveBeenCalledTimes(1);
		expect(onClear).not.toHaveBeenCalled();
	});

	it("Cancelar ends measuring instead of reopening the menu", async () => {
		const user = userEvent.setup();
		const onCancel = vi.fn();

		renderWithMantine(
			<MeasurementToolbar
				mode="measuring-distance"
				hasMeasurements={false}
				onStartDistance={() => {}}
				onStartArea={() => {}}
				onClear={() => {}}
				onCancel={onCancel}
			/>,
		);

		await user.click(screen.getByRole("button", { name: /cancelar medición/i }));

		expect(onCancel).toHaveBeenCalledTimes(1);
		expect(screen.queryByText("Medir distancia")).not.toBeInTheDocument();
	});

	it("reports aria-pressed=false and still opens the menu when idle", async () => {
		const user = userEvent.setup();
		const onCancel = vi.fn();

		renderWithMantine(
			<MeasurementToolbar
				mode="idle"
				hasMeasurements={false}
				onStartDistance={() => {}}
				onStartArea={() => {}}
				onClear={() => {}}
				onCancel={onCancel}
			/>,
		);

		const medirBtn = screen.getByRole("button", { name: "Herramientas" });
		expect(medirBtn).toHaveAttribute("aria-pressed", "false");

		await user.click(medirBtn);

		expect(screen.getByText("Medir distancia")).toBeInTheDocument();
		expect(onCancel).not.toHaveBeenCalled();
	});

	it("renders NO exit button when idle with nothing measured (chrome stays minimal)", () => {
		renderWithMantine(
			<MeasurementToolbar
				mode="idle"
				hasMeasurements={false}
				onStartDistance={() => {}}
				onStartArea={() => {}}
				onClear={() => {}}
				onCancel={() => {}}
			/>,
		);

		expect(
			screen.queryByRole("button", { name: /cancelar medición/i }),
		).not.toBeInTheDocument();
		expect(
			screen.queryByRole("button", { name: /limpiar mediciones/i }),
		).not.toBeInTheDocument();
		expect(screen.getAllByRole("button")).toHaveLength(1);
	});
});
