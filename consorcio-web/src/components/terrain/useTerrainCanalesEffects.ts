/**
 * useTerrainCanalesEffects
 *
 * Strict mirror of the 2D Pilar Azul (Canales) wiring (`useMapLayerEffects.ts`
 * lines 299–346) for the 3D terrain viewer. A single `useEffect` calls
 * `syncCanalesLayers(map, SyncCanalesLayersParams)` with the same payload the
 * 2D viewer computes, so both viewers render identical features + filters.
 *
 * Why a dedicated hook (vs inlining inside `TerrainViewer3D.tsx`):
 *   1. `TerrainViewer3D.tsx` is already > 500 lines — inlining this effect
 *      (~40 lines with deps array + per-canal id computation) keeps the
 *      viewer readable.
 *   2. Matches the Batch B precedent (`useTerrainPilarVerdeEffects`) — one
 *      dedicated hook per layer family (Pilar Verde / Pilar Azul).
 *   3. The hook surface accepts the `canales` payload from `useCanales()`
 *      directly, so it has zero coupling to the top-level hook (just a pure
 *      function of `{mapRef, ready, canales}` plus zustand selectors).
 *
 * Z-order note: `syncCanalesLayers` already calls the private
 * `raiseCanalesStack(map)` at its tail (see `mapLayerEffectHelpers.ts` line
 * 626). We do NOT add a second explicit hoist — duplicating that work would
 * couple this hook to the sync helper internals. Design doc Task 2.4
 * "Alternative" clause applies: z-order is idempotent inside each sync call.
 *
 * Per-canal id computation:
 *   - `visibleRelevadoIds`: every relevado id whose per-canal slug returns
 *     `true` from `isCanalVisible('map3d', ...)`. This encapsulates the
 *     master-gate + per-canal-flag check in one selector (matches the 2D
 *     blueprint's semantics for the relevados layer).
 *   - `visiblePropuestaIds`: `state.getVisiblePropuestaIds('map3d')` —
 *     combines master gate + per-canal + etapa filter in one call.
 *
 * `activeEtapas` fallback:
 *   - When every etapa is toggled OFF the store returns the empty set; the
 *     2D blueprint falls back to `ALL_ETAPAS` so the user still sees
 *     propuestos after flipping everything off + leaving the master ON.
 *     This hook mirrors that behavior (see 2D `useMapLayerEffects.ts` line
 *     335).
 *
 * @see `consorcio-web/src/components/map2d/useMapLayerEffects.ts` (lines
 * 299–346 — the 2D blueprint this hook mirrors 1:1).
 */

import type { FeatureCollection, LineString } from 'geojson';
import type maplibregl from 'maplibre-gl';
import { type RefObject, useEffect } from 'react';

import { ALL_ETAPAS, useMapLayerSyncStore } from '../../stores/mapLayerSyncStore';
import type { CanalFeatureProperties, Etapa, IndexFile } from '../../types/canales';
import { syncCanalesLayers } from '../map2d/mapLayerEffectHelpers';

export interface UseCanalesHookPayload {
  /** Relevados FeatureCollection — `null` while the fetch is in flight. */
  readonly relevados: FeatureCollection<LineString, CanalFeatureProperties> | null;
  /** Propuestas FeatureCollection — `null` while the fetch is in flight. */
  readonly propuestas: FeatureCollection<LineString, CanalFeatureProperties> | null;
  /** `index.json` registry (ids + prioridad + longitud) — `null` on fetch error. */
  readonly index: IndexFile | null;
}

export interface UseTerrainCanalesEffectsParams {
  /** Ref to the mounted MapLibre instance. `null` before `setReady(true)`. */
  readonly mapRef: RefObject<maplibregl.Map | null>;
  /** `ready` flag from the viewer — gates the effect until map is loaded. */
  readonly ready: boolean;
  /** Payload from `useCanales()` — kept narrow to keep the hook pure. */
  readonly canales: UseCanalesHookPayload;
}

