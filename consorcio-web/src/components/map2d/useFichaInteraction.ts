/**
 * useFichaInteraction — the ONE interaction-mode coordinator for the ficha
 * territorial (design §6.1/§6.2/§6.3, JDB-012/JDB-013).
 *
 * The design is explicit that there must NOT be a second independent state
 * machine that can also bind map clicks: measuring a distance/area, drawing a
 * ficha polygon and selecting a canal are mutually exclusive. This hook is the
 * single coordinator that makes that true. It owns the ficha's own state —
 * whether the user is drawing or in canal mode, the parcel resolved by a click,
 * the polygon just drawn, the canal + its analysis (buffer/cuenca) chosen — and
 * DERIVES the single `MapInteractionMode` value threaded to
 * `useMapInteractionEffects`:
 *
 *   interactionMode = tracing   ? 'ficha-dibujo'
 *                   : canalMode ? 'ficha-canal'
 *                   : measurementMode
 *
 * `tracing` — not `drawing` — because MapboxDraw returns to `simple_select` by
 * itself on `draw.create`: see {@link FichaInteractionState.tracing}.
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
 * Canal analysis (A6 + A7): once a CURATED canal is clicked the user picks how to
 * analyze it — a fixed-width influence strip (`buffer` → `tipo=canal_buffer`) or
 * its real upstream catchment (`cuenca` → `tipo=canal_cuenca`). The choice lives
 * here so the derived request switches wire `tipo` accordingly.
 *
 * Multi-parcel selection (T4): parcel clicks ACCUMULATE when the user holds
 * ctrl/⌘ (desktop) or turns the "Selección múltiple" toggle on (touch, where
 * there is no modifier key). The accumulated set lives in `state.parcelas` and
 * is the ONLY source of truth for the parcel request — 1 entry is
 * `tipo=parcela`, 2+ is `tipo=parcelas` over a union the SERVER builds from
 * `parcelas_catastro`. The tile geometries the clicks resolved are clipped and
 * simplified, so they are never unioned client-side.
 *
 * SETTLING (T4 fix round): a multi-parcel request is DEBOUNCED. Each click is
 * one full server-side analysis (ST_Union + raster IO, rate-limit cost 5, and a
 * bounded `ficha_max_concurrency` pool), so firing one per ctrl-click meant six
 * quick clicks paid for six analyses of which five were thrown away — while
 * eating the caller's own rate-limit budget. The SELECTION still updates on
 * every click (state + highlight are instantaneous); only the derivation of the
 * wire REQUEST waits for the selection to sit still for
 * {@link FICHA_PARCELAS_SETTLE_MS}. A single-parcel click is NOT debounced:
 * it is the pre-T4 interaction and it costs one cheap analysis.
 *
 * Staleness (design §6.5, spec "Switching modes discards previous result"):
 * every mode transition clears the previous selection, so the panel never shows
 * one area's numbers while another is selected. That contract is stronger than
 * the sticky-mode miss rule: a tap that MISSES while "selección múltiple" is on
 * keeps the selection, but entering a measurement is a MODE TRANSITION and
 * always clears it (`clearParcelas`).
 *
 * Sticky mode caveat: while `multiSelect` is on there is no plain click left to
 * reset the selection (every tap accumulates), so the panel's close button is
 * the reset affordance — that is what `clearFicha` is wired to. `multiSelect`
 * itself survives every reset EXCEPT the ones that rebuild the whole state from
 * `IDLE` (draw / canal / `clearFicha` / `stopDraw` / `stopCanal`), which turn
 * the touch mode off along with everything else.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import type { DrawnPolygon } from '../map/DrawControl';
import type { FichaRequest, FichaTipo } from '../../lib/api/ficha';
import {
  FICHA_DEFAULT_BUFFER_M,
  FICHA_PARCELAS_MAX,
  FICHA_PARCELAS_MIN,
} from '../../lib/api/ficha';
import type { MapInteractionMode, MeasurementMode } from './measurement/useMeasurement';
import type {
  CanalResuelta,
  ParcelaDisplayProps,
  ParcelaResuelta,
} from './useMapInteractionEffects';

/** How the user chose to analyze the selected canal. */
export type CanalAnalysisMode = 'buffer' | 'cuenca';

