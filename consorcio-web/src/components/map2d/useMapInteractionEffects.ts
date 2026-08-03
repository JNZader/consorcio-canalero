import type { Feature } from 'geojson';
import type maplibregl from 'maplibre-gl';
import { useEffect } from 'react';
import { SOURCE_IDS } from './map2dConfig';
import type { MapInteractionMode, MeasurementMode } from './measurement/useMeasurement';

/**
 * Whitelisted PUBLIC identity fields of a clicked catastro parcel, surfaced as a
 * header in the ficha panel (display-only — the ficha REQUEST still uses only
 * `nomenclatura`). These are the same fields the old InfoPanel catastro card
 * dumped; they are already public in the catastro tile whitelist (PR #83).
 */
export interface ParcelaDisplayProps {
  readonly nomenclatura: string | null;
  readonly nroCuenta: string | null;
  readonly desigOficial: string | null;
  readonly superficieHa: string | null;
  readonly departamento: string | null;
  readonly pedania: string | null;
  readonly tipoParcela: string | null;
}

/** A catastro parcel resolved from a click, for the ficha territorial request. */
export interface ParcelaResuelta {
  nomenclatura: string;
  nroCuenta: string | null;
  /** Display-only identity props, rendered as the ficha header (see bug-3 fix). */
  readonly props: ParcelaDisplayProps;
}

interface UseMapInteractionEffectsParams {
  mapRef: React.RefObject<maplibregl.Map | null>;
  mapReady: boolean;
  measurementMode: MeasurementMode;
  /**
   * Receives the FULL list of overlapping features MapLibre returned at the
   * click point (top-most first, per z-order). Empty array clears the panel.
   * Phase 8 — previously this was `Feature | null`; we now surface all of
   * them so InfoPanel can render one section per layer.
   */
  setSelectedFeatures: (value: Feature[]) => void;
  /**
   * Ficha territorial (A4). In the default `'idle'` mode a click that resolves
   * a `parcelas_catastro` feature ADDITIONALLY reports the parcel here so the
   * container can fetch its ficha. This is NOT a mode and does NOT change the
   * existing click routing / Pilar Verde precedence (design §6.2, JD-A-013):
   * the ficha fires alongside the InfoPanel, for whichever catastro feature the
   * click hit, regardless of z-order. `null` clears the current ficha (click on
   * empty space, or a non-idle interaction mode). Optional — callers that do
   * not want the ficha (3D viewer) simply omit it.
   *
   * `additive` (T4) reports whether the click carried the ctrl/⌘ modifier, i.e.
   * whether the user asked to ACCUMULATE this parcel into a multi-parcel
   * selection instead of replacing it. This hook only READS the modifier — the
   * selection itself, and the OR with the touch "selección múltiple" toggle,
   * belong to the coordinator, which is why no mode is threaded in here.
   */
  onParcelaResolved?: (parcela: ParcelaResuelta | null, additive?: boolean) => void;
  /**
   * MODE-TRANSITION clear (T4 fix round). Called when a click arrives while a
   * MEASUREMENT is active, i.e. when the ficha's selection must be discarded
   * because the user switched to another tool (design §6.5 — "switching modes
   * discards the previous result").
   *
   * It exists because `onParcelaResolved(null)` is NOT the same event: with the
   * sticky "selección múltiple" mode on, a null means "your tap missed" and the
   * coordinator deliberately KEEPS the selection. That made the mode transition a
   * no-op and left a stale multi-parcel ficha on screen through a measurement.
   * Optional — callers that omit it keep the previous behaviour.
   */
  onClearParcelas?: () => void;
  /**
   * Ficha territorial canal analysis (A6 + A7). In `'ficha-canal'` mode a click is
   * resolved against the CURATED relevados/propuestos line layers ONLY (never
   * parcels), and the clicked feature's string `properties.id` (+ `nombre`) is
   * reported here so the container can fire a `tipo=canal_buffer` /
   * `tipo=canal_cuenca` request against `canal_consorcio`. `null` when the click
   * missed a canal. Optional — callers that do not offer the canal mode omit it
   * (design §6.3, JDB-013).
   */
  onCanalResolved?: (canal: CanalResuelta | null) => void;
}

