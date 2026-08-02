/**
 * CanalBufferControl — the canal analysis control for `'ficha-canal'` mode (A6 + A7).
 *
 * Shows the active curated canal by NAME and lets the user pick influence-strip
 * (buffer) vs catchment (cuenca) with a segmented control. In buffer mode a
 * distance input commits the new value up (`onBufferChange`) ONLY on blur or
 * Enter — never per keystroke. The committed value + analysis mode live in
 * `useFichaInteraction`; the input keeps a local draft while editing. In cuenca
 * mode there is no distance to pick, so the input is hidden.
 */

import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { CanalBufferControl } from "@/components/map2d/CanalBufferControl";

function renderWithMantine(ui: ReactNode) {
	return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

function bufferProps(
	overrides?: Partial<Parameters<typeof CanalBufferControl>[0]>,
) {
	return {
		canalNombre: "Canal NE sin intervención",
		analysisMode: "buffer" as const,
		onAnalysisModeChange: () => {},
		bufferM: 500,
		maxBufferM: 2000,
		onBufferChange: () => {},
		onClose: () => {},
		...overrides,
	};
}

describe("<CanalBufferControl />", () => {
	it("shows the selected canal NAME and the current buffer value", () => {
		renderWithMantine(<CanalBufferControl {...bufferProps()} />);

		expect(screen.getByText("Canal NE sin intervención")).toBeInTheDocument();
		expect(
			screen.getByRole("textbox", { name: /distancia de influencia/i }),
		).toHaveValue("500");
	});

	it("lets the user switch to Cuenca analysis via the segmented control", async () => {
		const user = userEvent.setup();
		const onAnalysisModeChange = vi.fn();
		renderWithMantine(
			<CanalBufferControl {...bufferProps({ onAnalysisModeChange })} />,
		);

		await user.click(screen.getByRole("radio", { name: /cuenca/i }));
		expect(onAnalysisModeChange).toHaveBeenCalledWith("cuenca");
	});

	it("HIDES the distance input in cuenca mode (no half-width to pick)", () => {
		renderWithMantine(
			<CanalBufferControl {...bufferProps({ analysisMode: "cuenca" })} />,
		);

		expect(
			screen.queryByRole("textbox", { name: /distancia de influencia/i }),
		).toBeNull();
		expect(screen.getByText(/cuenca de aporte real/i)).toBeInTheDocument();
	});

	it("does NOT report intermediate keystrokes — only commits once on blur", async () => {
		const user = userEvent.setup();
		const onBufferChange = vi.fn();
		renderWithMantine(
			<CanalBufferControl {...bufferProps({ onBufferChange })} />,
		);

		const input = screen.getByRole("textbox", {
			name: /distancia de influencia/i,
		});
		await user.clear(input);
		await user.type(input, "1500");

		// Typing "1500" must NOT fire a request per digit (would self-429/503 the user).
		expect(onBufferChange).not.toHaveBeenCalled();

		await user.tab(); // blur commits the final value exactly once
		expect(onBufferChange).toHaveBeenCalledTimes(1);
		expect(onBufferChange).toHaveBeenCalledWith(1500);
	});

	it("commits on Enter with the fully-typed value", async () => {
		const user = userEvent.setup();
		const onBufferChange = vi.fn();
		renderWithMantine(
			<CanalBufferControl {...bufferProps({ onBufferChange })} />,
		);

		const input = screen.getByRole("textbox", {
			name: /distancia de influencia/i,
		});
		await user.clear(input);
		await user.type(input, "800");
		expect(onBufferChange).not.toHaveBeenCalled();

		await user.keyboard("{Enter}");
		expect(onBufferChange).toHaveBeenCalledTimes(1);
		expect(onBufferChange).toHaveBeenCalledWith(800);
	});

	it("does NOT re-fire when blurring an unchanged value", async () => {
		const user = userEvent.setup();
		const onBufferChange = vi.fn();
		renderWithMantine(
			<CanalBufferControl {...bufferProps({ onBufferChange })} />,
		);

		const input = screen.getByRole("textbox", {
			name: /distancia de influencia/i,
		});
		await user.click(input); // focus without changing
		await user.tab(); // blur, draft still equals the committed 500

		expect(onBufferChange).not.toHaveBeenCalled();
	});

	it("resets an invalid draft back to the committed value on blur", async () => {
		const user = userEvent.setup();
		const onBufferChange = vi.fn();
		renderWithMantine(
			<CanalBufferControl {...bufferProps({ onBufferChange })} />,
		);

		const input = screen.getByRole("textbox", {
			name: /distancia de influencia/i,
		});
		await user.clear(input); // empty → invalid draft
		await user.tab();

		expect(onBufferChange).not.toHaveBeenCalled();
		expect(input).toHaveValue("500"); // snapped back to the source-of-truth prop
	});

	it("commits at most the wire max (never an over-cap value the server would 422)", async () => {
		const user = userEvent.setup();
		const onBufferChange = vi.fn();
		renderWithMantine(
			<CanalBufferControl {...bufferProps({ onBufferChange })} />,
		);

		const input = screen.getByRole("textbox", {
			name: /distancia de influencia/i,
		});
		await user.clear(input);
		await user.type(input, "99999");
		await user.tab();

		// clampBehavior="strict" plus the commit clamp cap the value at the wire max.
		expect(onBufferChange).toHaveBeenCalledTimes(1);
		expect(onBufferChange.mock.calls[0][0]).toBeLessThanOrEqual(2000);
	});

	it("calls onClose when the close button is clicked", async () => {
		const user = userEvent.setup();
		const onClose = vi.fn();
		renderWithMantine(<CanalBufferControl {...bufferProps({ onClose })} />);

		await user.click(
			screen.getByRole("button", { name: /cerrar selección de canal/i }),
		);
		expect(onClose).toHaveBeenCalledTimes(1);
	});
});
