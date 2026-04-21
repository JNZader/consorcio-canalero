import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

import { ALL_ETAPAS, type Etapa, type IndexFile } from '../types/canales';

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

/**
 * Pilar Verde layer IDs registered with the visible-vectors slice.
 * These are wired into the map layer registry by Phase 2 (`map2dConfig.ts`).
 * Default visibility: all OFF — user toggles them on; the `?pv=1` URL param
 * flips all five on at mount time (handled by `useMapLayerEffects`).
 *
 * Phase 7: `pilar_verde_bpa` renamed to `pilar_verde_bpa_historico` — the
 * single-year 2025 fill was replaced by a gradient on the full historical
 * series (228 parcels instead of 70). The old `bpa_2025.geojson` file still
 * ships for backwards compat but is no longer consumed by the map.
 */
export const PILAR_VERDE_LAYER_IDS = [
  'pilar_verde_bpa_historico',
  'pilar_verde_agro_aceptada',
  'pilar_verde_agro_presentada',
  'pilar_verde_agro_zonas',
  'pilar_verde_porcentaje_forestacion',
] as const;

export type PilarVerdeLayerId = (typeof PILAR_VERDE_LAYER_IDS)[number];

export const PILAR_VERDE_DEFAULT_VISIBILITY: Record<PilarVerdeLayerId, boolean> = {
  pilar_verde_bpa_historico: false,
  pilar_verde_agro_aceptada: false,
  pilar_verde_agro_presentada: false,
  pilar_verde_agro_zonas: false,
  pilar_verde_porcentaje_forestacion: false,
};

// ───────────────────────────────────────────────────────────────────────────
// Pilar Azul (Canales) — MASTER toggle ids + defaults
//
// Per-canal ids (`canal_relevado_*`, `canal_propuesto_*`) are REGISTERED
// DYNAMICALLY at runtime via `registerPilarAzul(index)` after `useCanales`
// resolves. This avoids coupling the build to the KMZ pipeline — the ETL
// emits `index.json`, the frontend seeds dynamic ids on mount, and zustand's
// `persist` middleware preserves user-flipped values across reloads.
//
// Per-canal default: true. The master toggle GATES visibility — an ON master
// with a per-canal-true yields a visible layer; an OFF master hides every
// per-canal regardless of its individual flag (see `isCanalVisible`).
// ───────────────────────────────────────────────────────────────────────────
export const PILAR_AZUL_LAYER_IDS = ['canales_relevados', 'canales_propuestos'] as const;

export type PilarAzulLayerId = (typeof PILAR_AZUL_LAYER_IDS)[number];

export const PILAR_AZUL_DEFAULT_VISIBILITY: Record<PilarAzulLayerId, boolean> = {
  // Spec-locked: relevados default ON (visible context), propuestos default
  // OFF (power-user feature — opt-in via checkbox). See spec requirement
  // "Per-canal Layer IDs (dynamic registration)".
  canales_relevados: true,
  canales_propuestos: false,
};

/**
 * Default visibility for the 5 propuestas etapas filter.
 * ALL TRUE — the filter is additive: toggling an etapa OFF hides the matching
 * propuestos. Propuestos with `prioridad === null` are always visible
 * (v1 policy) — see `getVisiblePropuestaIds`.
 */
export const PROPUESTAS_ETAPAS_DEFAULTS: Record<Etapa, boolean> = {
  'Alta': true,
  'Media-Alta': true,
  'Media': true,
  'Opcional': true,
  'Largo plazo': true,
};

/**
 * Per-canal id derivation rules. The ETL uses `slugify(nombre)` with
 * collision suffixes; for the STORE keys we only need a valid JS identifier —
 * we take the slug from `index.json` and replace dashes with underscores so
 * the key stays stable and round-trippable.
 */
function perCanalKey(estado: 'relevado' | 'propuesto', slug: string): string {
  const safe = slug.replace(/-/g, '_');
  return `canal_${estado}_${safe}`;
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
  ign_historico: false,
  soil: false,
  catastro: false,
  hydraulic_risk: false,
  puntos_conflicto: false,
  // ── Pilar Azul — Escuelas rurales (design §7) ──
  // Single master toggle, default OFF. Opt-in per spec REQ-ESC-9.
  // No sub-toggles — the one layer carries all 7 features.
  escuelas: false,
  ...PILAR_VERDE_DEFAULT_VISIBILITY,
  ...PILAR_AZUL_DEFAULT_VISIBILITY,
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
  /**
   * Cached per-canal → prioridad lookup built at `registerPilarAzul` time.
   * Keys are the stable slugs from `index.json` (NOT the `canal_propuesto_*`
   * key form). Used by `getVisiblePropuestaIds` to apply the etapas filter.
   */
  canalesPropuestasPrioridad: Record<string, Etapa | null>;
  /** 5-key record — `true` means "show this etapa". */
  propuestasEtapasVisibility: Record<Etapa, boolean>;
}

