import { useEffect, useMemo } from 'react';

import { useIsAuthenticated } from '../../stores/authStore';

/**
 * The subset of `MeasurementToolbar` props that this gate owns.
 *
 * `MeasurementToolbar` renders each of these buttons ONLY when its callback is
 * provided (that is how the 3D viewer already opts out), so handing it an object
 * without them keeps the buttons OUT OF THE DOM — not disabled. That is the
 * explicit requirement: the owner wants the anonymous visitor to not SEE the
 * analysis tools, and a greyed-out button is still an advertisement plus a
 * dead-end.
 */
export interface AnalysisToolProps {
  readonly onToggleFichaDraw?: () => void;
  readonly onRedrawPolygon?: () => void;
  readonly onDeletePolygon?: () => void;
  readonly onToggleFichaCanal?: () => void;
  readonly onToggleFichaMultiSelect?: () => void;
}

export interface UseAnalysisToolsGateParams extends AnalysisToolProps {
  /** `state.drawing` — the free-draw SESSION (outlives tracing). */
  readonly drawing: boolean;
  /** `state.canalMode` — canal/cuenca selection mode. */
  readonly canalMode: boolean;
  /** `state.multiSelect` — the sticky accumulate-parcels mode. */
  readonly multiSelect: boolean;
  /** `useFichaInteraction.stopDraw` — leaves the draw session and clears the ficha. */
  readonly stopDraw: () => void;
  /** `useFichaInteraction.stopCanal` — leaves canal mode and clears the ficha. */
  readonly stopCanal: () => void;
  /** `useFichaInteraction.setMultiSelect` — turns accumulation off. */
  readonly setMultiSelect: (on: boolean) => void;
}

/**
 * Login gate for the map's ANALYSIS tools (ficha territorial).
 *
 * WHAT IS GATED — the three entry points the owner named: "Dibujar polígono"
 * (free-draw ficha), "Canal" (canal/cuenca mode) and the sticky "Selección
 * múltiple" toggle. Their draw sub-controls ("Otro" / "Borrar") ride along,
 * since they only exist inside a draw session that an anonymous visitor can no
 * longer open.
 *
 * WHAT STAYS PUBLIC — navigation, zoom, compass, fullscreen, DESCARGAR, MEDIR
 * (explicitly kept public by the owner), CAPAS, and the ficha itself on a parcel
 * click, single OR accumulated. The ctrl/⌘-click gesture that accumulates
 * parcels is NOT gated: the sticky toggle is only a discoverable shortcut for
 * the same gesture (and the only way to express it on touch), so hiding the
 * BUTTON is not hiding the CAPABILITY. See `useMapInteractionEffects`, where the
 * modifier is read off the DOM event and handed to
 * `useFichaInteraction.resolveParcela(parcela, additive)` with no reference to
 * this gate.
 *
 * THIS IS A RENDER GATE, NOT AN AUTHZ BOUNDARY. It is UX — a visible reason to
 * log in — and nothing more. The ficha endpoints stay PUBLIC behind their own
 * server-side caps (`FICHA_PARCELAS_MAX`, area/vertex caps, see
 * `src/lib/api/ficha.ts`); those caps are the security layer. Do NOT "harden"
 * this by requiring a token on the ficha API: that would break the anonymous
 * single-parcel and ctrl-click flows the owner wants kept.
 *
 * ANTI-FLASH: the criterion is `useIsAuthenticated()`
 * (`user && !loading && initialized`), so during the first render — auth still
 * initializing — it answers FALSE and the buttons stay hidden until a session is
 * CONFIRMED. Hidden-then-shown is the acceptable direction; the reverse (paint
 * the tools, then yank them from an anonymous visitor) is a visible glitch and
 * momentarily promises something the user cannot keep.
 *
 * SESSION LOSS MID-USE: if the token expires or the user logs out while a tool
 * is live, the effect below leaves the mode the same way Escape does
 * (`useMapEscapeExit` → `stopDraw` / `stopCanal`). Without it, `DrawControl`
 * would stay mounted owning map clicks with no visible button left to exit it.
 */
export function useAnalysisToolsGate({
  drawing,
  canalMode,
  multiSelect,
  stopDraw,
  stopCanal,
  setMultiSelect,
  onToggleFichaDraw,
  onRedrawPolygon,
  onDeletePolygon,
  onToggleFichaCanal,
  onToggleFichaMultiSelect,
}: UseAnalysisToolsGateParams): AnalysisToolProps {
  const isAuthenticated = useIsAuthenticated();

  useEffect(() => {
    if (isAuthenticated) return;
    // Idempotent by construction: each branch is guarded on the flag it clears,
    // so a re-run with the session already gone is a no-op (and `stopDraw` /
    // `stopCanal` both reset to IDLE, which also drops `multiSelect`).
    if (drawing) stopDraw();
    if (canalMode) stopCanal();
    if (multiSelect) setMultiSelect(false);
  }, [isAuthenticated, drawing, canalMode, multiSelect, stopDraw, stopCanal, setMultiSelect]);

  return useMemo(
    () =>
      isAuthenticated
        ? {
            onToggleFichaDraw,
            onRedrawPolygon,
            onDeletePolygon,
            onToggleFichaCanal,
            onToggleFichaMultiSelect,
          }
        : {},
    [
      isAuthenticated,
      onToggleFichaDraw,
      onRedrawPolygon,
      onDeletePolygon,
      onToggleFichaCanal,
      onToggleFichaMultiSelect,
    ]
  );
}
