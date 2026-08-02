import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

import { ALL_ETAPAS, type Etapa, type IndexFile } from '../types/canales';

export interface SharedMapLayerState {
  activeRasterType: string | null;
  visibleVectors: Record<string, boolean>;
  /**
   * Per-layer opacity MULTIPLIER (0..1) keyed by UI layer id. `1` (or absent)
   * means "untouched" — the hardcoded default paint is applied verbatim. The
   * imperative apply step (`applyLayerOpacity`) skips any id that is absent or
   * exactly 1 so the default rendering stays byte-identical. Default `{}`.
   */
  opacityByLayer: Record<string, number>;
  /**
   * Desired render order (bottom → top) as a list of UI layer ids. Empty
   * means "use the hardcoded default order" — the imperative apply step
   * (`applyLayerOrder`) is a no-op on an empty list. Default `[]`.
   */
  orderByLayer: string[];
}

type MapViewKey = 'map2d' | 'map3d';

interface SharedMapLayerActions {
  setActiveRasterType: (view: MapViewKey, tipo: string | null) => void;
  setVectorVisibility: (view: MapViewKey, layerId: string, visible: boolean) => void;
  /** Set a per-layer opacity multiplier (clamped to 0..1). */
  setLayerOpacity: (view: MapViewKey, layerId: string, value: number) => void;
  /** Replace the per-layer render order (bottom → top UI ids). */
  setLayerOrder: (view: MapViewKey, orderedIds: string[]) => void;
  hydrateViewState: (view: MapViewKey, payload: Partial<SharedMapLayerState>) => void;
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
  Alta: true,
  'Media-Alta': true,
  Media: true,
  Opcional: true,
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
  // Catastro rural starts ON: it is the ONLY affordance that makes the ficha
  // territorial discoverable — with the layer off a citizen clicks a parcel and
  // nothing happens at all. Flipped from `false` in the map-fluidity pass; the
  // v4 → v5 persist migration below carries existing visitors forward.
  catastro: true,
  hydraulic_risk: false,
  puntos_conflicto: false,
  // ── Pilar Azul — Escuelas rurales (design §7) ──
  // Single master toggle, default OFF. Opt-in per spec REQ-ESC-9.
  // No sub-toggles — the one layer carries all 7 features.
  escuelas: false,
  ...PILAR_VERDE_DEFAULT_VISIBILITY,
  ...PILAR_AZUL_DEFAULT_VISIBILITY,
};

// Map3D defaults intentionally mirror Map2D now — the historical OFF-by-
// default was a workaround for the render budget, but ``maxTileCacheSize``,
// ``prefetchZoomDelta: 0`` and the lazy-load of pilar verde / catastro /
// soil make starting with the core layers (roads, waterways, canales
// relevados) visible affordable on every viewer. The user sees a
// consistent map between the 2D and 3D toggles instead of a fresh-looking
// blank scene when they switch from 2D.
// Exported so the 3D viewer derives its startup visibility from THIS record
// instead of keeping a divergent copy (single source of truth for defaults).
export const MAP3D_DEFAULT_VISIBLE_VECTORS: Record<string, boolean> = {
  ...defaultVisibleVectors,
  // EXCEPTION to the 2D/3D mirror (map-fluidity T1): `catastro` was flipped ON
  // for 2D purely to make the ficha territorial discoverable — clicking a parcel
  // opens its ficha. The 3D terrain viewer has NO ficha, so mirroring the flip
  // would load a heavy vector-tile fill on every 3D mount for zero user benefit.
  // The 3D side therefore keeps the historical OFF default.
  catastro: false,
};
const defaultMap3dVisibleVectors = MAP3D_DEFAULT_VISIBLE_VECTORS;

const inMemoryStorage = {
  getItem: (_name: string) => null,
  setItem: (_name: string, _value: string) => undefined,
  removeItem: (_name: string) => undefined,
};

const storage = createJSONStorage(() => {
  if (typeof window === 'undefined') return inMemoryStorage;
  return window.localStorage;
});

const DEFAULT_MAP2D_LAYER_STATE: SharedMapLayerState = {
  activeRasterType: null,
  visibleVectors: defaultVisibleVectors,
  opacityByLayer: {},
  orderByLayer: [],
};

const DEFAULT_MAP3D_LAYER_STATE: SharedMapLayerState = {
  activeRasterType: null,
  visibleVectors: defaultMap3dVisibleVectors,
  opacityByLayer: {},
  orderByLayer: [],
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
  /**
   * Whether the 3D terrain viewer should request smoothed elevation tiles.
   * When ON, the per-tile request URL gets a `terrain_smoothing` query param
   * and the backend despikes DSM artefacts (trees, buildings) before
   * encoding to terrain-RGB. Persisted in localStorage so the preference
   * survives reloads — consistent with every other map toggle in this store.
   */
  terrainSmoothingEnabled: boolean;
  /**
   * Despike threshold used when smoothing is on. Maps 1-to-1 onto the
   * backend's despike_low / despike_med / despike_high methods (0.5, 1.5,
   * 3.0 m positive-spike threshold respectively). Default is `med` —
   * balances DSM artefact removal against preservation of canal-edge
   * micro-relief.
   */
  terrainSmoothingThreshold: 'low' | 'med' | 'high';
}

