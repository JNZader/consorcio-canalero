import type { Feature } from 'geojson';
import type maplibregl from 'maplibre-gl';
import { useEffect } from 'react';
import { SOURCE_IDS } from './map2dConfig';
import type { MeasurementMode } from './measurement/useMeasurement';

interface UseMapInteractionEffectsParams {
  mapRef: React.RefObject<maplibregl.Map | null>;
  mapReady: boolean;
  markingMode: boolean;
  measurementMode: MeasurementMode;
  setNewPoint: (value: { lat: number; lng: number } | null) => void;
  /**
   * Receives the FULL list of overlapping features MapLibre returned at the
   * click point (top-most first, per z-order). Empty array clears the panel.
   * Phase 8 — previously this was `Feature | null`; we now surface all of
   * them so InfoPanel can render one section per layer.
   */
  setSelectedFeatures: (value: Feature[]) => void;
  showSuggestedZonesPanel: boolean;
  setSelectedDraftBasinId: (value: string | null) => void;
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
 */
export function buildClickableLayers(): string[] {
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
    `${SOURCE_IDS.SUGGESTED_ZONES}-fill`,
    `${SOURCE_IDS.MARTIN_PUNTOS}-circle`,
  ];
}

export function useMapInteractionEffects({
  mapRef,
  mapReady,
  markingMode,
  measurementMode,
  setNewPoint,
  setSelectedFeatures,
  showSuggestedZonesPanel,
  setSelectedDraftBasinId,
}: UseMapInteractionEffectsParams) {
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;

    const clickableLayers = buildClickableLayers();

    const handleClick = (event: maplibregl.MapMouseEvent) => {
      if (markingMode) {
        setNewPoint({ lat: event.lngLat.lat, lng: event.lngLat.lng });
        return;
      }

      if (measurementMode !== 'idle') {
        setSelectedFeatures([]);
        return;
      }

      const features = map.queryRenderedFeatures(event.point, {
        layers: clickableLayers.filter((id) => map.getLayer(id)),
      });

      // Phase 8 — surface ALL overlapping features. MapLibre preserves the
      // on-screen z-order (top-most first) which matches the user-intuitive
      // "most specific first" ordering we want in the panel.
      setSelectedFeatures(features as unknown as Feature[]);
    };

    map.on('click', handleClick);
    return () => {
      map.off('click', handleClick);
    };
  }, [mapReady, mapRef, markingMode, measurementMode, setNewPoint, setSelectedFeatures]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !showSuggestedZonesPanel) return;

    const handleBasinClick = (event: maplibregl.MapMouseEvent) => {
      if (measurementMode !== 'idle') return;

      const features = map.queryRenderedFeatures(event.point, {
        layers: [`${SOURCE_IDS.BASINS}-fill`, `${SOURCE_IDS.SUGGESTED_ZONES}-fill`].filter((id) =>
          map.getLayer(id)
        ),
      });
      if (features.length > 0 && features[0]) {
        const basinId = features[0].properties?.id;
        if (typeof basinId === 'string') {
          setSelectedDraftBasinId(basinId);
        }
      }
    };

    map.on('click', handleBasinClick);
    return () => {
      map.off('click', handleBasinClick);
    };
  }, [mapReady, mapRef, measurementMode, setSelectedDraftBasinId, showSuggestedZonesPanel]);
}