/** The curated canal + how it is being analyzed (drives a canal_* request). */
export interface CanalSeleccionado {
  /** The `canal_consorcio` string id. */
  readonly canalRef: string;
  /** Display name for the analysis control. */
  readonly canalNombre: string;
  /** Buffer half-width (metres) — only used when `analysisMode === 'buffer'`. */
  readonly bufferM: number;
  /** Influence strip (`buffer`) vs real catchment (`cuenca`). */
  readonly analysisMode: CanalAnalysisMode;
}

export interface FichaInteractionState {
  /** True while the free-draw polygon mode is active (`DrawControl` mounted). */
  readonly drawing: boolean;
  /**
   * True only while MapboxDraw is actually TRACING (`draw_polygon`), i.e. while
   * it owns every map click.
   *
   * `drawing` and `tracing` are NOT the same thing and conflating them was a bug
   * (T4): MapboxDraw drops back to `simple_select` by itself the instant
   * `draw.create` fires, but React kept `drawing` true, so `interactionMode`
   * stayed `'ficha-dibujo'` and `buildClickableLayers` kept returning an EMPTY
   * whitelist. The user finished their polygon and the map went dead — every
   * click a no-op until they happened to press Escape. `tracing` mirrors
   * MapboxDraw's real mode, so click ownership is released exactly when
   * MapboxDraw releases it, while `drawing` keeps the control mounted (the
   * polygon stays on screen) and the toolbar lit (Otro / Borrar stay reachable).
   */
  readonly tracing: boolean;
  /** True while canal-selection mode is active (curated canal layers clickable). */
  readonly canalMode: boolean;
  /**
   * The catastro parcel resolved by the last idle click, or null.
   *
   * DISPLAY ONLY since T4 — the request is derived from {@link parcelas}. This
   * carries the whitelisted identity props of the parcel the user last clicked,
   * which the panel shows only while the selection is exactly that one parcel.
   */
  readonly parcela: ParcelaResuelta | null;
  /**
   * The accumulated multi-parcel selection: sorted, unique nomenclaturas (T4).
   *
   * This is THE parcel selection — a plain click leaves one entry here, a
   * ctrl-click adds or removes one. Length drives the wire shape: 0 → no parcel
   * ficha, 1 → `tipo=parcela`, 2+ → `tipo=parcelas` over the server-side union.
   * Sorted so that the same SET of parcels always produces the same request and
   * therefore the same selection key.
   */
  readonly parcelas: readonly string[];
  /**
   * Identity props of the selected parcels, keyed by nomenclatura (T4 fix round).
   *
   * Populated from every RESOLVED click and pruned to {@link parcelas}, so it is
   * bounded by the selection cap and never outlives what it describes. Its whole
   * job is the deselect-to-one case: ctrl-clicking B away from `[A, B]` leaves a
   * single-parcel selection whose identity header must come back, and the only
   * parcel the coordinator had in hand at that moment was B — the one being
   * REMOVED. Looking the survivor up here is what restores the header.
   */
  readonly parcelasResueltas: Readonly<Record<string, ParcelaResuelta>>;
  /**
   * Monotonic count of clicks DROPPED by {@link FICHA_PARCELAS_MAX} (T4 fix
   * round). At the cap an additive click used to be a silent no-op; the
   * container watches this counter to surface a notification. It is a counter,
   * not a boolean, so the Nth consecutive capped click is still distinguishable
   * from the (N-1)th.
   */
  readonly capHits: number;
  /**
   * Touch/mobile accumulation mode (T4). While ON, EVERY parcel tap accumulates
   * exactly as a ctrl-click does — there is no ctrl key on a touch screen, and a
   * long-press is already taken by the browser's context menu.
   */
  readonly multiSelect: boolean;
  /** The polygon the user just drew (drives a `tipo=poligono` request), or null. */
  readonly poligono: DrawnPolygon | null;
  /** The canal + analysis selected (drives a `tipo=canal_buffer|canal_cuenca` request), or null. */
  readonly canal: CanalSeleccionado | null;
}

