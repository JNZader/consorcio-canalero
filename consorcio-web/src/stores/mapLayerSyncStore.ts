import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

export interface SharedMapLayerState {
  activeRasterType: string | null;
  visibleVectors: Record<string, boolean>;
}

type MapViewKey = 'map2d' | 'map3d';

interface SharedMapLayerActions {
  setActiveRasterType: (view: MapViewKey, tipo: string | null) => void;
  setVectorVisibility: (view: MapViewKey, layerId: string, visible: boolean) => void;
  hydrateViewState: (view: MapViewKey, payload: Partial<SharedMapLayerState>) => void;
  seedViewFromOther: (target: MapViewKey, source: MapViewKey) => void;
  markViewInitialized: (view: MapViewKey) => void;
}

const defaultVisibleVectors: Record<string, boolean> = {
  approved_zones: false,
  zona: false,
  cuencas: false,
  basins: false,
  roads: true,
  waterways: true,
  waterways_rio_tercero: true,
  waterways_canal_desviador: true,
  waterways_canal_litin_tortugas: true,
  waterways_arroyo_algodon: true,
  waterways_arroyo_las_mojarras: true,
  waterways_canales_existentes: true,
  ign_historico: false,
  soil: false,
  catastro: false,
  hydraulic_risk: false,
  puntos_conflicto: false,
};

const inMemoryStorage = {
  getItem: (_name: string) => null,
  setItem: (_name: string, _value: string) => undefined,
  removeItem: (_name: string) => undefined,
};

const storage = createJSONStorage(() => {
  if (typeof window === 'undefined') return inMemoryStorage;
  return window.localStorage;
});

const DEFAULT_LAYER_STATE: SharedMapLayerState = {
  activeRasterType: null,
  visibleVectors: defaultVisibleVectors,
};

interface MapLayerSyncStoreState {
  map2d: SharedMapLayerState;
  map3d: SharedMapLayerState;
  initializedViews: Record<MapViewKey, boolean>;
}

export const useMapLayerSyncStore = create<MapLayerSyncStoreState & SharedMapLayerActions>()(
  persist(
    (set) => ({
      map2d: DEFAULT_LAYER_STATE,
      map3d: DEFAULT_LAYER_STATE,
      initializedViews: { map2d: false, map3d: false },
      setActiveRasterType: (view, tipo) =>
        set((state) => ({
          [view]: {
            ...state[view],
            activeRasterType: tipo,
          },
          initializedViews: { ...state.initializedViews, [view]: true },
        })),
      setVectorVisibility: (view, layerId, visible) =>
        set((state) => ({
          [view]: {
            ...state[view],
            visibleVectors: {
              ...state[view].visibleVectors,
              [layerId]: visible,
            },
          },
          initializedViews: { ...state.initializedViews, [view]: true },
        })),
      hydrateViewState: (view, payload) =>
        set((state) => ({
          [view]: {
            activeRasterType: payload.activeRasterType ?? state[view].activeRasterType,
            visibleVectors: payload.visibleVectors
              ? { ...state[view].visibleVectors, ...payload.visibleVectors }
              : state[view].visibleVectors,
          },
          initializedViews: { ...state.initializedViews, [view]: true },
        })),
      seedViewFromOther: (target, source) =>
        set((state) => ({
          [target]: {
            activeRasterType: state[source].activeRasterType,
            visibleVectors: { ...state[source].visibleVectors },
          },
          initializedViews: { ...state.initializedViews, [target]: true },
        })),
      markViewInitialized: (view) =>
        set((state) => ({
          initializedViews: { ...state.initializedViews, [view]: true },
        })),
    }),
    {
      name: 'cc-map-layer-sync-v2',
      storage,
      partialize: (state) => ({
        map2d: {
          ...state.map2d,
          visibleVectors: {
            ...state.map2d.visibleVectors,
            // Heavy / MVT layers — always start OFF, never persist as true
            basins: false,
            hydraulic_risk: false,
            puntos_conflicto: false,
          },
        },
        map3d: {
          ...state.map3d,
          visibleVectors: {
            ...state.map3d.visibleVectors,
            basins: false,
            hydraulic_risk: false,
            puntos_conflicto: false,
          },
        },
        initializedViews: state.initializedViews,
      }),
    },
  ),
);