interface PilarAzulActions {
  /** Toggle a single propuestas etapa on/off. */
  setEtapaVisible: (etapa: Etapa, visible: boolean) => void;
  /**
   * Bootstrap dynamic per-canal ids from the live `index.json`. Idempotent:
   * never clobbers a persisted user-flipped value — existing entries keep
   * their stored state, new entries seed as `true`.
   */
  registerPilarAzul: (index: IndexFile) => void;
  /**
   * Returns the list of currently-visible propuesta SLUGS (not store keys)
   * combining: master toggle, per-canal toggles, and etapa filter. Used by
   * the MapLibre `filter` expression to render only the intended subset.
   * Propuestos with `prioridad === null` are INCLUDED when their per-canal
   * toggle is on and the master is on (v1 policy — etapa filter doesn't
   * apply to them).
   */
  getVisiblePropuestaIds: (view: MapViewKey) => string[];
  /**
   * True iff a per-canal layer should render. Combines master toggle +
   * per-canal state (+ etapa filter for propuestos). Ids are the store keys
   * (`canal_relevado_*`, `canal_propuesto_*`) — unknown ids fall back to the
   * raw `visibleVectors[id]` for backwards compat with the rest of the layer
   * registry.
   */
  isCanalVisible: (view: MapViewKey, id: string) => boolean;
}

export const useMapLayerSyncStore = create<
  MapLayerSyncStoreState & SharedMapLayerActions & PilarAzulActions
>()(
  persist(
    (set, get) => ({
      map2d: DEFAULT_LAYER_STATE,
      map3d: DEFAULT_LAYER_STATE,
      initializedViews: { map2d: false, map3d: false },
      canalesPropuestasPrioridad: {},
      propuestasEtapasVisibility: { ...PROPUESTAS_ETAPAS_DEFAULTS },
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
      // ── Pilar Azul actions ────────────────────────────────────────────────
      setEtapaVisible: (etapa, visible) =>
        set((state) => ({
          propuestasEtapasVisibility: {
            ...state.propuestasEtapasVisibility,
            [etapa]: visible,
          },
        })),
      registerPilarAzul: (index) =>
        set((state) => {
          // Seed new per-canal entries to `true`, preserve any existing
          // (user-flipped / persisted) values. Both views mirror the same id
          // set because canales render on both map2d and map3d.
          const seedMap2d = { ...state.map2d.visibleVectors };
          const seedMap3d = { ...state.map3d.visibleVectors };
          const prioridadIndex: Record<string, Etapa | null> = {
            ...state.canalesPropuestasPrioridad,
          };

          for (const row of index.relevados) {
            const key = perCanalKey('relevado', row.id);
            if (!(key in seedMap2d)) seedMap2d[key] = true;
            if (!(key in seedMap3d)) seedMap3d[key] = true;
          }
          for (const row of index.propuestas) {
            const key = perCanalKey('propuesto', row.id);
            if (!(key in seedMap2d)) seedMap2d[key] = true;
            if (!(key in seedMap3d)) seedMap3d[key] = true;
            // `prioridad` is optional on the row type (absent on relevados,
            // nullable on propuestas). Normalize to `Etapa | null`.
            prioridadIndex[row.id] = row.prioridad ?? null;
          }

          return {
            map2d: { ...state.map2d, visibleVectors: seedMap2d },
            map3d: { ...state.map3d, visibleVectors: seedMap3d },
            canalesPropuestasPrioridad: prioridadIndex,
          };
        }),
      getVisiblePropuestaIds: (view) => {
        const state = get();
        const visibleVectors = state[view].visibleVectors;
        if (!visibleVectors.canales_propuestos) return [];
        const etapas = state.propuestasEtapasVisibility;
        const prioridadIndex = state.canalesPropuestasPrioridad;

        const out: string[] = [];
        for (const [slug, prioridad] of Object.entries(prioridadIndex)) {
          const key = perCanalKey('propuesto', slug);
          if (visibleVectors[key] === false) continue;
          // `null` prioridad → always visible (v1 policy — spec §Etapas Filter).
          if (prioridad !== null && etapas[prioridad] === false) continue;
          out.push(slug);
        }
        return out;
      },
      isCanalVisible: (view, id) => {
        const state = get();
        const vv = state[view].visibleVectors;
        if (id.startsWith('canal_relevado_')) {
          return !!vv.canales_relevados && vv[id] !== false;
        }
        if (id.startsWith('canal_propuesto_')) {
          if (!vv.canales_propuestos) return false;
          if (vv[id] === false) return false;
          // Etapa gate — decode slug → prioridad via the cached index.
          const slug = id.replace(/^canal_propuesto_/, '').replace(/_/g, '-');
          const prioridad = state.canalesPropuestasPrioridad[slug] ?? null;
          if (prioridad !== null && state.propuestasEtapasVisibility[prioridad] === false) {
            return false;
          }
          return true;
        }
        return !!vv[id];
      },
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
        canalesPropuestasPrioridad: state.canalesPropuestasPrioridad,
        propuestasEtapasVisibility: state.propuestasEtapasVisibility,
      }),
    },
  ),
);

// Re-export Etapa + ALL_ETAPAS here too so consumers can import them from the
// store if they don't want a second import from `types/canales`.
export { ALL_ETAPAS };
export type { Etapa };