export interface UseFichaInteractionResult {
  readonly state: FichaInteractionState;
  /** The single interaction-mode value for `useMapInteractionEffects`. */
  readonly interactionMode: MapInteractionMode;
  /** The area of interest to fetch, or null when nothing is selected. */
  readonly request: FichaRequest | null;
  /**
   * The parcels the CURRENT {@link request} actually analyzes (T4 fix round).
   *
   * Equal to `state.parcelas` except while a multi-parcel selection is still
   * settling, when it lags by up to {@link FICHA_PARCELAS_SETTLE_MS}. Anything
   * that must agree with the NUMBERS on screen (the panel's "N parcelas · X ha"
   * header) reads this; anything that reflects the user's SELECTION (the map
   * highlight) reads `state.parcelas` and updates on every click.
   */
  readonly parcelasAnalizadas: readonly string[];
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
  /**
   * "Otro" — trace a replacement polygon without leaving the draw session.
   *
   * Keeps the current polygon (and its ficha) on screen until the new
   * `draw.create` replaces it, and hands click ownership back to MapboxDraw.
   */
  readonly redrawPolygon: () => void;
  /** Enter canal-selection mode; discards the previous ficha and cancels measurement. */
  readonly startCanal: () => void;
  /** Leave canal mode and clear the canal ficha. */
  readonly stopCanal: () => void;
  /** A canal click resolved (or did not resolve) a curated canal. */
  readonly resolveCanal: (canal: CanalResuelta | null) => void;
  /** Adjust the buffer distance of the selected canal (re-fires the request). */
  readonly setBuffer: (bufferM: number) => void;
  /** Switch the selected canal between influence-strip and catchment analysis. */
  readonly setCanalAnalysisMode: (mode: CanalAnalysisMode) => void;
  /**
   * An idle click resolved (or did not resolve) a parcel.
   *
   * `additive` (T4) is the ctrl/⌘ modifier read off the DOM event by
   * `useMapInteractionEffects`. It is OR-ed here with the sticky
   * {@link FichaInteractionState.multiSelect} mode, so the caller never has to
   * know about the mobile toggle — and the click handler never has to
   * re-subscribe when that toggle flips.
   */
  readonly resolveParcela: (parcela: ParcelaResuelta | null, additive?: boolean) => void;
  /** Turn the touch accumulation mode on/off (T4). Keeps the current selection. */
  readonly setMultiSelect: (on: boolean) => void;
  /**
   * Drop specific parcels from the selection (T4 fix round).
   *
   * The recovery path for a 404 `parcela_no_encontrada`: the server names the
   * nomenclaturas it could not resolve, and until this existed a selection
   * containing one stale parcel could only be rebuilt from scratch, because the
   * missing parcel is by definition not on the map to ctrl-click away.
   */
  readonly removeParcelas: (nomenclaturas: readonly string[]) => void;
  /**
   * Discard the parcel selection WITHOUT touching the interaction modes.
   *
   * This is the mode-transition clear (a measurement starting), which is NOT the
   * same event as a click that missed: a sticky-mode tap-miss keeps the
   * selection on purpose, a mode transition always discards it (design §6.5).
   * Collapsing the two into `resolveParcela(null)` is what let a measurement
   * leave a stale ficha on screen while "selección múltiple" was on.
   */
  readonly clearParcelas: () => void;
  /** Close the panel / clear any current selection. */
  readonly clearFicha: () => void;
}

/**
 * Idle time (ms) a multi-parcel selection must sit still before its request is
 * derived. Long enough to absorb a burst of ctrl-clicks (a deliberate second
 * click lands well inside it), short enough that the wait reads as the analysis
 * starting rather than as the UI being stuck.
 */
export const FICHA_PARCELAS_SETTLE_MS = 600;

