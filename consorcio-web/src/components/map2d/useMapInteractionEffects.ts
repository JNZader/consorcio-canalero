import type { Feature } from 'geojson';
import type maplibregl from 'maplibre-gl';
import { useEffect } from 'react';
import { SOURCE_IDS } from './map2dConfig';
import type { MapInteractionMode, MeasurementMode } from './measurement/useMeasurement';

/** A catastro parcel resolved from a click, for the ficha territorial request. */
export interface ParcelaResuelta {
  nomenclatura: string;
  nroCuenta: string | null;
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
   */
  onParcelaResolved?: (parcela: ParcelaResuelta | null) => void;
}

type FeatureWithLayer = Feature & { readonly layer?: { readonly id?: string } };

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
  const catastroLayerId = `${SOURCE_IDS.CATASTRO}-fill`;
  const feature = features.find((f) => f.layer?.id === catastroLayerId);
  if (!feature) return null;
  const props = (feature.properties as Record<string, unknown> | null) ?? {};
  const nomenclatura = readProp(props, 'nomenclatura', 'Nomenclatura');
  if (!nomenclatura) return null;
  return {
    nomenclatura,
    nroCuenta: readProp(props, 'nro_cuenta', 'Nro_Cuenta'),
  };
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
 * **Mode gate (A5.3, design §6.2):** in `'ficha-dibujo'` the `DrawControl` owns
 * every click (the user is drawing a polygon, not selecting a feature), so
 * NOTHING on the map is clickable for feature selection and the whitelist is
 * empty. All other modes get the full ordered list; the `'idle'` default
 * preserves the pre-existing behaviour exactly. Canal-only filtering for
 * `'ficha-canal'` lands in A6.
 */
export function buildClickableLayers(mode: MapInteractionMode = 'idle'): string[] {
  if (mode === 'ficha-dibujo') return [];
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
}: UseMapInteractionEffectsParams) {
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;

    // Mode-aware whitelist: empty in 'ficha-dibujo' (DrawControl owns clicks).
    const clickableLayers = buildClickableLayers(measurementMode);

    const handleClick = (event: maplibregl.MapMouseEvent) => {
      if (measurementMode !== 'idle') {
        setSelectedFeatures([]);
        onParcelaResolved?.(null);
        return;
      }

      const features = map.queryRenderedFeatures(event.point, {
        layers: clickableLayers.filter((id) => map.getLayer(id)),
      });

      // Phase 8 — surface ALL overlapping features. MapLibre preserves the
      // on-screen z-order (top-most first) which matches the user-intuitive
      // "most specific first" ordering we want in the panel.
      setSelectedFeatures(features as unknown as Feature[]);

      // A4 — a catastro click ADDITIONALLY fires the ficha (design §6.2). A
      // click that hit no parcel clears the current ficha so it does not linger
      // over an unrelated area.
      onParcelaResolved?.(resolveParcela(features as unknown as FeatureWithLayer[]));
    };

    map.on('click', handleClick);
    return () => {
      map.off('click', handleClick);
    };
  }, [mapReady, mapRef, measurementMode, setSelectedFeatures, onParcelaResolved]);
}
