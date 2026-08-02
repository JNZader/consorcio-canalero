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
		expect(screen.getByRole("button", { name: /medir/i })).toBeInTheDocument();

		// Limpiar is NOT rendered when there's nothing to clear.
		expect(
			screen.queryByRole("button", { name: /limpiar/i }),
		).not.toBeInTheDocument();

		// Exactly ONE toolbar button rendered in this state.
		expect(screen.getAllByRole("button")).toHaveLength(1);
	});

	it("renders the Limpiar button ALONGSIDE Medir when hasMeasurements is true", () => {
		renderWithMantine(
			<MeasurementToolbar
				mode="idle"
				hasMeasurements={true}
				onStartDistance={() => {}}
				onStartArea={() => {}}
				onClear={() => {}}
			/>,
		);

		expect(screen.getByRole("button", { name: /medir/i })).toBeInTheDocument();
		expect(
			screen.getByRole("button", { name: /limpiar/i }),
		).toBeInTheDocument();
		expect(screen.getAllByRole("button")).toHaveLength(2);
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

		await user.click(screen.getByRole("button", { name: /medir/i }));

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

		await user.click(screen.getByRole("button", { name: /medir/i }));
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

		await user.click(screen.getByRole("button", { name: /medir/i }));
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

		await user.click(screen.getByRole("button", { name: /limpiar/i }));
		expect(onClear).toHaveBeenCalledTimes(1);
	});

	it('marks the Medir trigger as active (variant="filled") when mode is measuring-distance', () => {
		renderWithMantine(
			<MeasurementToolbar
				mode="measuring-distance"
				hasMeasurements={false}
				onStartDistance={() => {}}
				onStartArea={() => {}}
				onClear={() => {}}
			/>,
		);

		const medirBtn = screen.getByRole("button", { name: /medir/i });
		// El componente migró de Mantine ActionIcon (`data-variant="filled"`)
		// a un UnstyledButton con `style.background` directo. La señal de
		// "activo" hoy es el color de fondo naranja `#fb923c` en vez del
		// data-attribute. Verificamos el style — el contrato externo (chip
		// de naranja al medir) es el mismo.
		// El componente setea `style.background` inline; JSDOM expone el
		// valor crudo via `getAttribute('style')`. No usamos `toHaveStyle`
		// porque su normalización con shorthand `background` vs longhand
		// `backgroundColor` es inconsistente entre Mantine y JSDOM.
		expect(medirBtn.getAttribute("style") ?? "").toContain("#fb923c");
	});

	it("marks the Medir trigger as active (orange background) when mode is measuring-area", () => {
		renderWithMantine(
			<MeasurementToolbar
				mode="measuring-area"
				hasMeasurements={false}
				onStartDistance={() => {}}
				onStartArea={() => {}}
				onClear={() => {}}
			/>,
		);

		const medirBtn = screen.getByRole("button", { name: /medir/i });
		// El componente setea `style.background` inline; JSDOM expone el
		// valor crudo via `getAttribute('style')`. No usamos `toHaveStyle`
		// porque su normalización con shorthand `background` vs longhand
		// `backgroundColor` es inconsistente entre Mantine y JSDOM.
		expect(medirBtn.getAttribute("style") ?? "").toContain("#fb923c");
	});

	it("does NOT mark the Medir trigger as filled when mode is idle", () => {
		renderWithMantine(
			<MeasurementToolbar
				mode="idle"
				hasMeasurements={false}
				onStartDistance={() => {}}
				onStartArea={() => {}}
				onClear={() => {}}
			/>,
		);

		const medirBtn = screen.getByRole("button", { name: /medir/i });
		expect(medirBtn).not.toHaveAttribute("data-variant", "filled");
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
		const drawBtn = screen.getByRole("button", { name: /dibujar polígono/i });
		expect(drawBtn).toHaveAttribute("aria-pressed", "false");
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
		const medirBtn = screen.getByRole("button", { name: /^medir$/i });
		expect(medirBtn.getAttribute("style") ?? "").not.toContain("#fb923c");
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
		const canalBtn = screen.getByRole("button", { name: /seleccionar canal/i });
		expect(canalBtn).toHaveAttribute("aria-pressed", "false");
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
		const medirBtn = screen.getByRole("button", { name: /^medir$/i });
		expect(medirBtn.getAttribute("style") ?? "").not.toContain("#fb923c");
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

	it('keeps "Limpiar mediciones" (onClear) once there IS something to wipe', async () => {
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

		await user.click(
			screen.getByRole("button", { name: /limpiar mediciones/i }),
		);

		expect(onClear).toHaveBeenCalledTimes(1);
		expect(onCancel).not.toHaveBeenCalled();
	});

	it("exposes the Medir trigger as a toggle: aria-pressed + cancels on click while measuring", async () => {
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

		const medirBtn = screen.getByRole("button", { name: /^medir$/i });
		expect(medirBtn).toHaveAttribute("aria-pressed", "true");

		await user.click(medirBtn);

		// Toggling off ends the mode instead of re-opening the mode menu.
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

		const medirBtn = screen.getByRole("button", { name: /^medir$/i });
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