const IDLE: FichaInteractionState = {
  drawing: false,
  tracing: false,
  canalMode: false,
  parcela: null,
  parcelas: [],
  parcelasResueltas: {},
  capHits: 0,
  multiSelect: false,
  poligono: null,
  canal: null,
};

/**
 * Keep only the resolved parcels still present in the selection.
 *
 * Bounds the map by {@link FICHA_PARCELAS_MAX} and, more importantly, keeps it
 * HONEST: a stale entry for a deselected parcel could resurface as the identity
 * header of a later single-parcel selection.
 */
function podarResueltas(
  resueltas: Readonly<Record<string, ParcelaResuelta>>,
  parcelas: readonly string[]
): Record<string, ParcelaResuelta> {
  const podadas: Record<string, ParcelaResuelta> = {};
  for (const nomenclatura of parcelas) {
    const resuelta = resueltas[nomenclatura];
    if (resuelta) podadas[nomenclatura] = resuelta;
  }
  return podadas;
}

/**
 * Add or remove one parcel from an accumulated selection (T4).
 *
 * Toggle semantics: ctrl-clicking a parcel that is ALREADY selected removes it,
 * which is the only deselect affordance the map has. The result is sorted so the
 * selection's identity is its SET, not the order the user happened to click in.
 *
 * At {@link FICHA_PARCELAS_MAX} the selection stops GROWING but never breaks:
 * removing still works, and re-clicking an already-selected parcel still
 * deselects it. Dropping the extra click is better than letting the user build a
 * request the server can only answer with a 422 they cannot act on — but it is
 * reported (`capped`) instead of being silent, because a click that changes
 * nothing and says nothing reads as a broken map.
 */
function toggleParcela(
  seleccion: readonly string[],
  nomenclatura: string
): { readonly parcelas: string[]; readonly capped: boolean } {
  if (seleccion.includes(nomenclatura)) {
    return {
      parcelas: seleccion.filter((n) => n !== nomenclatura),
      capped: false,
    };
  }
  if (seleccion.length >= FICHA_PARCELAS_MAX) {
    return { parcelas: [...seleccion], capped: true };
  }
  return { parcelas: [...seleccion, nomenclatura].sort(), capped: false };
}

