/**
 * useTerrainPilarVerdeEffects
 *
 * Strict mirror of the 2D Pilar Verde wiring (`useMapLayerEffects.ts` — Phase
 * 2) for the 3D terrain viewer. One `useEffect` per Pilar Verde layer, each
 * invoking the matching sync helper from `map2d/mapLayerEffectHelpers.ts`.
 *
 * Why a dedicated hook (vs inlining inside `TerrainViewer3D.tsx`):
 *   1. `TerrainViewer3D.tsx` is already > 300 lines — extracting 5 effects +
 *      their dependency arrays into a hook keeps the viewer readable.
 *   2. Matches the 2D blueprint's separation (`useMapLayerEffects.ts` is the
 *      layer-sync orchestrator used by `MapaMapLibre.tsx`). Parallelism
 *      between 2D and 3D entry points makes future maintenance obvious.
 *   3. The hook surface accepts the already-resolved `pilarVerde` payload +
 *      the `vectorLayerVisibility` record, so it has zero coupling to the
 *      top-level hooks (`usePilarVerde`, `useMapLayerSyncStore`). Pure,
 *      testable, easy to reason about.
 *
 * Z-order note: each `sync*Layer` helper already calls the private
 * `raisePilarVerdeStack(map)` at its tail (see `mapLayerEffectHelpers.ts`).
 * We do NOT add a second explicit hoist — duplicating that work would couple
 * this hook to the sync helper internals. Design doc Task 1.5 "Alternative"
 * clause applies: z-order is idempotent inside each sync call.
 *
 * @see `consorcio-web/src/components/map2d/useMapLayerEffects.ts` (lines
 * 219–281 — the 5 Pilar Verde `useEffect` blocks this mirror mirrors 1:1).
 */

import type { FeatureCollection } from 'geojson';
import type maplibregl from 'maplibre-gl';
import { type RefObject, useEffect } from 'react';

import type { PilarVerdeData } from '../../types/pilarVerde';
import {
  syncAgroAceptadaLayer,
  syncAgroPresentadaLayer,
  syncAgroZonasLayer,
  syncBpaHistoricoLayer,
  syncPorcentajeForestacionLayer,
} from '../map2d/mapLayerEffectHelpers';

export interface UseTerrainPilarVerdeEffectsParams {
  /** Ref to the mounted MapLibre instance. `null` before `setReady(true)`. */
  readonly mapRef: RefObject<maplibregl.Map | null>;
  /** `ready` flag from the viewer — gates the effects until map is loaded. */
  readonly ready: boolean;
  /**
   * Pilar Verde payload from `usePilarVerde().data`. `null`/`undefined` means
   * the hook is still loading OR the fetch failed; each `null` slot is
   * short-circuited inside its own effect so partial payloads (only some
   * slots resolved) still render gracefully.
   */
  readonly pilarVerde: PilarVerdeData | null | undefined;
  /**
   * Visibility record from the viewer's local `vectorLayerVisibility` state
   * — already mirrored from the `map3d.visibleVectors` store slice by the
   * viewer's own store subscription effect.
   */
  readonly vectorLayerVisibility: Record<string, boolean>;
}

/**
 * Register the 5 Pilar Verde sync effects on the 3D map.
 *
 * Each effect runs when its data slot OR its visibility flag changes, mirroring
 * the 2D blueprint's finer-grained dependency arrays (a change to BPA data
 * does NOT re-run the other 4 syncs).
 */
export function useTerrainPilarVerdeEffects({
  mapRef,
  ready,
  pilarVerde,
  vectorLayerVisibility,
}: UseTerrainPilarVerdeEffectsParams): void {
  // ── 1. BPA histórico ───────────────────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const data = pilarVerde?.bpaHistorico ?? null;
    if (!data) return;
    syncBpaHistoricoLayer(
      map,
      data as FeatureCollection,
      !!vectorLayerVisibility.pilar_verde_bpa_historico
    );
  }, [mapRef, ready, pilarVerde?.bpaHistorico, vectorLayerVisibility.pilar_verde_bpa_historico]);

  // ── 2. Agro aceptada ────────────────────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const data = pilarVerde?.agroAceptada ?? null;
    if (!data) return;
    syncAgroAceptadaLayer(
      map,
      data as FeatureCollection,
      !!vectorLayerVisibility.pilar_verde_agro_aceptada
    );
  }, [mapRef, ready, pilarVerde?.agroAceptada, vectorLayerVisibility.pilar_verde_agro_aceptada]);

  // ── 3. Agro presentada ──────────────────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const data = pilarVerde?.agroPresentada ?? null;
    if (!data) return;
    syncAgroPresentadaLayer(
      map,
      data as FeatureCollection,
      !!vectorLayerVisibility.pilar_verde_agro_presentada
    );
  }, [
    mapRef,
    ready,
    pilarVerde?.agroPresentada,
    vectorLayerVisibility.pilar_verde_agro_presentada,
  ]);

  // ── 4. Agro zonas ───────────────────────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const data = pilarVerde?.agroZonas ?? null;
    if (!data) return;
    syncAgroZonasLayer(
      map,
      data as FeatureCollection,
      !!vectorLayerVisibility.pilar_verde_agro_zonas
    );
  }, [mapRef, ready, pilarVerde?.agroZonas, vectorLayerVisibility.pilar_verde_agro_zonas]);

  // ── 5. Porcentaje forestación ───────────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const data = pilarVerde?.porcentajeForestacion ?? null;
    if (!data) return;
    syncPorcentajeForestacionLayer(
      map,
      data as FeatureCollection,
      !!vectorLayerVisibility.pilar_verde_porcentaje_forestacion
    );
  }, [
    mapRef,
    ready,
    pilarVerde?.porcentajeForestacion,
    vectorLayerVisibility.pilar_verde_porcentaje_forestacion,
  ]);
}
