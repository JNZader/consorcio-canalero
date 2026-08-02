/**
 * useFichaOverlayTabs.ts
 *
 * All the state behind the ficha panel's dataset TABS and the clipped on-map
 * overlay they drive (T3b).
 *
 * It exists as a hook rather than as four more `useState` calls inside
 * `MapaMapLibre` for one reason: these pieces are only correct TOGETHER. The
 * selected tab decides which table is read AND which dataset is painted; the
 * per-class visibility is meaningful only against that tab's class labels and
 * must be dropped whenever the tab or the analyzed zone changes; and toggling a
 * class has to be able to turn the overlay on. Spreading that across the
 * container is how the two used to drift apart.
 *
 * The container keeps what only it knows: whether a zone is selected at all, the
 * overlay query, and the map paint call.
 */

import { useCallback, useMemo, useState } from 'react';

import type { FichaOverlayDataset, FichaResponse } from '../../lib/api/ficha';
import { type FichaPanelTab, fichaTabPaintsOverlay } from './FichaTerritorialPanel';

/**
 * Stable "no class hidden" value. A module constant rather than a fresh `[]`:
 * it is written on every tab change and on every new selection, and a new array
 * identity each time would invalidate the `visibleClases` memo (and re-render
 * the panel) for a state that did not actually change.
 */
const NO_HIDDEN_CLASES: readonly string[] = [];

export interface FichaOverlayTabsState {
  /** Selected dataset tab — the ONE control behind body and paint. */
  readonly tab: FichaPanelTab;
  readonly changeTab: (tab: FichaPanelTab) => void;
  /**
   * Dataset the overlay paints. It follows `tab` for the three class datasets
   * and KEEPS ITS LAST VALUE while the rainfall tab is open, so leaving and
   * returning to "Lluvia" repaints what was painted before rather than silently
   * falling back to soils.
   */
  readonly overlayDataset: FichaOverlayDataset;
  /** The user's ON/OFF intent for "Ver recortado en el mapa". */
  readonly overlayVisible: boolean;
  readonly setOverlayVisible: (visible: boolean) => void;
  /**
   * Whether anything should actually be painted: the intent AND a tab that has
   * an overlay. The rainfall tab has none, and disabling it here (instead of
   * clearing `overlayVisible`) is exactly what preserves the intent.
   */
  readonly overlayEnabled: boolean;
  /** Class labels of the current tab hidden from the paint. */
  readonly hiddenClases: readonly string[];
  readonly toggleClase: (clase: string) => void;
  /**
   * Labels to paint, resolved against the ficha table of the active dataset —
   * the same table on screen acting as the legend. `null` means "no filter at
   * all", so the untouched path writes nothing to the map.
   */
  readonly visibleClases: string[] | null;
}

export function useFichaOverlayTabs(params: {
  /**
   * Identity of the analyzed zone (`fichaSelectionKey`). A change resets class
   * visibility: a new analysis has different classes over different areas, so
   * carrying "Alto is hidden" into it would hide part of a result the user has
   * not looked at yet.
   */
  readonly selectionKey: string;
  /** The resolved ficha, source of the class labels for the active dataset. */
  readonly ficha: FichaResponse | undefined;
}): FichaOverlayTabsState {
  const { selectionKey, ficha } = params;

  const [tab, setTab] = useState<FichaPanelTab>('suelos');
  const [overlayDataset, setOverlayDataset] = useState<FichaOverlayDataset>('suelos');
  const [overlayVisible, setOverlayVisible] = useState(false);
  const [hiddenClases, setHiddenClases] = useState<readonly string[]>(NO_HIDDEN_CLASES);

  // Adjusted DURING render (React's documented "resetting state when a prop
  // changes"), like every other ficha reset in this tree: an effect would paint
  // one frame with the previous selection's filter before correcting itself.
  // `selectionKey` is a pure trigger — only its identity is compared.
  // CONTRACT — what resets vs what survives a new analyzed zone:
  //   RESETS:   hiddenClases (class filters never leak into another zone).
  //   SURVIVES: `tab` and `overlayVisible` — the LENS the user picked is theirs
  //   (deliberate; do NOT "complete" this reset with setTab/setOverlayVisible).
  const [lastSelectionKey, setLastSelectionKey] = useState(selectionKey);
  if (lastSelectionKey !== selectionKey) {
    setLastSelectionKey(selectionKey);
    setHiddenClases(NO_HIDDEN_CLASES);
  }

  const changeTab = useCallback((next: FichaPanelTab) => {
    setTab(next);
    // Class visibility is per-DATASET: "Alto" in flood risk and "IV" in soils are
    // unrelated sets, so a label held over from the previous tab would either
    // hide a class the user never touched or be a silent no-op. Every tab starts
    // fully painted.
    setHiddenClases(NO_HIDDEN_CLASES);
    if (fichaTabPaintsOverlay(next)) setOverlayDataset(next);
  }, []);

  // Clicking a class row acts on the map. Doing it while the overlay is OFF is
  // an unambiguous "show me this", so it turns the overlay on — otherwise the
  // click would be a no-op the user has no way to explain.
  const toggleClase = useCallback((clase: string) => {
    setHiddenClases((prev) =>
      prev.includes(clase) ? prev.filter((value) => value !== clase) : [...prev, clase]
    );
    setOverlayVisible(true);
  }, []);

  const visibleClases = useMemo(() => {
    if (hiddenClases.length === 0) return null;
    const clases = ficha?.[overlayDataset]?.clases ?? [];
    // No table to resolve against (no result yet, or a `sin_cobertura` dataset)
    // means no legend either. Deriving a filter from it would produce an EMPTY
    // visible list — a blank map — from a stale label the user cannot even see a
    // row for. No table, no filter.
    if (clases.length === 0) return null;
    // The overlay features and this table come from the SAME analysis of the
    // same zone and dataset, so the row labels are exactly the values in
    // `properties.clase`; nothing paintable is left out of the list.
    return clases.map((entry) => entry.clase).filter((clase) => !hiddenClases.includes(clase));
  }, [hiddenClases, ficha, overlayDataset]);

  return {
    tab,
    changeTab,
    overlayDataset,
    overlayVisible,
    setOverlayVisible,
    overlayEnabled: overlayVisible && fichaTabPaintsOverlay(tab),
    hiddenClases,
    toggleClase,
    visibleClases,
  };
}
