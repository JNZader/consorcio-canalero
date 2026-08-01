/**
 * useFichaInteraction — the ONE interaction-mode coordinator for the ficha
 * territorial (design §6.1/§6.2/§6.3, JDB-012/JDB-013).
 *
 * The design is explicit that there must NOT be a second independent state
 * machine that can also bind map clicks: measuring a distance/area, drawing a
 * ficha polygon and selecting a canal are mutually exclusive. This hook is the
 * single coordinator that makes that true. It owns the ficha's own state —
 * whether the user is drawing or in canal mode, the parcel resolved by a click,
 * the polygon just drawn, the canal + buffer chosen — and DERIVES the single
 * `MapInteractionMode` value threaded to `useMapInteractionEffects`:
 *
 *   interactionMode = drawing   ? 'ficha-dibujo'
 *                   : canalMode ? 'ficha-canal'
 *                   : measurementMode
 *
 * Mutual exclusion is enforced at the transitions, and the winner is named
 * explicitly:
 *   - entering draw OR canal mode (`startDraw` / `startCanal`) cancels any live
 *     measurement via `onEnterDrawMode` (the container passes `clearMeasurements`),
 *     so the measurement MapboxDraw releases its slot before the ficha
 *     `DrawControl` mounts — only ONE MapboxDraw instance ever exists at a time;
 *   - starting a measurement calls `stopDraw` (see the container), so drawing
 *     ends first;
 *   - starting draw clears canal mode and vice-versa (a union holds one value).
 *
 * Staleness (design §6.5, spec "Switching modes discards previous result"):
 * every mode transition clears the previous selection, so the panel never shows
 * one area's numbers while another is selected.
 */

import { useCallback, useState } from 'react';

import type { DrawnPolygon } from '../map/DrawControl';
import type { FichaRequest, FichaTipo } from '../../lib/api/ficha';
import { FICHA_DEFAULT_BUFFER_M } from '../../lib/api/ficha';
import type { MapInteractionMode, MeasurementMode } from './measurement/useMeasurement';
import type { ParcelaDisplayProps, ParcelaResuelta } from './useMapInteractionEffects';

/** The canal + buffer the user has selected for a `tipo=canal_buffer` request. */
export interface CanalSeleccionado {
  readonly canalId: number;
  readonly bufferM: number;
}

export interface FichaInteractionState {
  /** True while the free-draw polygon mode is active (`DrawControl` mounted). */
  readonly drawing: boolean;
  /** True while canal-selection mode is active (`vt_canal_network` clickable). */
  readonly canalMode: boolean;
  /** The catastro parcel resolved by the last idle click, or null. */
  readonly parcela: ParcelaResuelta | null;
  /** The polygon the user just drew (drives a `tipo=poligono` request), or null. */
  readonly poligono: DrawnPolygon | null;
  /** The canal + buffer selected (drives a `tipo=canal_buffer` request), or null. */
  readonly canal: CanalSeleccionado | null;
}

export interface UseFichaInteractionResult {
  readonly state: FichaInteractionState;
  /** The single interaction-mode value for `useMapInteractionEffects`. */
  readonly interactionMode: MapInteractionMode;
  /** The area of interest to fetch, or null when nothing is selected. */
  readonly request: FichaRequest | null;
  /** Wire tipo of the active selection (for the panel + BPA-join gating). */
  readonly tipo: FichaTipo;
  /** Account of the clicked parcel, for the client-side BPA join (null otherwise). */
  readonly nroCuenta: string | null;
  /** Display-only identity props of the clicked parcel, for the ficha header. */
  readonly parcelaProps: ParcelaDisplayProps | null;
  /** Enter free-draw mode; discards the previous ficha and cancels measurement. */
  readonly startDraw: () => void;
  /** Leave free-draw mode and clear the drawn ficha. */
  readonly stopDraw: () => void;
  /** A completed drawing → fires a `tipo=poligono` request (stays in draw mode). */
  readonly completePolygon: (geometry: DrawnPolygon) => void;
  /** The drawing was deleted → clear the polygon ficha. */
  readonly deletePolygon: () => void;
  /** Enter canal-selection mode; discards the previous ficha and cancels measurement. */
  readonly startCanal: () => void;
  /** Leave canal mode and clear the canal ficha. */
  readonly stopCanal: () => void;
  /** A canal click resolved (or did not resolve) a `canal_id`. */
  readonly resolveCanal: (canalId: number | null) => void;
  /** Adjust the buffer distance of the selected canal (re-fires the request). */
  readonly setBuffer: (bufferM: number) => void;
  /** An idle click resolved (or did not resolve) a parcel. */
  readonly resolveParcela: (parcela: ParcelaResuelta | null) => void;
  /** Close the panel / clear any current selection. */
  readonly clearFicha: () => void;
}

