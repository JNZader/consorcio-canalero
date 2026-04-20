/**
 * useApplyPilarVerdeUrlParam
 *
 * One-shot mount-time reader for the `?pilarVerde=1` query param. When the
 * param is present, the 5 Pilar Verde layers are flipped visible via
 * `useMapLayerSyncStore.setVectorVisibility('map2d', id, true)`.
 *
 * Why a dedicated hook:
 *   - Keeps `MapaMapLibre.tsx` thin (single `useApplyPilarVerdeUrlParam()` call)
 *   - Unit-testable without mounting the full map
 *   - "Mount-time flip, not per-render override" per Phase 2 risk #3 — the
 *     effect deps array is empty, so user toggles OFF at runtime stick.
 *
 * Noop cases:
 *   - `?pilarVerde=0`
 *   - No param / empty search string
 *   - Param present with any value other than the literal string "1"
 *
 * Rationale for strict `=== '1'` matching: the widget CTA is the only thing
 * that emits this param, and the contract is pinned in the spec. Accepting
 * "true"/"yes"/etc would open the door to accidental flips from other links.
 */

import { useEffect } from 'react';

import { PILAR_VERDE_LAYER_IDS, useMapLayerSyncStore } from '../../stores/mapLayerSyncStore';

const FLAG_VALUE = '1' as const;
const PARAM_NAME = 'pilarVerde' as const;

function readPilarVerdeFlag(): boolean {
  if (typeof window === 'undefined') return false;
  const search = window.location?.search ?? '';
  if (!search) return false;
  const params = new URLSearchParams(search);
  return params.get(PARAM_NAME) === FLAG_VALUE;
}

/**
 * Reads `?pilarVerde=1` from `window.location.search` exactly once at mount.
 * When present, flips ALL 5 Pilar Verde layers to visible via the shared
 * zustand store.
 */
export function useApplyPilarVerdeUrlParam(): void {
  useEffect(() => {
    if (!readPilarVerdeFlag()) return;
    const setVectorVisibility = useMapLayerSyncStore.getState().setVectorVisibility;
    for (const id of PILAR_VERDE_LAYER_IDS) {
      setVectorVisibility('map2d', id, true);
    }
    // Deps intentionally empty — flip is one-shot. See module header.
  }, []);
}
