/**
 * FichaErrorRetry.test.tsx
 *
 * Actionable ficha error states (map-fluidity T2, fix 4).
 *
 * Before this the panel rendered a raw red Alert with the server string. The
 * 429's `retry_after` WAS parsed into `FichaApiError.extra` but never shown, and
 * TanStack does not retry client errors — so the user's only recovery was
 * re-clicking the parcel on the map. Now:
 *   - 429 → "Demasiados pedidos" + a live countdown, "Reintentar" enabled at 0;
 *   - 5xx / network → "Reintentar" available immediately;
 *   - 404 / 422 / cuenca_no_computada / cuenca_demasiado_grande → informative
 *     only, no button (a retry would hit the same wall).
 */

import { MantineProvider } from "@mantine/core";
import { act, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FichaTerritorialPanel } from "../../src/components/map2d/FichaTerritorialPanel";
import { FichaApiError } from "../../src/lib/api/ficha";

function renderWithMantine(ui: ReactNode) {
	return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

const baseProps = {
	active: true,
	tipo: "parcela" as const,
	nroCuenta: null,
	parcelaProps: null,
	bpaEnriched: null,
	isLoading: false,
	isError: true,
	data: undefined,
	onClose: () => {},
};

function rateLimited(retryAfter: unknown) {
	return new FichaApiError(429, "limite_de_tasa", "Demasiados pedidos.", {
		retry_after: retryAfter,
	});
}

/** Advance the fake clock by `seconds`, flushing React state per tick. */
function tick(seconds: number) {
	act(() => {
		vi.advanceTimersByTime(seconds * 1000);
	});
}

describe("ficha error state — 429 countdown", () => {
	beforeEach(() => {
		vi.useFakeTimers();
	});

	afterEach(() => {
		vi.useRealTimers();
	});

	it("shows the rate-limit title, a live countdown and a disabled Reintentar", () => {
		renderWithMantine(
			<FichaTerritorialPanel
				{...baseProps}
				error={rateLimited(3)}
				onRetry={() => {}}
			/>,
		);

		expect(screen.getByTestId("ficha-error")).toHaveTextContent(
			"Demasiados pedidos",
		);
		expect(screen.getByTestId("ficha-error-countdown")).toHaveTextContent(
			"Reintentá en 3s",
		);
		expect(screen.getByTestId("ficha-error-retry")).toBeDisabled();

		tick(1);
		expect(screen.getByTestId("ficha-error-countdown")).toHaveTextContent(
			"Reintentá en 2s",
		);
		expect(screen.getByTestId("ficha-error-retry")).toBeDisabled();

		tick(1);
		expect(screen.getByTestId("ficha-error-countdown")).toHaveTextContent(
			"Reintentá en 1s",
		);

		// Countdown exhausted → the copy disappears and the button unlocks.
		tick(1);
		expect(screen.queryByTestId("ficha-error-countdown")).toBeNull();
		expect(screen.getByTestId("ficha-error-retry")).toBeEnabled();
	});

	it("calls refetch when Reintentar is pressed after the countdown", () => {
		const onRetry = vi.fn();
		renderWithMantine(
			<FichaTerritorialPanel
				{...baseProps}
				error={rateLimited(2)}
				onRetry={onRetry}
			/>,
		);

		fireEvent.click(screen.getByTestId("ficha-error-retry"));
		expect(onRetry).not.toHaveBeenCalled(); // disabled while waiting

		tick(2);
		fireEvent.click(screen.getByTestId("ficha-error-retry"));
		expect(onRetry).toHaveBeenCalledTimes(1);
	});

	it("accepts a numeric-string retry_after and enables immediately without one", () => {
		const { unmount } = renderWithMantine(
			<FichaTerritorialPanel
				{...baseProps}
				error={rateLimited("5")}
				onRetry={() => {}}
			/>,
		);
		expect(screen.getByTestId("ficha-error-countdown")).toHaveTextContent(
			"Reintentá en 5s",
		);
		unmount();

		renderWithMantine(
			<FichaTerritorialPanel
				{...baseProps}
				error={new FichaApiError(429, "limite_de_tasa", "Demasiados pedidos.")}
				onRetry={() => {}}
			/>,
		);
		expect(screen.queryByTestId("ficha-error-countdown")).toBeNull();
		expect(screen.getByTestId("ficha-error-retry")).toBeEnabled();
	});

	it("re-arms the countdown when a SECOND 429 with the same retry_after arrives", () => {
		const { rerender } = renderWithMantine(
			<FichaTerritorialPanel
				{...baseProps}
				error={rateLimited(3)}
				onRetry={() => {}}
			/>,
		);

		tick(2);
		expect(screen.getByTestId("ficha-error-countdown")).toHaveTextContent(
			"Reintentá en 1s",
		);

		rerender(
			<MantineProvider env="test">
				<FichaTerritorialPanel
					{...baseProps}
					error={rateLimited(3)}
					onRetry={() => {}}
				/>
			</MantineProvider>,
		);
		expect(screen.getByTestId("ficha-error-countdown")).toHaveTextContent(
			"Reintentá en 3s",
		);
	});

	// Behavioural, not a `clearInterval` spy: what matters is that nothing keeps
	// ticking against a dead panel. A surviving interval would call `setState` on
	// an unmounted component, which React reports on the console.
	it("stops ticking on unmount (no state updates against a dead panel)", () => {
		const consoleError = vi
			.spyOn(console, "error")
			.mockImplementation(() => {});
		const consoleWarn = vi.spyOn(console, "warn").mockImplementation(() => {});

		const { unmount } = renderWithMantine(
			<FichaTerritorialPanel
				{...baseProps}
				error={rateLimited(30)}
				onRetry={() => {}}
			/>,
		);
		expect(screen.getByTestId("ficha-error-countdown")).toHaveTextContent(
			"Reintentá en 30s",
		);

		unmount();
		// Well past the 30s window: a leaked interval would fire 30 times here.
		tick(30);

		expect(consoleError).not.toHaveBeenCalled();
		expect(consoleWarn).not.toHaveBeenCalled();
		expect(vi.getTimerCount()).toBe(0);

		consoleError.mockRestore();
		consoleWarn.mockRestore();
	});

	// Back-pressure against an absurd server value (fix R1-002).
	it("clamps retry_after to 300s so the panel can never lock for hours", () => {
		renderWithMantine(
			<FichaTerritorialPanel
				{...baseProps}
				error={rateLimited(86_400)}
				onRetry={() => {}}
			/>,
		);
		expect(screen.getByTestId("ficha-error-countdown")).toHaveTextContent(
			"Reintentá en 300s",
		);
	});
});

// In-flight retry feedback (findings R1-001 / R4-001 / R3-004 — REFUTED as
// written, pinned here as the real contract). The review assumed the alert stays
// mounted during a retry, so the button needed a disabled/"Reintentando…" state.
// It does not: query-core's `fetchState()` resets `status` to "pending" and
// clears `error` whenever `data === undefined`, and a failed ficha never has
// data. So a retry swaps the whole alert for the loading spinner in the same
// commit — the acknowledgement is the spinner, and the button is UNMOUNTED
// rather than merely disabled, which is a stronger guarantee against hammering.
describe("ficha error state — retryable vs informative", () => {
	it.each([
		[503, "dataset_no_cargado", "El dataset suelos no esta cargado"],
		[500, "error_interno", "Error interno del servidor"],
	])("offers Reintentar immediately for a %i", (status, codigo, detail) => {
		renderWithMantine(
			<FichaTerritorialPanel
				{...baseProps}
				error={new FichaApiError(status, codigo, detail)}
				onRetry={() => {}}
			/>,
		);

		const retry = screen.getByTestId("ficha-error-retry");
		expect(retry).toBeEnabled();
		expect(screen.queryByTestId("ficha-error-countdown")).toBeNull();
	});

	it("offers Reintentar for a bare network error (no HTTP response)", () => {
		renderWithMantine(
			<FichaTerritorialPanel
				{...baseProps}
				error={new Error("Failed to fetch")}
				onRetry={() => {}}
			/>,
		);
		expect(screen.getByTestId("ficha-error-retry")).toBeEnabled();
	});

	it.each([
		[
			404,
			"parcela_no_encontrada",
			"No existe una parcela con nomenclatura 99-99",
		],
		[422, "geometria_invalida", "La geometría enviada no es válida"],
		[413, "cap_excedido", "Se superó el límite de área"],
		[
			503,
			"cuenca_no_computada",
			"La cuenca de este canal todavía no fue computada",
		],
		[422, "cuenca_demasiado_grande", "La cuenca supera el límite de análisis"],
	])(
		"keeps %i/%s informative-only (no retry button)",
		(status, codigo, detail) => {
			renderWithMantine(
				<FichaTerritorialPanel
					{...baseProps}
					error={new FichaApiError(status, codigo, detail)}
					onRetry={() => {}}
				/>,
			);

			expect(screen.getByTestId("ficha-error")).toHaveTextContent(detail);
			expect(screen.queryByTestId("ficha-error-retry")).toBeNull();
		},
	);

	it("renders no button at all when the container wires no refetch", () => {
		renderWithMantine(
			<FichaTerritorialPanel
				{...baseProps}
				error={new FichaApiError(503, "dataset_no_cargado", "No disponible")}
			/>,
		);
		expect(screen.queryByTestId("ficha-error-retry")).toBeNull();
	});
});

describe("ficha error state — the loading state wins over a stale error", () => {
	it("shows the spinner and NO retry button while a request is in flight", () => {
		renderWithMantine(
			<FichaTerritorialPanel
				{...baseProps}
				isLoading
				isError={false}
				error={null}
				onRetry={() => {}}
			/>,
		);

		expect(screen.getByTestId("ficha-loading")).toHaveTextContent(
			"Analizando la zona",
		);
		expect(screen.queryByTestId("ficha-error")).toBeNull();
		expect(screen.queryByTestId("ficha-error-retry")).toBeNull();
	});

	it("keeps the spinner even if a stale error is still threaded in", () => {
		// Defensive: `isLoading` is checked FIRST, so no ordering of the props can
		// leave a live "Reintentar" button on screen mid-request.
		renderWithMantine(
			<FichaTerritorialPanel
				{...baseProps}
				isLoading
				error={new FichaApiError(500, "error_interno", "Error interno")}
				onRetry={() => {}}
			/>,
		);

		expect(screen.getByTestId("ficha-loading")).toBeInTheDocument();
		expect(screen.queryByTestId("ficha-error-retry")).toBeNull();
	});
});

describe("ficha error state — retry over CACHED data (R3-007)", () => {
	// When the query cache already holds data for the key, TanStack keeps
	// status:'error' across refetch() (it only resets to pending when
	// data === undefined). The alert therefore STAYS MOUNTED during the retry;
	// isFetching is the only in-flight signal on that path.
	it("disables Reintentar and shows Reintentando while a retry is in flight", () => {
		renderWithMantine(
			<FichaTerritorialPanel
				{...baseProps}
				isFetching
				error={new FichaApiError(500, "error_interno", "Error interno.")}
				onRetry={() => {}}
			/>,
		);

		const btn = screen.getByTestId("ficha-error-retry");
		expect(btn).toBeDisabled();
		expect(btn.textContent).toContain("Reintentando");
	});

	it("re-enables Reintentar when the retry settles back into error", () => {
		const onRetry = vi.fn();
		renderWithMantine(
			<FichaTerritorialPanel
				{...baseProps}
				isFetching={false}
				error={new FichaApiError(500, "error_interno", "Error interno.")}
				onRetry={onRetry}
			/>,
		);

		const btn = screen.getByTestId("ficha-error-retry");
		expect(btn).toBeEnabled();
		expect(btn.textContent).toContain("Reintentar");
		fireEvent.click(btn);
		expect(onRetry).toHaveBeenCalledTimes(1);
	});
});
