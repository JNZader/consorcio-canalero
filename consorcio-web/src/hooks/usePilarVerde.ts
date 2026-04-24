/**
 * usePilarVerde
 *
 * Loads the 9 static Pilar Verde assets in a single TanStack Query.
 *
 * Design echoes `useCatastroMap.ts`:
 *   - queryKey: [...queryKeys.publicLayers(), 'pilar-verde']
 *   - staleTime: Infinity (assets are immutable per deploy)
 *   - Returned shape: { data, loading, error }
 *
 * Graceful degradation (per spec scenario "missing files"):
 *   - The 9 fetches run in parallel via Promise.allSettled.
 *   - A failed slot becomes `null` in the returned `data`.
 *   - The query itself never rejects on partial failure — error is reserved
 *     for catastrophic cases (e.g. Promise.allSettled itself throws — never
 *     in practice).
 *   - Consumers MUST tolerate any combination of `null` slots.
 */

import { useQuery } from '@tanstack/react-query';
import { logger } from '../lib/logger';
import { queryKeys } from '../lib/query';
import type {
  AggregatesFile,
  AgroAceptadaFeatureCollection,
  AgroPresentadaFeatureCollection,
  AgroZonasFeatureCollection,
  Bpa2025FeatureCollection,
  BpaEnrichedFile,
  BpaHistoricoFeatureCollection,
  BpaHistoryFile,
  PilarVerdeData,
  PorcentajeForestacionFeatureCollection,
  ZonaAmpliadaFeatureCollection,
} from '../types/pilarVerde';

/** Public asset paths — keys mirror PilarVerdeData slot names. */
export const PILAR_VERDE_PUBLIC_PATHS = {
  zonaAmpliada: '/capas/pilar-verde/zona_ampliada.geojson',
  bpa2025: '/capas/pilar-verde/bpa_2025.geojson',
  bpaHistorico: '/capas/pilar-verde/bpa_historico.geojson',
  agroAceptada: '/capas/pilar-verde/agro_aceptada.geojson',
  agroPresentada: '/capas/pilar-verde/agro_presentada.geojson',
  agroZonas: '/capas/pilar-verde/agro_zonas.geojson',
  porcentajeForestacion: '/capas/pilar-verde/porcentaje_forestacion.geojson',
  bpaEnriched: '/data/pilar-verde/bpa_enriched.json',
  bpaHistory: '/data/pilar-verde/bpa_history.json',
  aggregates: '/data/pilar-verde/aggregates.json',
} as const satisfies Record<keyof PilarVerdeData, string>;

type SlotKey = keyof PilarVerdeData;

async function fetchSlot<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Pilar Verde fetch failed (${res.status}): ${url}`);
  }
  return (await res.json()) as T;
}

async function loadAllPilarVerde(): Promise<PilarVerdeData> {
  // Order matches PILAR_VERDE_PUBLIC_PATHS so the .map() preserves slot identity.
  const slotKeys = Object.keys(PILAR_VERDE_PUBLIC_PATHS) as SlotKey[];
  const settled = await Promise.allSettled(
    slotKeys.map((key) => fetchSlot<unknown>(PILAR_VERDE_PUBLIC_PATHS[key]))
  );
  const out: PilarVerdeData = {
    zonaAmpliada: null,
    bpa2025: null,
    bpaHistorico: null,
    agroAceptada: null,
    agroPresentada: null,
    agroZonas: null,
    porcentajeForestacion: null,
    bpaEnriched: null,
    bpaHistory: null,
    aggregates: null,
  };
  slotKeys.forEach((key, idx) => {
    const result = settled[idx];
    if (result.status === 'fulfilled') {
      // Each slot is typed by its destination — see assignSlot below.
      assignSlot(out, key, result.value);
    } else {
      // Leave as null. Consumer surfaces "Datos no disponibles".
      logger.warn(`[pilarVerde] failed to load ${key}`, result.reason);
    }
  });
  return out;
}

function assignSlot(data: PilarVerdeData, key: SlotKey, value: unknown): void {
  switch (key) {
    case 'zonaAmpliada':
      data.zonaAmpliada = value as ZonaAmpliadaFeatureCollection;
      return;
    case 'bpa2025':
      data.bpa2025 = value as Bpa2025FeatureCollection;
      return;
    case 'bpaHistorico':
      data.bpaHistorico = value as BpaHistoricoFeatureCollection;
      return;
    case 'agroAceptada':
      data.agroAceptada = value as AgroAceptadaFeatureCollection;
      return;
    case 'agroPresentada':
      data.agroPresentada = value as AgroPresentadaFeatureCollection;
      return;
    case 'agroZonas':
      data.agroZonas = value as AgroZonasFeatureCollection;
      return;
    case 'porcentajeForestacion':
      data.porcentajeForestacion = value as PorcentajeForestacionFeatureCollection;
      return;
    case 'bpaEnriched':
      data.bpaEnriched = value as BpaEnrichedFile;
      return;
    case 'bpaHistory':
      data.bpaHistory = value as BpaHistoryFile;
      return;
    case 'aggregates':
      data.aggregates = value as AggregatesFile;
      return;
  }
}

export interface UsePilarVerdeResult {
  data: PilarVerdeData | null;
  loading: boolean;
  error: string | null;
}

export function usePilarVerde(): UsePilarVerdeResult {
  const query = useQuery({
    queryKey: [...queryKeys.publicLayers(), 'pilar-verde'] as const,
    queryFn: loadAllPilarVerde,
    staleTime: Number.POSITIVE_INFINITY,
  });
  return {
    data: query.data ?? null,
    loading: query.isLoading,
    error: query.error instanceof Error ? query.error.message : null,
  };
}
