import { create } from 'zustand';

export interface HazardMapUiState {
  /** Desktop side panel open/closed. */
  panelOpen: boolean;
  /** Mobile bottom-sheet / chip expanded. */
  mobileExpanded: boolean;
  /** True while a basin flyTo is in flight. */
  pendingBasinZoom: boolean;

  setPanelOpen: (open: boolean) => void;
  setMobileExpanded: (expanded: boolean) => void;
  setPendingBasinZoom: (pending: boolean) => void;
  /** Collapse all panels when a parcel ficha opens. */
  minimizeForFicha: () => void;
  /** Restore UI state to defaults (called when hazard mode turns off). */
  reset: () => void;
}

const DEFAULT_STATE: Pick<
  HazardMapUiState,
  'panelOpen' | 'mobileExpanded' | 'pendingBasinZoom'
> = {
  panelOpen: true,
  mobileExpanded: false,
  pendingBasinZoom: false,
};

/**
 * Ephemeral UI state for the Multi-Hazard mode control bar.
 *
 * Deliberately NOT persisted to localStorage: the product forbids remembering
 * hazard panel state across reloads. This store is independent of
 * `mapLayerSyncStore` so it cannot accidentally inherit that store's persist
 * middleware.
 */
export const useHazardMapStore = create<HazardMapUiState>((set) => ({
  ...DEFAULT_STATE,

  setPanelOpen: (panelOpen) => set({ panelOpen }),
  setMobileExpanded: (mobileExpanded) => set({ mobileExpanded }),
  setPendingBasinZoom: (pendingBasinZoom) => set({ pendingBasinZoom }),

  minimizeForFicha: () =>
    set({
      panelOpen: false,
      mobileExpanded: false,
    }),

  reset: () => set({ ...DEFAULT_STATE }),
}));
