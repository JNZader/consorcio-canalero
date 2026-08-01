/**
 * useFichaOverlay.test.tsx
 *
 * The opt-in overlay fetch (A(b) slice 1). Confirms the query:
 *   - stays idle (no fetch) when the toggle is OFF, even with a selection;
 *   - stays idle when there is no selection, even with the toggle ON;
 *   - fetches the `/analisis-zona/overlay` endpoint (body = request + dataset)
 *     when the toggle is ON and a zone is selected;
 *   - re-keys on a selection switch so the previous overlay is not reused.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useFichaOverlay } from "../../src/hooks/useFichaOverlay";
import type { FichaRequest } from "../../src/lib/api/ficha";

function wrapper() {
	const client = new QueryClient({
		defaultOptions: { queries: { retryDelay: 0 } },
	});
	return function Wrapper({ children }: { children: ReactNode }) {
		return (
			<QueryClientProvider client={client}>{children}</QueryClientProvider>
		);
	};
}

function jsonResponse(status: number, body: unknown): Response {
	return {
		ok: status >= 200 && status < 300,
		status,
		json: async () => body,
	} as unknown as Response;
}

const PARCELA: FichaRequest = { tipo: "parcela", nomenclatura: "13-06-01" };
const OVERLAY_FC = {
	dataset: "suelos",
	type: "FeatureCollection",
	features: [],
};

let fetchMock: ReturnType<typeof vi.fn>;

describe("useFichaOverlay", () => {
	beforeEach(() => {
		fetchMock = vi.fn();
		global.fetch = fetchMock as unknown as typeof fetch;
	});
	afterEach(() => {
		vi.clearAllMocks();
	});

	it("does NOT fetch when the toggle is off (even with a selection)", () => {
		renderHook(() => useFichaOverlay(PARCELA, "suelos", false), {
			wrapper: wrapper(),
		});
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it("does NOT fetch when there is no selection (even with the toggle on)", () => {
		renderHook(() => useFichaOverlay(null, "suelos", true), {
			wrapper: wrapper(),
		});
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it("fetches the overlay endpoint when the toggle is on and a zone is selected", async () => {
		fetchMock.mockResolvedValue(jsonResponse(200, OVERLAY_FC));

		const { result } = renderHook(
			() => useFichaOverlay(PARCELA, "suelos", true),
			{
				wrapper: wrapper(),
			},
		);

		await waitFor(() => expect(result.current.data).toBeDefined());
		expect(result.current.data).toEqual(OVERLAY_FC);

		const [url, init] = fetchMock.mock.calls[0];
		expect(String(url)).toContain("/api/v2/geo/analisis-zona/overlay");
		expect(init?.method).toBe("POST");
		expect(JSON.parse(String(init?.body))).toEqual({
			tipo: "parcela",
			nomenclatura: "13-06-01",
			dataset: "suelos",
		});
	});

	it("re-fetches on a selection switch (previous overlay is not reused)", async () => {
		fetchMock.mockResolvedValue(jsonResponse(200, OVERLAY_FC));

		const { rerender } = renderHook(
			({
				request,
				enabled,
			}: { request: FichaRequest | null; enabled: boolean }) =>
				useFichaOverlay(request, "suelos", enabled),
			{ wrapper: wrapper(), initialProps: { request: PARCELA, enabled: true } },
		);

		await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

		const OTRA: FichaRequest = { tipo: "parcela", nomenclatura: "99-99-99" };
		rerender({ request: OTRA, enabled: true });

		await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
		expect(
			JSON.parse(String(fetchMock.mock.calls[1][1]?.body)).nomenclatura,
		).toBe("99-99-99");
	});

	it("goes idle when the toggle is turned off after a selection", async () => {
		fetchMock.mockResolvedValue(jsonResponse(200, OVERLAY_FC));

		const { rerender } = renderHook(
			({ enabled }: { enabled: boolean }) =>
				useFichaOverlay(PARCELA, "suelos", enabled),
			{ wrapper: wrapper(), initialProps: { enabled: true } },
		);

		await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

		rerender({ enabled: false });
		// No additional fetch is issued once the toggle is off.
		expect(fetchMock).toHaveBeenCalledTimes(1);
	});

	it("re-fetches with the new dataset when the overlay dataset switches", async () => {
		fetchMock.mockResolvedValue(jsonResponse(200, OVERLAY_FC));

		const { rerender } = renderHook(
			({ dataset }: { dataset: "suelos" | "flood_risk" | "drainage_need" }) =>
				useFichaOverlay(PARCELA, dataset, true),
			{ wrapper: wrapper(), initialProps: { dataset: "suelos" as const } },
		);

		await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
		expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body)).dataset).toBe(
			"suelos",
		);

		// Switching the dataset changes the query key → a new fetch with the new
		// dataset in the body (the previous overlay is not reused).
		rerender({ dataset: "flood_risk" as const });

		await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
		expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body)).dataset).toBe(
			"flood_risk",
		);
	});
});
