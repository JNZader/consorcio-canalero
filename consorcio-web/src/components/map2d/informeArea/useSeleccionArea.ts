/**
 * useSeleccionArea — the selection state machine of the informe de área (PR 1).
 *
 * A plain `useReducer` reducer, no external state library: the selection is a
 * SET of `zonas_operativas` ids (the same uuid strings `/geo/basins` publishes
 * as `properties.id` and the ficha `tipo=zonas` expects as `zona_ids`), and
 * every interaction in the Elegir step maps to one action:
 *
 *   - plain click on the map  → `reemplazar` (the click REPLACES the selection)
 *   - ctrl/⌘+click / touch "Sumar a la selección" → `alternar` (suma o saca)
 *   - list checkbox           → `alternar`
 *   - "Toda la cuenca"        → `cuenca` with the cuenca's explicit ids
 *   - removable Pill          → `quitar`
 *
 * The reducer is deliberately catalog-FREE: actions carry explicit ids and
 * derivation helpers take the catalog as an argument, so the reducer stays
 * trivially testable and the catalog (an async fetch) can arrive in any order
 * relative to the first selection.
 *
 * CAP (S3): at most {@link LIMITE_ZONAS} subcuencas per selection (mirror of
 * the backend `schemas_ficha.FICHA_ZONAS_MAX` — the server re-checks the
 * RESOLVED union and answers 422 `cap_excedido` beyond it). Growing actions
 * (`sumar`, `alternar` adding, `reemplazar`, `cuenca` including) add ids in
 * incoming order and stop at the cap, so the wire request can never exceed 60
 * entries; the UI surfaces the cap with `cupoLleno` instead of failing at the
 * server.
 */

/** One selectable subcuenca, as the `/geo/basins` FeatureCollection describes it. */
export interface ZonaRef {
  readonly id: string;
  readonly nombre: string;
  readonly cuenca: string;
}

/**
 * Selection state per cuenca: `parcial` is the "Checkbox indeterminate" state
 * of S5 — some of the cuenca's zonas are selected, not all.
 */
export type EstadoCuenca = 'ninguna' | 'parcial' | 'toda';

/** The selection IS the id set; `Readonly` keeps reducers immutable by contract. */
export type SeleccionAreaState = ReadonlySet<string>;

/** Máximo 60 subcuencas por selección (S3; mirrors `schemas_ficha.FICHA_ZONAS_MAX`). */
export const LIMITE_ZONAS = 60;

export type SeleccionAreaAction =
  /** Sumar zonas (set union), clamped to {@link LIMITE_ZONAS}. */
  | { type: 'sumar'; ids: readonly string[] }
  /** Quitar zonas (set difference). */
  | { type: 'quitar'; ids: readonly string[] }
  /** Toggle one zona: suma si no está, saca si está (ctrl/⌘+click, checkbox). */
  | { type: 'alternar'; id: string }
  /** Plain map click: the new ids REPLACE the selection (clamped to the cap). */
  | { type: 'reemplazar'; ids: readonly string[] }
  /** "Toda la cuenca": union or difference with the cuenca's explicit ids. */
  | { type: 'cuenca'; ids: readonly string[]; incluir: boolean }
  /** Clear the whole selection. */
  | { type: 'vaciar' };

/** Union capped at {@link LIMITE_ZONAS}, preserving incoming order. */
function sumarConLimite(actual: SeleccionAreaState, ids: readonly string[]): Set<string> {
  const siguiente = new Set(actual);
  for (const id of ids) {
    if (siguiente.size >= LIMITE_ZONAS) break;
    siguiente.add(id);
  }
  return siguiente;
}

export function seleccionAreaReducer(
  state: SeleccionAreaState,
  action: SeleccionAreaAction
): SeleccionAreaState {
  switch (action.type) {
    case 'sumar':
      return sumarConLimite(state, action.ids);
    case 'quitar': {
      const siguiente = new Set(state);
      for (const id of action.ids) siguiente.delete(id);
      return siguiente;
    }
    case 'alternar': {
      if (state.has(action.id)) {
        const siguiente = new Set(state);
        siguiente.delete(action.id);
        return siguiente;
      }
      return sumarConLimite(state, [action.id]);
    }
    case 'reemplazar':
      return sumarConLimite(new Set(), action.ids);
    case 'cuenca':
      return action.incluir
        ? sumarConLimite(state, action.ids)
        : seleccionAreaReducer(state, { type: 'quitar', ids: action.ids });
    case 'vaciar':
      return new Set();
  }
}

// ── derivation helpers (pure; catalog passed in) ─────────────────────────────

/** How many subcuencas are selected. */
export function contarSeleccion(state: SeleccionAreaState): number {
  return state.size;
}

/** True when nothing is selected. */
export function seleccionVacia(state: SeleccionAreaState): boolean {
  return state.size === 0;
}

/** True when the selection hit the 60-subcuenca cap (S3) — the UI stops adding. */
export function cupoLleno(state: SeleccionAreaState): boolean {
  return state.size >= LIMITE_ZONAS;
}

/** The ids of one cuenca's zonas, in catalog order. */
export function idsDeCuenca(catalog: readonly ZonaRef[], cuenca: string): string[] {
  return catalog.filter((zona) => zona.cuenca === cuenca).map((zona) => zona.id);
}

/**
 * Selection state of one cuenca: `toda` when every zona of the cuenca is
 * selected, `ninguna` when none is, `parcial` otherwise — the indeterminate
 * Checkbox state of S5. A cuenca with no zonas in the catalog is `ninguna`.
 */
export function estadoCuenca(
  catalog: readonly ZonaRef[],
  cuenca: string,
  state: SeleccionAreaState
): EstadoCuenca {
  const ids = idsDeCuenca(catalog, cuenca);
  if (ids.length === 0) return 'ninguna';
  let seleccionadas = 0;
  for (const id of ids) {
    if (state.has(id)) seleccionadas += 1;
  }
  if (seleccionadas === 0) return 'ninguna';
  return seleccionadas === ids.length ? 'toda' : 'parcial';
}

/** The selected zonas, in CATALOG order (stable Pill list, stable request ids). */
export function zonasSeleccionadas(
  catalog: readonly ZonaRef[],
  state: SeleccionAreaState
): ZonaRef[] {
  return catalog.filter((zona) => state.has(zona.id));
}

/**
 * Stable identity of the selection for query keys: sorted ids joined, so two
 * selections built in different click order share one cache entry.
 */
export function claveDeSeleccion(state: SeleccionAreaState): string {
  return [...state].sort().join(',');
}