export type TerrainSmoothingThreshold = 'low' | 'med' | 'high';

interface PilarAzulActions {
  /** Toggle a single propuestas etapa on/off. */
  setEtapaVisible: (etapa: Etapa, visible: boolean) => void;
  /** Toggle 3D terrain smoothing on/off (persisted). */
  setTerrainSmoothingEnabled: (enabled: boolean) => void;
  /** Pick the despike threshold for 3D terrain smoothing (persisted). */
  setTerrainSmoothingThreshold: (threshold: 'low' | 'med' | 'high') => void;
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

/**
 * Persist migration — patches a persisted state blob forward to the current
 * schema version. Exported (not inlined) so it can be unit-tested directly:
 * the store's test harness mocks the `persist` middleware to a pass-through,
 * which would otherwise skip this callback entirely.
 *
 * Migration history:
 *   v1 → v2 (2026-05-18): force `terrainSmoothingEnabled = true`.
 *   v2 → v3 (2026-05-19): unify 3D defaults with 2D (roads/waterways/canales).
 *   v3 → v4 (2026-07-04): seed per-layer `opacityByLayer` / `orderByLayer`
 *     slots as `{}` / `[]` on both views WITHOUT touching any persisted
 *     visibility — empty = untouched default → no render change.
 *   v4 → v5 (map-fluidity T1): force `catastro = true` on map2d ONLY. The old
 *     default was `false`, so every returning visitor has a persisted `false`
 *     that would pin them to the broken experience (clicking a parcel does
 *     nothing because the clickable fill is hidden). Since the old value was
 *     the DEFAULT and not a considered choice, overriding it once is the
 *     correct call; the user can still switch it off afterwards and that
 *     choice persists. Only `catastro` is touched — every other persisted
 *     preference is carried through untouched.
 */
export function migrateMapLayerState(
  persistedState: unknown,
  fromVersion: number
): Partial<MapLayerSyncStoreState> {
  const state = (persistedState as Partial<MapLayerSyncStoreState>) ?? {};
  let next = state;
  if (fromVersion < 2) {
    next = {
      ...next,
      terrainSmoothingEnabled: true,
      terrainSmoothingThreshold: next.terrainSmoothingThreshold ?? 'med',
    };
  }
  if (fromVersion < 3 && next.map3d) {
    next = {
      ...next,
      map3d: {
        ...next.map3d,
        visibleVectors: {
          ...next.map3d.visibleVectors,
          roads: true,
          waterways: true,
          waterways_rio_tercero: true,
          waterways_canal_desviador: true,
          waterways_canal_litin_tortugas: true,
          waterways_arroyo_algodon: true,
          waterways_arroyo_las_mojarras: true,
          canales_relevados: true,
        },
      },
    };
  }
  if (fromVersion < 4) {
    if (next.map2d) {
      next = {
        ...next,
        map2d: {
          ...next.map2d,
          opacityByLayer: next.map2d.opacityByLayer ?? {},
          orderByLayer: next.map2d.orderByLayer ?? [],
        },
      };
    }
    if (next.map3d) {
      next = {
        ...next,
        map3d: {
          ...next.map3d,
          opacityByLayer: next.map3d.opacityByLayer ?? {},
          orderByLayer: next.map3d.orderByLayer ?? [],
        },
      };
    }
  }
  if (fromVersion < 5) {
    // Catastro default flipped false → true on the 2D map. A persisted `false`
    // is the OLD DEFAULT, not a user choice, so we override it once. This is
    // the ONLY key the step touches — every other visibility flag (including
    // deliberate user OFFs) is preserved verbatim.
    //
    // map3d is INTENTIONALLY left alone: the 3D viewer has no ficha
    // territorial, so it keeps `catastro` off (see MAP3D_DEFAULT_VISIBLE_VECTORS).
    if (next.map2d) {
      next = {
        ...next,
        map2d: {
          ...next.map2d,
          visibleVectors: { ...next.map2d.visibleVectors, catastro: true },
        },
      };
    }
  }
  return next;
}

export const useMapLayerSyncStore = create<
  MapLayerSyncStoreState & SharedMapLayerActions & PilarAzulActions
>()(
  persist(
    (set, get) => ({
      map2d: DEFAULT_MAP2D_LAYER_STATE,
      map3d: DEFAULT_MAP3D_LAYER_STATE,
      initializedViews: { map2d: false, map3d: false },
      canalesPropuestasPrioridad: {},
      propuestasEtapasVisibility: { ...PROPUESTAS_ETAPAS_DEFAULTS },
      // Smoothing arranca ON: a 200× de exageración los picos de árboles y
      // edificios del DSM dominan visualmente y entorpecen lo que el
      // usuario va a leer (canales, depresiones, surcos). Si quiere ver el
      // DSM crudo, lo apaga desde el panel.
      terrainSmoothingEnabled: true,
      terrainSmoothingThreshold: 'med' as const,
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
      setLayerOpacity: (view, layerId, value) =>
        set((state) => ({
          [view]: {
            ...state[view],
            opacityByLayer: {
              ...state[view].opacityByLayer,
              [layerId]: Math.min(1, Math.max(0, value)),
            },
          },
          initializedViews: { ...state.initializedViews, [view]: true },
        })),
      setLayerOrder: (view, orderedIds) =>
        set((state) => ({
          [view]: {
            ...state[view],
            orderByLayer: [...orderedIds],
          },
          initializedViews: { ...state.initializedViews, [view]: true },
        })),
      hydrateViewState: (view, payload) =>
        set((state) => ({
          [view]: {
            ...state[view],
            activeRasterType: payload.activeRasterType ?? state[view].activeRasterType,
            visibleVectors: payload.visibleVectors
              ? { ...state[view].visibleVectors, ...payload.visibleVectors }
              : state[view].visibleVectors,
            opacityByLayer: payload.opacityByLayer
              ? { ...state[view].opacityByLayer, ...payload.opacityByLayer }
              : state[view].opacityByLayer,
            orderByLayer: payload.orderByLayer ?? state[view].orderByLayer,
          },
          initializedViews: { ...state.initializedViews, [view]: true },
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
      setTerrainSmoothingEnabled: (enabled) => set({ terrainSmoothingEnabled: enabled }),
      setTerrainSmoothingThreshold: (threshold) => set({ terrainSmoothingThreshold: threshold }),
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

        // "Show all when nothing is explicitly selected" — see `isCanalVisible`.
        const anyOn = Object.entries(visibleVectors).some(
          ([k, v]) => k.startsWith('canal_propuesto_') && v === true
        );

        const out: string[] = [];
        for (const [slug, prioridad] of Object.entries(prioridadIndex)) {
          const key = perCanalKey('propuesto', slug);
          const passesIndividual = anyOn ? visibleVectors[key] === true : true;
          if (!passesIndividual) continue;
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
          if (!vv.canales_relevados) return false;
          // "Show all when nothing is explicitly selected" — if no per-canal
          // relevado is in `true`, the master toggle alone is enough to show
          // every canal. As soon as the user marks even one individually,
          // gating reverts to "only the marked ones".
          const anyOn = Object.entries(vv).some(
            ([k, v]) => k.startsWith('canal_relevado_') && v === true
          );
          if (!anyOn) return true;
          return vv[id] === true;
        }
        if (id.startsWith('canal_propuesto_')) {
          if (!vv.canales_propuestos) return false;
          // Same policy as relevados — show all when nothing is explicitly
          // selected, otherwise gate by per-canal flag.
          const anyOn = Object.entries(vv).some(
            ([k, v]) => k.startsWith('canal_propuesto_') && v === true
          );
          const passesIndividual = anyOn ? vv[id] === true : true;
          if (!passesIndividual) return false;
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
      // Persist schema version. Bump this whenever you change a default that
      // existing users in production should pick up automatically — the
      // `migrate` callback below patches the persisted state before it
      // rehydrates the store, so we don't have to ask users to clear
      // localStorage by hand.
      //
      // Migration history:
      //   v1 → v2 (2026-05-18): force `terrainSmoothingEnabled = true` so
      //   the 3D viewer launches with the despike pipeline on by default.
      //   v2 → v3 (2026-05-19): unify 3D defaults with 2D so users see
      //   roads / waterways / canales_relevados ON on the 3D side too.
      //   v3 → v4 (2026-07-04): seed the per-layer `opacityByLayer` /
      //   `orderByLayer` slots (map-redesign Fase 3) as empty `{}` / `[]` on
      //   both views so existing users get the new fields without touching any
      //   persisted visibility. Empty = "untouched default" → no render change.
      //   v4 → v5 (map-fluidity T1): force `catastro = true` on map2d so
      //   returning visitors are not pinned to the old OFF default, which made
      //   the ficha territorial undiscoverable (clicking a parcel did nothing).
      //   map3d is untouched — the 3D viewer has no ficha.
      version: 5,
      migrate: (persistedState, fromVersion) => migrateMapLayerState(persistedState, fromVersion),
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
          // Per-layer opacity/order overrides (Fase 3) — persisted verbatim.
          opacityByLayer: state.map2d.opacityByLayer,
          orderByLayer: state.map2d.orderByLayer,
        },
        map3d: {
          ...state.map3d,
          visibleVectors: {
            ...state.map3d.visibleVectors,
            basins: false,
            hydraulic_risk: false,
            puntos_conflicto: false,
          },
          opacityByLayer: state.map3d.opacityByLayer,
          orderByLayer: state.map3d.orderByLayer,
        },
        initializedViews: state.initializedViews,
        canalesPropuestasPrioridad: state.canalesPropuestasPrioridad,
        propuestasEtapasVisibility: state.propuestasEtapasVisibility,
        terrainSmoothingEnabled: state.terrainSmoothingEnabled,
        terrainSmoothingThreshold: state.terrainSmoothingThreshold,
      }),
    }
  )
);

// Re-export Etapa + ALL_ETAPAS here too so consumers can import them from the
// store if they don't want a second import from `types/canales`.
export { ALL_ETAPAS };
export type { Etapa };
