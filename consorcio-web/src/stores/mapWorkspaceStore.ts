import { create } from 'zustand';
import { type PersistStorage, persist } from 'zustand/middleware';

/**
 * Persisted UI preferences for the 2D map workspace shell (`MapWorkspace`).
 *
 * Only the desktop sidebar collapse preference lives here for now. Kept in a
 * dedicated tiny store — separate from `mapLayerSyncStore` (layer VISIBILITY
 * state) — so a UX-layout preference never risks colliding with the layer
 * persist schema / migrations. Follows the same zustand + `persist`
 * (`createJSONStorage(localStorage)`) pattern as `mapLayerSyncStore`.
 */
interface MapWorkspaceState {
  /** Desktop sidebar collapsed (true) vs expanded (false). Persisted. */
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (collapsed: boolean) => void;
  toggleSidebar: () => void;
}

/**
 * JSON-backed persist storage that reads `window.localStorage` FRESH on every
 * operation (instead of memoizing the reference at import time like
 * `createJSONStorage` does). This keeps the store SSR-safe AND lets test
 * environments swap `window.localStorage` after module import.
 */
const storage: PersistStorage<MapWorkspaceState> = {
  getItem: (name) => {
    if (typeof window === 'undefined') return null;
    const raw = window.localStorage.getItem(name);
    return raw ? JSON.parse(raw) : null;
  },
  setItem: (name, value) => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(name, JSON.stringify(value));
  },
  removeItem: (name) => {
    if (typeof window === 'undefined') return;
    window.localStorage.removeItem(name);
  },
};

export const useMapWorkspaceStore = create<MapWorkspaceState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
      toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
    }),
    {
      name: 'cc-map-workspace-ui',
      storage,
      version: 1,
    }
  )
);
