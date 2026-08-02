/**
 * useFichaTerritorial.test.tsx
 *
 * The container-owned fetch (A4.1 / A4.6). Confirms the hook issues the
 * `analisis-zona` POST, parses a success body, preserves the HTTP status +
 * codigo on failure (so the card can branch and the retry predicate can decide),
 * and stays idle when no area is selected.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useFichaTerritorial } from "../../src/hooks/useFichaTerritorial";
import { FichaApiError } from "../../src/lib/api/ficha";

function wrapper() {
	// The hook owns the `retry` predicate (retry once except 413/422/429), so a
	// 404 retries once — `retryDelay: 0` keeps that deterministic and fast here.
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

let fetchMock: ReturnType<typeof vi.fn>;

describe("useFichaTerritorial", () => {
	beforeEach(() => {
		fetchMock = vi.fn();
		global.fetch = fetchMock as unknown as typeof fetch;
	});
	afterEach(() => {
		vi.clearAllMocks();
	});

	it("does not fetch when no area is selected", () => {
		renderHook(() => useFichaTerritorial(null), { wrapper: wrapper() });
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it("POSTs analisis-zona and returns the parsed ficha", async () => {
		const payload = { tipo: "parcela", area_ha: 20 };
		fetchMock.mockResolvedValue(jsonResponse(200, payload));

		const { result } = renderHook(
			() => useFichaTerritorial({ tipo: "parcela", nomenclatura: "13-06-01" }),
			{ wrapper: wrapper() },
		);

		await waitFor(() => expect(result.current.data).toBeDefined());
		expect(result.current.data).toEqual(payload);

		const [url, init] = fetchMock.mock.calls[0];
		expect(String(url)).toContain("/api/v2/geo/analisis-zona");
		expect(init?.method).toBe("POST");
		expect(JSON.parse(String(init?.body))).toEqual({
			tipo: "parcela",
			nomenclatura: "13-06-01",
		});
	});

	// Retry-contract lock (predicate: failureCount < 1 && ![413,422,429].includes(status)).
	// Cap/rate-limit errors are terminal — retrying them is wrong — so each must hit the
	// network EXACTLY once. Flipping the predicate would silently retry these.
	it.each([
		[413, "payload_demasiado_grande"],
		[422, "cap_excedido"],
		[429, "limite_de_tasa"],
	])(
		"does NOT retry a terminal %i (fetched exactly once)",
		async (status, codigo) => {
			fetchMock.mockResolvedValue(
				jsonResponse(status, { detail: "nope", codigo }),
			);

			const { result } = renderHook(
				() => useFichaTerritorial({ tipo: "parcela", nomenclatura: "x" }),
				{ wrapper: wrapper() },
			);

			await waitFor(() => expect(result.current.isError).toBe(true));
			expect(fetchMock).toHaveBeenCalledTimes(1);
		},
	);

	// `cuenca_no_computada` is a 503 but a DELIBERATE not-yet-computed state — a blind
	// retry just re-hits the same 503, so it must be terminal (no retry storm, A7).
	it("does NOT retry a 503 cuenca_no_computada (fetched exactly once)", async () => {
		fetchMock.mockResolvedValue(
			jsonResponse(503, {
				detail: "La cuenca de este canal aún no está disponible",
				codigo: "cuenca_no_computada",
			}),
		);

		const { result } = renderHook(
			() =>
				useFichaTerritorial({
					tipo: "canal_cuenca",
					canal_ref: "canal-a",
					variante: "relevado",
				}),
			{ wrapper: wrapper() },
		);

		await waitFor(() => expect(result.current.isError).toBe(true));
		expect(fetchMock).toHaveBeenCalledTimes(1);
	});

	it("retries a transient 503 exactly once (fetched twice)", async () => {
		fetchMock.mockResolvedValue(
			jsonResponse(503, {
				detail: "dataset off",
				codigo: "dataset_no_cargado",
			}),
		);

		const { result } = renderHook(
			() => useFichaTerritorial({ tipo: "parcela", nomenclatura: "x" }),
			{ wrapper: wrapper() },
		);

		await waitFor(() => expect(result.current.isError).toBe(true));
		expect(fetchMock).toHaveBeenCalledTimes(2);
	});

	it("retries a network fault exactly once (fetched twice)", async () => {
		fetchMock.mockRejectedValue(new Error("network down"));

		const { result } = renderHook(
			() => useFichaTerritorial({ tipo: "parcela", nomenclatura: "x" }),
			{ wrapper: wrapper() },
		);

		await waitFor(() => expect(result.current.isError).toBe(true));
		expect(fetchMock).toHaveBeenCalledTimes(2);
	});

	it("preserves the HTTP status and codigo on a failure", async () => {
		fetchMock.mockResolvedValue(
			jsonResponse(404, {
				detail: "No existe una parcela",
				codigo: "parcela_no_encontrada",
			}),
		);

		const { result } = renderHook(
			() => useFichaTerritorial({ tipo: "parcela", nomenclatura: "nope" }),
			{ wrapper: wrapper() },
		);

		await waitFor(() => expect(result.current.isError).toBe(true));
		const error = result.current.error;
		expect(error).toBeInstanceOf(FichaApiError);
		expect((error as FichaApiError).status).toBe(404);
		expect((error as FichaApiError).codigo).toBe("parcela_no_encontrada");
		expect((error as FichaApiError).message).toBe("No existe una parcela");
	});
});