const IDLE: FichaInteractionState = {
  drawing: false,
  canalMode: false,
  parcela: null,
  poligono: null,
  canal: null,
};

export function useFichaInteraction(
  measurementMode: MeasurementMode,
  onEnterDrawMode: () => void
): UseFichaInteractionResult {
  const [state, setState] = useState<FichaInteractionState>(IDLE);

  const startDraw = useCallback(() => {
    // Measurement loses the shared MapboxDraw slot BEFORE the ficha DrawControl
    // mounts (mutual exclusion, structural). Switching into draw mode discards
    // whatever the panel was showing (spec: switching modes discards the result)
    // and leaves canal mode.
    onEnterDrawMode();
    setState({ ...IDLE, drawing: true });
  }, [onEnterDrawMode]);

  const stopDraw = useCallback(() => setState(IDLE), []);
  const clearFicha = useCallback(() => setState(IDLE), []);

  const completePolygon = useCallback((geometry: DrawnPolygon) => {
    // Stay in draw mode so the drawn shape remains visible while its ficha shows;
    // a fresh drawing supersedes any lingering parcel/canal selection.
    setState((prev) => ({ ...prev, parcela: null, canal: null, poligono: geometry }));
  }, []);

  const deletePolygon = useCallback(() => {
    setState((prev) => ({ ...prev, poligono: null }));
  }, []);

  const startCanal = useCallback(() => {
    // Same mutual-exclusion guarantee as startDraw: cancel any measurement, leave
    // draw mode, discard the previous ficha. Canal is not yet selected — the user
    // clicks a `vt_canal_network` line next.
    onEnterDrawMode();
    setState({ ...IDLE, canalMode: true });
  }, [onEnterDrawMode]);

  const stopCanal = useCallback(() => setState(IDLE), []);

  const resolveCanal = useCallback((canalId: number | null) => {
    setState((prev) => {
      // Only meaningful while in canal mode; a stray resolve otherwise is ignored.
      if (!prev.canalMode) return prev;
      if (canalId === null) return { ...prev, canal: null };
      // Keep the buffer the user already dialed in when they pick another canal.
      const bufferM = prev.canal?.bufferM ?? FICHA_DEFAULT_BUFFER_M;
      return { ...prev, parcela: null, poligono: null, canal: { canalId, bufferM } };
    });
  }, []);

  const setBuffer = useCallback((bufferM: number) => {
    setState((prev) => (prev.canal ? { ...prev, canal: { ...prev.canal, bufferM } } : prev));
  }, []);

  const resolveParcela = useCallback((parcela: ParcelaResuelta | null) => {
    // While drawing OR in canal mode, another control owns clicks — ignore parcel
    // resolution so a stray click cannot wipe the active selection. Otherwise a
    // fresh parcel click supersedes any drawn/canal ficha.
    setState((prev) => (prev.drawing || prev.canalMode ? prev : { ...IDLE, parcela }));
  }, []);

  const interactionMode: MapInteractionMode = state.drawing
    ? 'ficha-dibujo'
    : state.canalMode
      ? 'ficha-canal'
      : measurementMode;

  const request: FichaRequest | null = state.poligono
    ? // `DrawnPolygon` ({type:'Polygon', coordinates}) IS a valid GeoJSON geometry;
      // the request type is the looser `Record<string, unknown>`, hence the cast.
      { tipo: 'poligono', geometry: state.poligono as unknown as Record<string, unknown> }
    : state.canal
      ? { tipo: 'canal_buffer', canal_id: state.canal.canalId, buffer_m: state.canal.bufferM }
      : state.parcela
        ? { tipo: 'parcela', nomenclatura: state.parcela.nomenclatura }
        : null;

  const tipo: FichaTipo = state.poligono ? 'poligono' : state.canal ? 'canal_buffer' : 'parcela';

  return {
    state,
    interactionMode,
    request,
    tipo,
    nroCuenta: state.parcela?.nroCuenta ?? null,
    parcelaProps: state.parcela?.props ?? null,
    startDraw,
    stopDraw,
    completePolygon,
    deletePolygon,
    startCanal,
    stopCanal,
    resolveCanal,
    setBuffer,
    resolveParcela,
    clearFicha,
  };
}