/** A curated consorcio canal resolved from a click in `'ficha-canal'` mode. */
export interface CanalResuelta {
  /** The `canal_consorcio` string id (from the GeoJSON `properties.id`). */
  readonly ref: string;
  /** Display name for the analysis control (`properties.nombre`, falls back to the ref). */
  readonly nombre: string;
}

type FeatureWithLayer = Feature & { readonly layer?: { readonly id?: string } };

/** The clickable catastro fill layer id — the only source a parcel resolves from. */
const CATASTRO_LAYER_ID = `${SOURCE_IDS.CATASTRO}-fill`;

/** Tolerant read of a property across the casings the catastro sources use. */
function readProp(props: Record<string, unknown>, ...keys: string[]): string | null {
  for (const key of keys) {
    const value = props[key];
    if (value !== null && value !== undefined) {
      const asStr = String(value).trim();
      if (asStr.length > 0) return asStr;
    }
  }
  return null;
}

/**
 * Find the clicked `parcelas_catastro` parcel among the overlapping features,
 * regardless of z-order, and pull its nomenclatura (+ nro_cuenta for the BPA
 * join). Returns `null` when the click did not hit a catastro parcel.
 */
function resolveParcela(features: FeatureWithLayer[]): ParcelaResuelta | null {
  const feature = features.find((f) => f.layer?.id === CATASTRO_LAYER_ID);
  if (!feature) return null;
  const props = (feature.properties as Record<string, unknown> | null) ?? {};
  const nomenclatura = readProp(props, 'nomenclatura', 'Nomenclatura');
  if (!nomenclatura) return null;
  const nroCuenta = readProp(props, 'nro_cuenta', 'Nro_Cuenta');
  return {
    nomenclatura,
    nroCuenta,
    // Display-only identity header (bug-3 combine). All fields are public in the
    // catastro tile whitelist; missing ones stay null and are hidden by the panel.
    props: {
      nomenclatura,
      nroCuenta,
      desigOficial: readProp(props, 'desig_oficial', 'Desig_Oficial'),
      superficieHa: readProp(props, 'superficie_ha', 'Superficie_Ha'),
      departamento: readProp(props, 'departamento', 'Departamento'),
      pedania: readProp(props, 'pedania', 'Pedania'),
      tipoParcela: readProp(props, 'tipo_parcela', 'Tipo_Parcela'),
    },
  };
}

/** The two curated canal line layers that are clickable in `'ficha-canal'` mode. */
const CANAL_FICHA_LAYER_IDS = [
  `${SOURCE_IDS.CANALES_RELEVADOS}-line`,
  `${SOURCE_IDS.CANALES_PROPUESTOS}-line`,
];

/**
 * Read the curated `canal_consorcio` string id (+ nombre) off a clicked
 * relevados/propuestos feature.
 *
 * These layers are rendered from `capas/canales/{relevados,propuestas}.geojson`,
 * whose features carry `properties.id` = the `canal_consorcio` string id (e.g.
 * `canal-ne-sin-intervencion`) and `properties.nombre`. We prefer a feature on the
 * two curated canal layers; the top-most hit wins on overlap. Returns `null` when
 * the click did not land on a curated canal (the caller then clears the selection).
 */
export function resolveCanalRef(features: FeatureWithLayer[]): CanalResuelta | null {
  const feature =
    features.find((f) => f.layer?.id && CANAL_FICHA_LAYER_IDS.includes(f.layer.id)) ?? features[0];
  if (!feature) return null;
  const props = (feature.properties as Record<string, unknown> | null) ?? {};
  const rawId = props.id;
  const ref = typeof rawId === 'string' ? rawId.trim() : '';
  if (!ref) return null;
  const rawNombre = props.nombre;
  const nombre = typeof rawNombre === 'string' && rawNombre.trim() ? rawNombre.trim() : ref;
  return { ref, nombre };
}

