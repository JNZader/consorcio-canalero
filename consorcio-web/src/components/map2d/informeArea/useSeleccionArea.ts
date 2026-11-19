/**
 * useSeleccionArea — the selection state machine of the informe de área (PR 1).
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

import type { MultiPolygon, Polygon } from 'geojson';

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

// ── PR 3: geometries of the MIXED selection (zonas + dibujo + archivo) ───────
//
// The zonas reducer above is UNCHANGED on purpose: its contract (a plain id
// Set) is what the whole PR 1 surface (map clicks, lista, cuenca expansion)
// and its test suite are written against. The drawn/imported polygons are a
// SECOND, parallel list — same module, same pure-function discipline — and
// the mixed helpers below compose both halves at the edges (preview query,
// create payload, chips). A drawn polygon has no catalog row to key on, so
// it carries a synthetic id from the moment it enters the selection.

/** One drawn or imported polygon inside the selection (PR 3, S1). */
export interface SeleccionGeometria {
  /** Synthetic stable id (`dibujo-3`, `archivo-7f2a…`) — the Pill/removal key. */
  readonly id: string;
  readonly origen: 'dibujo' | 'archivo';
  /** Human label for the Chip: "Dibujo 2", "lote.kml · Polígono 1". */
  readonly etiqueta: string;
  /** Client-measured hectares (@turf/area) — shown on the Checkbox/Pill. */
  readonly ha: number;
  readonly geometry: Polygon | MultiPolygon;
}

/**
 * The combined cap, in zonas-equivalents (S5): the backend counts
 * `len(zona_ids) + len(geometrias)` against its 120 and so does the UI —
 * the zona-only 60 above stays the LIST's own bound (it mirrors the ficha
 * preview's tighter cap, a different contract).
 */
export const LIMITE_SELECCION_MIXTA = 120;

/** The wire side of the geometry list: bare geometries, no UI metadata. */
export function geometriasDeSeleccion(
  geometrias: readonly SeleccionGeometria[]
): (Polygon | MultiPolygon)[] {
  return geometrias.map((geometria) => geometria.geometry);
}

/** True when NEITHER zonas nor geometrias are selected. */
export function seleccionMixtaVacia(
  zonas: SeleccionAreaState,
  geometrias: readonly SeleccionGeometria[]
): boolean {
  return zonas.size === 0 && geometrias.length === 0;
}

/** Combined zonas-equivalents count (the LIMITE_SELECCION_MIXTA unit). */
export function contarSeleccionMixta(
  zonas: SeleccionAreaState,
  geometrias: readonly SeleccionGeometria[]
): number {
  return zonas.size + geometrias.length;
}

/** True when adding one more element would exceed the combined cap. */
export function cupoMixtoLleno(
  zonas: SeleccionAreaState,
  geometrias: readonly SeleccionGeometria[]
): boolean {
  return contarSeleccionMixta(zonas, geometrias) >= LIMITE_SELECCION_MIXTA;
}

/**
 * Stable FNV-1a 32-bit hash of a geometry's JSON — deterministic across
 * sessions and tab reloads, unlike identity or insertion order.
 */
function hashGeometria(geometry: Polygon | MultiPolygon): string {
  const texto = JSON.stringify(geometry);
  let hash = 0x811c9dc5;
  for (let i = 0; i < texto.length; i += 1) {
    hash ^= texto.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash.toString(16).padStart(8, '0');
}

/**
 * Query-key identity of the WHOLE mixed selection: the zonas clave plus the
 * geometry hashes in selection order. Same selection → same clave → one
 * preview cache entry, regardless of how it was assembled.
 */
export function claveSeleccionMixta(
  zonas: SeleccionAreaState,
  geometrias: readonly SeleccionGeometria[]
): string {
  const parteZonas = claveDeSeleccion(zonas);
  if (geometrias.length === 0) return parteZonas;
  const parteGeometrias = geometrias
    .map((geometria) => hashGeometria(geometria.geometry))
    .join(',');
  return `${parteZonas}|${parteGeometrias}`;
}
