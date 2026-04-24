/**
 * useCanales
 *
 * Loads the 3 static Pilar Azul (Canales) assets in a single TanStack Query.
 *
 * Design mirror of `usePilarVerde.ts` / `useCatastroMap.ts`:
 *   - queryKey: `["public", "canales"]`
 *   - staleTime: `Number.POSITIVE_INFINITY` (static public assets, forever cacheable)
 *   - 3 parallel fetches via `Promise.allSettled` — a failing slot stays `null`
 *     without crashing the hook or the other two (spec requirement
 *     "Missing file graceful degradation").
 *
 * Returned shape: `{ relevados, propuestas, index, isLoading, isError }`.
 * `isError` is a coarse "something failed" flag (any slot 404 / network reject)
 * — per-slot diagnostics are logged via the app logger tagged `[canales:fetch]`.
 */

import { useQuery } from '@tanstack/react-query';

import { logger } from '../lib/logger';
import type { CanalesData, CanalesFeatureCollection, IndexFile } from '../types/canales';

/** Public asset paths — keys mirror `CanalesData` slot names. */
export const CANALES_PATHS = {
  relevados: '/capas/canales/relevados.geojson',
  propuestas: '/capas/canales/propuestas.geojson',
  index: '/capas/canales/index.json',
} as const satisfies Record<keyof CanalesData, string>;

type SlotKey = keyof CanalesData;

async function fetchSlot<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Canales fetch failed (${res.status}): ${url}`);
  }
  return (await res.json()) as T;
}

interface LoadResult {
  data: CanalesData;
  anyFailed: boolean;
}

async function loadAllCanales(): Promise<LoadResult> {
  const slotKeys = Object.keys(CANALES_PATHS) as SlotKey[];
  const settled = await Promise.allSettled(
    slotKeys.map((key) => fetchSlot<unknown>(CANALES_PATHS[key]))
  );

  const data: CanalesData = {
    relevados: null,
    propuestas: null,
    index: null,
  };
  let anyFailed = false;

  slotKeys.forEach((key, idx) => {
    const result = settled[idx]!;
    if (result.status === 'fulfilled') {
      assignSlot(data, key, result.value);
    } else {
      anyFailed = true;
      logger.warn(`[canales:fetch] failed to load ${key}`, result.reason);
    }
  });

  return { data, anyFailed };
}

function assignSlot(data: CanalesData, key: SlotKey, value: unknown): void {
  switch (key) {
    case 'relevados':
      data.relevados = value as CanalesFeatureCollection;
      return;
    case 'propuestas':
      data.propuestas = value as CanalesFeatureCollection;
      return;
    case 'index':
      data.index = value as IndexFile;
      return;
  }
}

export interface UseCanalesResult {
  relevados: CanalesFeatureCollection | null;
  propuestas: CanalesFeatureCollection | null;
  index: IndexFile | null;
  isLoading: boolean;
  /** True iff at least one of the 3 slots failed to load. */
  isError: boolean;
}

export function useCanales(): UseCanalesResult {
  const query = useQuery({
    queryKey: ['public', 'canales'] as const,
    queryFn: loadAllCanales,
    staleTime: Number.POSITIVE_INFINITY,
  });

  const payload = query.data;
  return {
    relevados: payload?.data.relevados ?? null,
    propuestas: payload?.data.propuestas ?? null,
    index: payload?.data.index ?? null,
    isLoading: query.isLoading,
    isError: payload?.anyFailed ?? false,
  };
}
