/**
 * usePilarVerde
 *
 * Loads the 8 CONSUMED static Pilar Verde assets (of the 10 that ship — see
 * `PILAR_VERDE_UNFETCHED_SLOTS`), split into THREE independently gated
 * TanStack queries so a viewer only pays for what it actually renders:
 *
 *   - `meta`   → aggregates.json (~4 KB). Cheap and load-bearing: every
 *                consumer gates the Pilar Verde UI on `data.aggregates`
 *                (`useMapDerivedState::showPilarVerde`), so deferring it would
 *                hide the very toggles the user needs to request the rest.
 *   - `layers` → the 5 render GeoJSON (~1.0 MB), one per `pilar_verde_*`
 *                toggle. Only needed when one is visible; all five default OFF.
 *   - `bpa`    → bpa_enriched.json + bpa_history.json (~512 KB). Consumed by
 *                the client-side BPA join in the ficha (`PilarVerdeBadges`)
 *                and by `BpaCard` in the InfoPanel.
 *
 * Design echoes `useCatastroMap.ts`:
 *   - queryKey: [...queryKeys.publicLayers(), 'pilar-verde', <group>]
 *   - staleTime: Infinity (assets are immutable per deploy) — one fetch per
 *     group per session once its gate opens.
 *   - Returned shape: { data, loading, error }
 *
 * Back-compat: every group defaults to ENABLED, so `usePilarVerde()` behaves
 * exactly as the previous single-query version. `enabled` remains the master
 * gate (the 3D viewer passes it).
 *
 * Failure handling (T3c final round, R4-001) — a group FAILS AS A UNIT:
 *   - Fetches inside a group run in parallel via Promise.allSettled, but if
 *     ANY slot rejects the queryFn RE-THROWS an aggregate error naming the
 *     failed slots.
 *   - Why throw instead of resolving with `null` slots: resolving made the
 *     query SUCCEED, and `staleTime: Infinity` then cached that all-null result
 *     for the whole session. A layer toggled on during a network blip stayed
 *     permanently dead — no retry, no `error`, and the only trace was a
 *     `logger.warn` that is a no-op in production (`minLevel: 'error'`).
 *     Throwing restores TanStack's retry/backoff, leaves the query in `error`
 *     state (no data to shield behind `staleTime`), and makes it refetch the
 *     next time its gate opens.
 *   - Consumers MUST still tolerate any combination of `null` slots: a group
 *     that never ran (gate closed) leaves its slots `null`, and per-group
 *     `layersError` / `bpaError` tell the UI which family is degraded.
 */

import { useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';
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

/**
 * Slots that ship in `public/` and are still typed, but that NOTHING renders or
 * reads anymore — so no group fetches them (T3c final round, R2-004):
 *   - `zonaAmpliada` (~25 KB) — never had a map layer or a consumer.
 *   - `bpa2025` (~73 KB) — superseded in Phase 7 by the `bpaHistorico`
 *     gradient (see `mapLayerSyncStore.PILAR_VERDE_LAYER_IDS`); the file still
 *     ships for backwards compat with external consumers.
 * They stay in `PILAR_VERDE_PUBLIC_PATHS` (the path map is the asset
 * inventory), stay `null` in the returned data, and cost 0 bytes per session.
 * Re-add one to a group the moment a consumer appears.
 */
export const PILAR_VERDE_UNFETCHED_SLOTS = [
  'zonaAmpliada',
  'bpa2025',
] as const satisfies readonly SlotKey[];

/**
 * Slot → group partition. Every key of `PILAR_VERDE_PUBLIC_PATHS` MUST appear
 * in exactly one group OR in `PILAR_VERDE_UNFETCHED_SLOTS` (asserted by the
 * hook's unit test).
 */
export const PILAR_VERDE_SLOT_GROUPS = {
  meta: ['aggregates'],
  layers: ['bpaHistorico', 'agroAceptada', 'agroPresentada', 'agroZonas', 'porcentajeForestacion'],
  bpa: ['bpaEnriched', 'bpaHistory'],
} as const satisfies Record<string, readonly SlotKey[]>;

export type PilarVerdeSlotGroup = keyof typeof PILAR_VERDE_SLOT_GROUPS;

/** All-null baseline — a group that never ran leaves its slots at `null`. */
const EMPTY_PILAR_VERDE: PilarVerdeData = {
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

async function fetchSlot<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Pilar Verde fetch failed (${res.status}): ${url}`);
  }
  return (await res.json()) as T;
}

/**
 * Load one group's slots in parallel. The group is ATOMIC: every slot must
 * land, or the whole queryFn rejects with an error naming the failed slots.
 *
 * `allSettled` (instead of `all`) is kept on purpose so a single failure still
 * reports EVERY failed slot in one message and so no rejection escapes
 * unhandled; the fan-in is what turns partial failure into a real error.
 */
async function loadSlots(slotKeys: readonly SlotKey[]): Promise<Partial<PilarVerdeData>> {
  const settled = await Promise.allSettled(
    slotKeys.map((key) => fetchSlot<unknown>(PILAR_VERDE_PUBLIC_PATHS[key]))
  );
  const out: Partial<PilarVerdeData> = {};
  const failed: SlotKey[] = [];
  const reasons: unknown[] = [];
  slotKeys.forEach((key, idx) => {
    const result = settled[idx];
    if (result.status === 'fulfilled') {
      // Each slot is typed by its destination — see assignSlot below.
      assignSlot(out, key, result.value);
    } else {
      failed.push(key);
      reasons.push(result.reason);
    }
  });
  if (failed.length > 0) {
    // logger.ERROR, not warn: `warn` is compiled out in production
    // (`logger.minLevel: 'error'`), which is exactly where this matters.
    logger.error(
      `[pilarVerde] failed to load ${failed.join(', ')}`,
      reasons[0],
      ...reasons.slice(1)
    );
    throw new Error(`Pilar Verde: no se pudieron cargar ${failed.join(', ')}`);
  }
  return out;
}

function assignSlot(data: Partial<PilarVerdeData>, key: SlotKey, value: unknown): void {
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
  /**
   * True while the BPA join payload (`bpa_enriched` / `bpa_history`) is still
   * in flight. The ficha uses it to show "Cargando…" instead of wrongly
   * claiming "Sin vinculación" before the file lands.
   */
  bpaLoading: boolean;
  /**
   * True while the ~1.0 MB render GeoJSON group is in flight. Drives the small
   * spinner beside the Pilar Verde family in the layer panel — without it, a
   * toggled-on layer looks broken for the whole download (R4-002).
   */
  layersLoading: boolean;
  /**
   * Per-group failure messages (R4-001). `null` when the group is healthy, has
   * never run, or is still loading. The UI uses them to say WHICH family is
   * degraded instead of hanging on a permanent "Cargando…" / empty map.
   */
  layersError: string | null;
  bpaError: string | null;
}

export interface UsePilarVerdeOptions {
  /**
   * MASTER gate: skip every group when nothing in the UI needs the data. Used
   * by the 3D viewer to defer the downloads until the user actually toggles a
   * Pilar Verde sub-layer on. Default ``true``.
   */
  enabled?: boolean;
  /** Fetch the 5 render GeoJSON (~1.0 MB). Default ``true``. */
  layers?: boolean;
  /** Fetch bpa_enriched + bpa_history (~512 KB). Default ``true``. */
  bpa?: boolean;
  /** Fetch aggregates.json (~4 KB, gates the Pilar Verde UI). Default ``true``. */
  meta?: boolean;
}

function usePilarVerdeGroup(group: PilarVerdeSlotGroup, enabled: boolean) {
  return useQuery({
    queryKey: [...queryKeys.publicLayers(), 'pilar-verde', group] as const,
    queryFn: () => loadSlots(PILAR_VERDE_SLOT_GROUPS[group]),
    staleTime: Number.POSITIVE_INFINITY,
    enabled,
  });
}

export function usePilarVerde(options: UsePilarVerdeOptions = {}): UsePilarVerdeResult {
  const master = options.enabled ?? true;
  const metaQuery = usePilarVerdeGroup('meta', master && (options.meta ?? true));
  const layersQuery = usePilarVerdeGroup('layers', master && (options.layers ?? true));
  const bpaQuery = usePilarVerdeGroup('bpa', master && (options.bpa ?? true));

  const metaData = metaQuery.data;
  const layersData = layersQuery.data;
  const bpaData = bpaQuery.data;

  const data = useMemo(() => {
    // `null` until at least ONE group resolves — preserves the previous
    // "data is null while loading" contract.
    if (!metaData && !layersData && !bpaData) return null;
    return { ...EMPTY_PILAR_VERDE, ...metaData, ...layersData, ...bpaData };
  }, [metaData, layersData, bpaData]);

  const firstError = [metaQuery.error, layersQuery.error, bpaQuery.error].find(
    (err): err is Error => err instanceof Error
  );

  return {
    data,
    loading: metaQuery.isLoading || layersQuery.isLoading || bpaQuery.isLoading,
    error: firstError?.message ?? null,
    bpaLoading: bpaQuery.isLoading,
    layersLoading: layersQuery.isLoading,
    layersError: layersQuery.error instanceof Error ? layersQuery.error.message : null,
    bpaError: bpaQuery.error instanceof Error ? bpaQuery.error.message : null,
  };
}
