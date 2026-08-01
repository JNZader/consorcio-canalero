/**
 * useFichaInteraction — the ONE interaction-mode coordinator for the ficha
 * territorial (design §6.1/§6.2, JDB-012).
 *
 * The design is explicit that there must NOT be a second independent state
 * machine that can also bind map clicks: measuring a distance/area and drawing a
 * ficha polygon are mutually exclusive. This hook is the single coordinator that
 * makes that true. It owns the ficha's own state — whether the user is drawing,
 * the parcel resolved by a click, the polygon just drawn — and DERIVES the single
 * `MapInteractionMode` value threaded to `useMapInteractionEffects`:
 *
 *   interactionMode = drawing ? 'ficha-dibujo' : measurementMode
 *
 * Mutual exclusion is enforced at the transitions, and the winner is named
 * explicitly:
 *   - entering draw mode (`startDraw`) cancels any live measurement via
 *     `onEnterDrawMode` (the container passes `clearMeasurements`), so the
 *     measurement MapboxDraw releases its slot before the ficha `DrawControl`
 *     mounts — only ONE MapboxDraw instance ever exists at a time;
 *   - starting a measurement calls `stopDraw` (see the container), so drawing
 *     ends first.
 * Because only one of {drawing, measurement} is ever non-idle, `ficha-dibujo`
 * "winning" the derived mode is a formality, not a race.
 *
 * Staleness (design §6.5, spec "Switching modes discards previous result"):
 * `startDraw` clears the previous parcel ficha and any previous drawing, and
 * a parcel click clears a drawn ficha and vice-versa. The panel therefore never
 * shows one area's numbers while another is selected.
 */

import { useCallback, useState } from 'react';

import type { DrawnPolygon } from '../map/DrawControl';
import type { FichaRequest } from '../../lib/api/ficha';
import type { MapInteractionMode, MeasurementMode } from './measurement/useMeasurement';
import type { ParcelaResuelta } from './useMapInteractionEffects';

export interface FichaInteractionState {
  /** True while the free-draw polygon mode is active (`DrawControl` mounted). */
  readonly drawing: boolean;
  /** The catastro parcel resolved by the last idle click, or null. */
  readonly parcela: ParcelaResuelta | null;
  /** The polygon the user just drew (drives a `tipo=poligono` request), or null. */
  readonly poligono: DrawnPolygon | null;
}

export interface UseFichaInteractionResult {
  readonly state: FichaInteractionState;
  /** The single interaction-mode value for `useMapInteractionEffects`. */
  readonly interactionMode: MapInteractionMode;
  /** The area of interest to fetch, or null when nothing is selected. */
  readonly request: FichaRequest | null;
  /** Wire tipo of the active selection (for the panel + BPA-join gating). */
  readonly tipo: 'parcela' | 'poligono';
  /** Account of the clicked parcel, for the client-side BPA join (null otherwise). */
  readonly nroCuenta: string | null;
  /** Enter free-draw mode; discards the previous ficha and cancels measurement. */
  readonly startDraw: () => void;
  /** Leave free-draw mode and clear the drawn ficha. */
  readonly stopDraw: () => void;
  /** A completed drawing → fires a `tipo=poligono` request (stays in draw mode). */
  readonly completePolygon: (geometry: DrawnPolygon) => void;
  /** The drawing was deleted → clear the polygon ficha. */
  readonly deletePolygon: () => void;
  /** An idle click resolved (or did not resolve) a parcel. */
  readonly resolveParcela: (parcela: ParcelaResuelta | null) => void;
  /** Close the panel / clear any current selection. */
  readonly clearFicha: () => void;
}

const IDLE: FichaInteractionState = { drawing: false, parcela: null, poligono: null };

export function useFichaInteraction(
  measurementMode: MeasurementMode,
  onEnterDrawMode: () => void
): UseFichaInteractionResult {
  const [state, setState] = useState<FichaInteractionState>(IDLE);

  const startDraw = useCallback(() => {
    // Measurement loses the shared MapboxDraw slot BEFORE the ficha DrawControl
    // mounts (mutual exclusion, structural). Switching into draw mode discards
    // whatever the panel was showing (spec: switching modes discards the result).
    onEnterDrawMode();
    setState({ drawing: true, parcela: null, poligono: null });
  }, [onEnterDrawMode]);

  const stopDraw = useCallback(() => setState(IDLE), []);
  const clearFicha = useCallback(() => setState(IDLE), []);

  const completePolygon = useCallback((geometry: DrawnPolygon) => {
    // Stay in draw mode so the drawn shape remains visible while its ficha shows;
    // a fresh drawing supersedes any lingering parcel selection.
    setState((prev) => ({ ...prev, parcela: null, poligono: geometry }));
  }, []);

  const deletePolygon = useCallback(() => {
    setState((prev) => ({ ...prev, poligono: null }));
  }, []);

  const resolveParcela = useCallback((parcela: ParcelaResuelta | null) => {
    // While drawing, DrawControl owns clicks — ignore parcel resolution so a
    // stray click cannot wipe the polygon the user just drew. Otherwise a fresh
    // parcel click supersedes any drawn ficha.
    setState((prev) => (prev.drawing ? prev : { drawing: false, parcela, poligono: null }));
  }, []);

  const interactionMode: MapInteractionMode = state.drawing ? 'ficha-dibujo' : measurementMode;

  const request: FichaRequest | null = state.poligono
    ? // `DrawnPolygon` ({type:'Polygon', coordinates}) IS a valid GeoJSON geometry;
      // the request type is the looser `Record<string, unknown>`, hence the cast.
      { tipo: 'poligono', geometry: state.poligono as unknown as Record<string, unknown> }
    : state.parcela
      ? { tipo: 'parcela', nomenclatura: state.parcela.nomenclatura }
      : null;

  return {
    state,
    interactionMode,
    request,
    tipo: state.poligono ? 'poligono' : 'parcela',
    nroCuenta: state.parcela?.nroCuenta ?? null,
    startDraw,
    stopDraw,
    completePolygon,
    deletePolygon,
    resolveParcela,
    clearFicha,
  };
}