export function useFichaInteraction(
  measurementMode: MeasurementMode,
  onEnterDrawMode: () => void,
  /**
   * Called once per click DROPPED by {@link FICHA_PARCELAS_MAX} (T4 fix round).
   * The container turns it into a notification; the hook stays free of any UI
   * dependency and the behaviour is assertable without rendering a toast.
   */
  onParcelasCapReached?: () => void
): UseFichaInteractionResult {
  const [state, setState] = useState<FichaInteractionState>(IDLE);

  const startDraw = useCallback(() => {
    // Measurement loses the shared MapboxDraw slot BEFORE the ficha DrawControl
    // mounts (mutual exclusion, structural). Switching into draw mode discards
    // whatever the panel was showing (spec: switching modes discards the result)
    // and leaves canal mode.
    onEnterDrawMode();
    setState({ ...IDLE, drawing: true, tracing: true });
  }, [onEnterDrawMode]);

  const stopDraw = useCallback(() => setState(IDLE), []);
  const clearFicha = useCallback(() => setState(IDLE), []);

  const completePolygon = useCallback((geometry: DrawnPolygon) => {
    // Stay in draw mode so the drawn shape remains visible while its ficha shows;
    // a fresh drawing supersedes any lingering parcel/canal selection.
    //
    // But STOP TRACING (T4): MapboxDraw already went back to `simple_select` on
    // its own, so holding the click whitelist hostage past this point is what
    // left the map dead after a finished polygon.
    setState((prev) => ({
      ...prev,
      tracing: false,
      parcela: null,
      parcelas: [],
      parcelasResueltas: {},
      canal: null,
      poligono: geometry,
    }));
  }, []);

  const deletePolygon = useCallback(() => {
    // `clearDrawing` only calls `deleteAll()`, which does NOT change MapboxDraw's
    // mode — it stays in `simple_select`, so tracing stays off too.
    setState((prev) => ({ ...prev, poligono: null }));
  }, []);

  const redrawPolygon = useCallback(() => {
    // "Otro" — re-enter `draw_polygon` with REPLACE semantics. The polygon (and
    // therefore the ficha on screen) is KEPT until the new `draw.create`
    // supersedes it, exactly as `DrawControl.startDrawing`'s silent `deleteAll()`
    // intends; only click ownership goes back to MapboxDraw. Without flipping
    // `tracing` here the whitelist would stay populated during the new trace and
    // a click meant for a vertex would resolve a parcel instead.
    setState((prev) => (prev.drawing ? { ...prev, tracing: true } : prev));
  }, []);

  const startCanal = useCallback(() => {
    // Same mutual-exclusion guarantee as startDraw: cancel any measurement, leave
    // draw mode, discard the previous ficha. Canal is not yet selected — the user
    // clicks a curated relevados/propuestos line next.
    onEnterDrawMode();
    setState({ ...IDLE, canalMode: true });
  }, [onEnterDrawMode]);

  const stopCanal = useCallback(() => setState(IDLE), []);

  const resolveCanal = useCallback((canal: CanalResuelta | null) => {
    setState((prev) => {
      // Only meaningful while in canal mode; a stray resolve otherwise is ignored.
      if (!prev.canalMode) return prev;
      if (canal === null) return { ...prev, canal: null };
      // Keep the buffer + analysis mode the user already chose when they pick another canal.
      const bufferM = prev.canal?.bufferM ?? FICHA_DEFAULT_BUFFER_M;
      const analysisMode = prev.canal?.analysisMode ?? 'buffer';
      return {
        ...prev,
        parcela: null,
        parcelas: [],
        parcelasResueltas: {},
        poligono: null,
        canal: {
          canalRef: canal.ref,
          canalNombre: canal.nombre,
          bufferM,
          analysisMode,
        },
      };
    });
  }, []);

  const setBuffer = useCallback((bufferM: number) => {
    setState((prev) => (prev.canal ? { ...prev, canal: { ...prev.canal, bufferM } } : prev));
  }, []);

  const setCanalAnalysisMode = useCallback((analysisMode: CanalAnalysisMode) => {
    setState((prev) => (prev.canal ? { ...prev, canal: { ...prev.canal, analysisMode } } : prev));
  }, []);

  const resolveParcela = useCallback((parcela: ParcelaResuelta | null, additive = false) => {
    setState((prev) => {
      // While TRACING or in canal mode, another control owns clicks — ignore
      // parcel resolution so a stray click cannot wipe the active selection.
      // Once the polygon is finished (T4) clicks belong to the map again: the
      // parcel ficha then supersedes the polygon ficha, which also ends the draw
      // session (`IDLE.drawing === false` unmounts `DrawControl`).
      if (prev.tracing || prev.canalMode) return prev;

      // The ctrl/⌘ modifier and the sticky mobile toggle mean the same thing.
      // OR-ing them HERE (instead of in the click handler) keeps the map's click
      // subscription independent of the toggle: reading `multiSelect` inside the
      // updater cannot go stale, whereas a handler closing over it would have to
      // re-subscribe on every flip.
      const acumular = additive || prev.multiSelect;

      if (parcela === null) {
        // An accumulating click that hits empty space is a MISS, not a reset:
        // wiping a five-parcel selection because the user's ctrl-click landed on
        // a road would be unrecoverable. A plain click still clears, unchanged.
        // A MODE TRANSITION is a different event and clears unconditionally —
        // see `clearParcelas`.
        return acumular ? prev : { ...IDLE, multiSelect: prev.multiSelect, capHits: prev.capHits };
      }

      if (!acumular) {
        // Plain click: fresh single selection. `multiSelect` survives so the
        // mobile toggle is not a one-shot, and the polygon/canal ficha is
        // superseded exactly as before.
        return {
          ...IDLE,
          multiSelect: prev.multiSelect,
          capHits: prev.capHits,
          parcela,
          parcelas: [parcela.nomenclatura],
          parcelasResueltas: { [parcela.nomenclatura]: parcela },
        };
      }

      // `parcelas` is authoritative for the selection (a plain click already
      // leaves its one entry there), so accumulating is a pure toggle over it —
      // there is no second source of truth to reconcile.
      const { parcelas, capped } = toggleParcela(prev.parcelas, parcela.nomenclatura);
      const parcelasResueltas = podarResueltas(
        { ...prev.parcelasResueltas, [parcela.nomenclatura]: parcela },
        parcelas
      );
      return {
        ...prev,
        // Closing the draw SESSION is part of superseding the polygon, exactly
        // as in the plain-click branch above. Dropping `poligono` while leaving
        // `drawing: true` kept `DrawControl` mounted, so MapboxDraw went on
        // rendering a shape that no React state backed any more — an orphan the
        // user could only clear by re-entering draw mode. Unmounting the control
        // wipes its artifacts (`removeMapboxDrawArtifacts`).
        drawing: false,
        tracing: false,
        poligono: null,
        canal: null,
        parcelas,
        parcelasResueltas,
        capHits: capped ? prev.capHits + 1 : prev.capHits,
        // Identity props are only shown for a single-parcel selection. Looked
        // up by NOMENCLATURA rather than taken from the clicked parcel: when a
        // ctrl-click deselects B out of [A, B], the survivor is A and the
        // clicked parcel is the wrong one to describe it with (before this the
        // header simply vanished, leaving a single-parcel ficha with no
        // nomenclatura, account or BPA badge).
        parcela: parcelas.length === 1 ? (parcelasResueltas[parcelas[0]] ?? null) : null,
      };
    });
  }, []);

  const setMultiSelect = useCallback((on: boolean) => {
    // The current selection is kept: turning the mode off is "stop accumulating",
    // not "discard what I picked". A plain click is the reset.
    setState((prev) => (prev.multiSelect === on ? prev : { ...prev, multiSelect: on }));
  }, []);

  const removeParcelas = useCallback((nomenclaturas: readonly string[]) => {
    const aQuitar = new Set(nomenclaturas);
    if (aQuitar.size === 0) return;
    setState((prev) => {
      const parcelas = prev.parcelas.filter((n) => !aQuitar.has(n));
      if (parcelas.length === prev.parcelas.length) return prev;
      const parcelasResueltas = podarResueltas(prev.parcelasResueltas, parcelas);
      return {
        ...prev,
        parcelas,
        parcelasResueltas,
        parcela: parcelas.length === 1 ? (parcelasResueltas[parcelas[0]] ?? null) : null,
      };
    });
  }, []);

  const clearParcelas = useCallback(() => {
    setState((prev) =>
      prev.parcelas.length === 0 && prev.parcela === null
        ? prev
        : { ...prev, parcela: null, parcelas: [], parcelasResueltas: {} }
    );
  }, []);

  // One notification per DROPPED click. Compared against the last value seen
  // rather than fired from the updater: React may invoke an updater twice (strict
  // mode) and a state reset takes the counter back to 0, so only a genuine
  // INCREASE is a new capped click.
  const capHitsVistos = useRef(state.capHits);
  useEffect(() => {
    const anterior = capHitsVistos.current;
    capHitsVistos.current = state.capHits;
    if (state.capHits > anterior) onParcelasCapReached?.();
  }, [state.capHits, onParcelasCapReached]);

  // ── request settling (T4 fix round) ───────────────────────────────────────
  // The selection the REQUEST is derived from. It trails `state.parcelas` by
  // `FICHA_PARCELAS_SETTLE_MS` while the selection is multi, and catches up
  // immediately for 0/1 parcels (a plain click must feel exactly as it did
  // before T4). Clearing + re-arming on every change is what collapses a burst
  // of ctrl-clicks into ONE analysis.
  const [parcelasEstables, setParcelasEstables] = useState<readonly string[]>(IDLE.parcelas);
  const parcelasSeleccionadas = state.parcelas;
  useEffect(() => {
    if (parcelasSeleccionadas.length < FICHA_PARCELAS_MIN) {
      setParcelasEstables(parcelasSeleccionadas);
      return;
    }
    const id = setTimeout(
      () => setParcelasEstables(parcelasSeleccionadas),
      FICHA_PARCELAS_SETTLE_MS
    );
    return () => clearTimeout(id);
  }, [parcelasSeleccionadas]);

  // While a multi selection settles, the PREVIOUS settled set still drives the
  // request — so the panel keeps showing the analysis it already has instead of
  // blanking out, and no request is issued for an intermediate selection.
  const parcelasAnalizadas =
    parcelasSeleccionadas.length >= FICHA_PARCELAS_MIN ? parcelasEstables : parcelasSeleccionadas;

  // Keyed on `tracing`, NOT on `drawing`: see the field docs. A finished polygon
  // leaves the draw SESSION open (control mounted, toolbar lit) while the map
  // goes back to answering clicks.
  const interactionMode: MapInteractionMode = state.tracing
    ? 'ficha-dibujo'
    : state.canalMode
      ? 'ficha-canal'
      : measurementMode;

  const request: FichaRequest | null = state.poligono
    ? // `DrawnPolygon` ({type:'Polygon', coordinates}) IS a valid GeoJSON geometry;
      // the request type is the looser `Record<string, unknown>`, hence the cast.
      {
        tipo: 'poligono',
        geometry: state.poligono as unknown as Record<string, unknown>,
      }
    : state.canal
      ? state.canal.analysisMode === 'cuenca'
        ? {
            tipo: 'canal_cuenca',
            canal_ref: state.canal.canalRef,
            // v1 computes catchments against the NATURAL flow_dir (the burned/
            // relevado layer was pruned); the precomputed rows are variante=natural.
            variante: 'natural',
          }
        : {
            tipo: 'canal_buffer',
            canal_ref: state.canal.canalRef,
            buffer_m: state.canal.bufferM,
          }
      : parcelasAnalizadas.length >= FICHA_PARCELAS_MIN
        ? // The union is built SERVER-SIDE from these nomenclaturas: the tile
          // geometries the clicks resolved are simplified per zoom and clipped at
          // tile boundaries, so they are not something to union client-side.
          { tipo: 'parcelas', nomenclaturas: [...parcelasAnalizadas] }
        : parcelasAnalizadas.length === 1
          ? { tipo: 'parcela', nomenclatura: parcelasAnalizadas[0] }
          : null;

  const tipo: FichaTipo = state.poligono
    ? 'poligono'
    : state.canal
      ? state.canal.analysisMode === 'cuenca'
        ? 'canal_cuenca'
        : 'canal_buffer'
      : parcelasAnalizadas.length >= FICHA_PARCELAS_MIN
        ? 'parcelas'
        : 'parcela';

  // Identity + the BPA join are SINGLE-parcel facts. A union has no account and
  // no nomenclatura of its own, and showing the last-clicked parcel's account
  // next to N parcels' hectares would be a straightforward lie. Derived from the
  // ANALYZED set so the header always describes the numbers currently on screen,
  // including while a growing selection is still settling.
  const parcelaUnica =
    parcelasAnalizadas.length === 1
      ? (state.parcelasResueltas[parcelasAnalizadas[0]] ?? null)
      : null;

  return {
    state,
    interactionMode,
    request,
    parcelasAnalizadas,
    tipo,
    nroCuenta: parcelaUnica?.nroCuenta ?? null,
    parcelaProps: parcelaUnica?.props ?? null,
    startDraw,
    stopDraw,
    completePolygon,
    deletePolygon,
    redrawPolygon,
    startCanal,
    stopCanal,
    resolveCanal,
    setBuffer,
    setCanalAnalysisMode,
    resolveParcela,
    setMultiSelect,
    removeParcelas,
    clearParcelas,
    clearFicha,
  };
}