/**
 * Ordered list of layer IDs passed to `queryRenderedFeatures`.
 *
 * **Z-order invariant** (Phase 2, spec decision #2):
 *   - Pilar Verde BPA-fill MUST appear BEFORE `catastro-fill` so on
 *     overlapping clicks MapLibre returns the BPA feature at index 0 —
 *     InfoPanel then renders the BPA-aware card, not the generic catastro
 *     dump.
 *   - Agro aceptada/presentada are clickable too (future Phase 3 BPA-lite
 *     branch can pick them up).
 *   - Agro zonas and porcentaje_forestacion are context-only layers — they
 *     are intentionally NOT clickable so they don't hijack parcel clicks.
 *
 * Exported so tests can assert the ordering without running the hook.
 *
 * **Mode gate (A5.3/A6, design §6.2/§6.3):** in `'ficha-dibujo'` the `DrawControl`
 * owns every click (the user is drawing a polygon, not selecting a feature), so
 * NOTHING on the map is clickable for feature selection and the whitelist is
 * empty. In `'ficha-canal'` the ONLY clickable layers are the two CURATED canal
 * line layers (relevados + propuestos) — parcels/BPA/soil are excluded so a canal
 * click can only ever resolve a curated `canal_ref`, never a parcel (JDB-013).
 * All other modes get the full ordered list; the `'idle'` default preserves the
 * pre-existing behaviour exactly (its ordering is pinned by tests, so the two
 * ficha modes are handled as early returns and never perturb it).
 */
export function buildClickableLayers(mode: MapInteractionMode = 'idle'): string[] {
  if (mode === 'ficha-dibujo') return [];
  if (mode === 'ficha-canal') return [...CANAL_FICHA_LAYER_IDS];
  return [
    // ── Pilar Verde (top-most — wins click precedence on overlap) ──
    `${SOURCE_IDS.PILAR_VERDE_BPA_HISTORICO}-fill`,
    `${SOURCE_IDS.PILAR_VERDE_AGRO_ACEPTADA}-fill`,
    `${SOURCE_IDS.PILAR_VERDE_AGRO_PRESENTADA}-fill`,
    // ── Waterways + Canales (Phase 2 Pilar Azul) ──
    // Existing waterways come FIRST so `rio_tercero` + arroyos still surface
    // on their own overlay clicks. Canales line layers are inserted BEFORE
    // catastro-fill — overlapping clicks on a river that has a canal
    // crossing resolve to the canal (user feedback: canales are the more
    // specific context for hydraulic decisions).
    `${SOURCE_IDS.WATERWAYS}-rio-tercero-line`,
    `${SOURCE_IDS.WATERWAYS}-arroyo-algodon-line`,
    `${SOURCE_IDS.WATERWAYS}-canal-desviador-line`,
    `${SOURCE_IDS.WATERWAYS}-canal-litin-line`,
    `${SOURCE_IDS.WATERWAYS}-arroyo-mojarras-line`,
    `${SOURCE_IDS.CANALES_RELEVADOS}-line`,
    `${SOURCE_IDS.CANALES_PROPUESTOS}-line`,
    // ── Pilar Azul (Escuelas rurales) ──
    // Symbol layer sits BETWEEN canales_propuestos-line (index 9) and
    // soil-fill (index 11) per design `sdd/escuelas-rurales/design` §6.5.
    // Canales WIN a crossing overlap (line-over-point, same rationale as
    // canal-over-catastro). Schools WIN over soil/catastro/roads so the
    // EscuelaCard opens instead of the generic parcel dump.
    `${SOURCE_IDS.ESCUELAS}-symbol`,
    `${SOURCE_IDS.SOIL}-fill`,
    `${SOURCE_IDS.CATASTRO}-fill`,
    `${SOURCE_IDS.ROADS}-line`,
    `${SOURCE_IDS.BASINS}-fill`,
    `${SOURCE_IDS.APPROVED_ZONES}-fill`,
    `${SOURCE_IDS.MARTIN_PUNTOS}-circle`,
  ];
}