/**
 * Register the canales sync effect on the 3D map. Fires on:
 *   - mount (once the map is ready)
 *   - `canales.relevados` / `canales.propuestas` / `canales.index` resolve
 *   - master toggles flip (`canales_relevados` / `canales_propuestos`)
 *   - any etapa toggle flips (`propuestasEtapasVisibility`)
 *   - any per-canal flag flips (`map3d.visibleVectors` — broad dep)
 */
export function useTerrainCanalesEffects({
  mapRef,
  ready,
  canales,
}: UseTerrainCanalesEffectsParams): void {
  // Master toggles (selective subscription — only re-render on flips).
  const relevadosVisible = useMapLayerSyncStore(
    (s) => s.map3d.visibleVectors.canales_relevados ?? false
  );
  const propuestasVisible = useMapLayerSyncStore(
    (s) => s.map3d.visibleVectors.canales_propuestos ?? false
  );
  // Etapas filter slice — shared between 2D + 3D.
  const propuestasEtapasVisibility = useMapLayerSyncStore((s) => s.propuestasEtapasVisibility);
  // Broad slice — triggers re-sync when any per-canal flag changes. We read
  // per-canal flags via `getState()` inside the effect body (avoids
  // subscribing to 43 individual selectors).
  const visibleVectors = useMapLayerSyncStore((s) => s.map3d.visibleVectors);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    // Graceful degradation: if both slots are null (e.g. fetch still in
    // flight OR both failed), skip the sync entirely. The 2D blueprint lets
    // `syncCanalesLayers` render empty sources when one slot is null — we
    // keep that tolerance but avoid calling the helper when neither slot is
    // resolved yet.
    if (!canales.relevados && !canales.propuestas) return;

    const state = useMapLayerSyncStore.getState();

    // Per-canal relevados list: every relevado id whose per-canal slug
    // is NOT flagged false. Derives the store key from the raw slug the
    // same way `registerPilarAzul` does (slug with `-` → `_`). Treats a
    // missing key as `true` (default) so relevados registered AFTER the
    // effect runs still render — matches 2D blueprint exactly
    // (`useMapLayerEffects.ts` lines 307–312). The master toggle gates
    // the whole layer via `relevadosVisible` below.
    const visibleRelevadoIds =
      canales.index?.relevados
        .map(({ id }) => id)
        .filter((slug) => {
          const key = `canal_relevado_${slug.replace(/-/g, '_')}`;
          return visibleVectors[key] !== false;
        }) ?? [];

    // `getVisiblePropuestaIds` bakes in master gate + per-canal + etapa
    // filter; mirrors the 2D blueprint exactly.
    const visiblePropuestaIds = state.getVisiblePropuestaIds('map3d');

    // Active etapas = keys with `true`. Fall back to ALL_ETAPAS when the
    // user has flipped every etapa OFF — preserves the 2D behavior of
    // rendering all propuestos when no etapa-specific filter is selected
    // (spec scenario "5 etapas all true → filter is no-op").
    const activeEtapas = (Object.entries(propuestasEtapasVisibility) as [Etapa, boolean][])
      .filter(([, v]) => v)
      .map(([k]) => k);
    const effectiveEtapas: readonly Etapa[] = activeEtapas.length > 0 ? activeEtapas : ALL_ETAPAS;

    syncCanalesLayers(map, {
      relevados: canales.relevados,
      propuestas: canales.propuestas,
      relevadosVisible,
      propuestasVisible,
      visibleRelevadoIds,
      visiblePropuestaIds,
      activeEtapas: effectiveEtapas,
    });
  }, [
    mapRef,
    ready,
    canales.relevados,
    canales.propuestas,
    canales.index,
    relevadosVisible,
    propuestasVisible,
    propuestasEtapasVisibility,
    // `visibleVectors` is a broad dep — any per-canal toggle change
    // triggers a re-sync so the filter stays in sync with the store.
    visibleVectors,
  ]);
}