export function useMapInteractionEffects({
  mapRef,
  mapReady,
  measurementMode,
  setSelectedFeatures,
  onParcelaResolved,
  onClearParcelas,
  onCanalResolved,
}: UseMapInteractionEffectsParams) {
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;

    // Mode-aware whitelist: empty in 'ficha-dibujo' (DrawControl owns clicks),
    // canal-only in 'ficha-canal', the full ordered list otherwise.
    const clickableLayers = buildClickableLayers(measurementMode);

    const handleClick = (event: maplibregl.MapMouseEvent) => {
      // A6/A7 — canal mode: resolve a curated `canal_ref` off the relevados /
      // propuestos layers ONLY. The InfoPanel/parcel path is bypassed entirely so
      // a canal click can never open a parcel card or fire a `tipo=parcela` ficha
      // (design §6.3).
      if (measurementMode === 'ficha-canal') {
        const canalFeatures = map.queryRenderedFeatures(event.point, {
          layers: clickableLayers.filter((id) => map.getLayer(id)),
        });
        setSelectedFeatures([]);
        onParcelaResolved?.(null);
        onCanalResolved?.(resolveCanalRef(canalFeatures as unknown as FeatureWithLayer[]));
        return;
      }

      if (measurementMode !== 'idle') {
        setSelectedFeatures([]);
        // MODE TRANSITION, not a miss: the selection goes even when the sticky
        // touch mode is on (which is exactly the case `onParcelaResolved(null)`
        // keeps). `onParcelaResolved(null)` stays for callers that never wired
        // the explicit clear.
        onParcelaResolved?.(null);
        onClearParcelas?.();
        onCanalResolved?.(null);
        return;
      }

      const features = map.queryRenderedFeatures(event.point, {
        layers: clickableLayers.filter((id) => map.getLayer(id)),
      });

      const featuresWithLayer = features as unknown as FeatureWithLayer[];
      const parcela = resolveParcela(featuresWithLayer);

      // De-duplication (bug-3 combine): when a catastro parcel resolves, its
      // identity is already rendered by the ficha's header, so the redundant
      // catastro CARD is dropped from the InfoPanel — but ONLY that card. Every
      // other feature under the same click (canal, escuela, BPA, suelo, camino)
      // still opens its InfoPanel card; suppressing them wholesale made those
      // cards unreachable on any rural click now that catastro defaults to ON.
      // The two panels are laid out so they coexist (InfoPanel top-right, ficha
      // bottom-right, both capped — see `map.module.css` `.infoPanelCompact` /
      // `.fichaPanelCompact`), which is what the blanket suppression was really
      // trying to solve.
      const featuresForInfoPanel: FeatureWithLayer[] = parcela
        ? featuresWithLayer.filter((f) => f.layer?.id !== CATASTRO_LAYER_ID)
        : featuresWithLayer;

      // Phase 8 — surface ALL overlapping features. MapLibre preserves the
      // on-screen z-order (top-most first) which matches the user-intuitive
      // "most specific first" ordering we want in the panel.
      setSelectedFeatures(featuresForInfoPanel as unknown as Feature[]);

      // A4 — a catastro click ADDITIONALLY fires the ficha (design §6.2). A
      // click that hit no parcel clears the current ficha so it does not linger
      // over an unrelated area.
      //
      // T4 — ctrl (Windows/Linux) or ⌘ (macOS) means ACCUMULATE. `originalEvent`
      // is optional in the MapLibre typings and absent in synthesized events, so
      // a missing modifier reads as a plain click — the pre-T4 behaviour.
      const original = event.originalEvent as MouseEvent | undefined;
      const additive = !!original && (original.ctrlKey || original.metaKey);
      onParcelaResolved?.(parcela, additive);
    };

    map.on('click', handleClick);
    return () => {
      map.off('click', handleClick);
    };
  }, [
    mapReady,
    mapRef,
    measurementMode,
    setSelectedFeatures,
    onParcelaResolved,
    onClearParcelas,
    onCanalResolved,
  ]);
}
