/**
 * useRoadFlowWiring — everything the cruces-de-camino capability needs to exist
 * on the map, in ONE place (flujo-caminos, S4 wiring).
 *
 * ⚠️ THE LAYER TOGGLE IS THE WHOLE LIFECYCLE. ⚠️
 * Ticking `road_flow` in the layer selector enables the single fetch, feeds the
 * two circle layers from that response and opens the ranked panel; unticking it
 * stops all three. There is no second "open the cruces panel" control that
 * could get out of step with what the map is drawing.
 *
 * It lives in its own hook rather than inside `MapaMapLibre` because that
 * component sits EXACTLY on biome's `noExcessiveCognitiveComplexity` ceiling
 * (30, see its own header note): adding this block inline would trip the rule.
 * The container calls one hook and threads the result.
 *
 * OPERATOR-ONLY. Both routes behind this (`/geo/intelligence/cruces-camino`
 * and `/geo/relevamiento/*`) are `require_admin_or_operator` server-side, so
 * `showRoadFlow` gates the SELECTOR ENTRY on the session's role. Every other
 * entry in `buildVectorLayerItems` gates on data, which is unavailable here by
 * construction — the fetch only starts once the layer is on — and a citizen who
 * ticked the box would get a 403 and an empty panel.
 */

import type { FeatureCollection, Point } from 'geojson';
import type maplibregl from 'maplibre-gl';
import { type RefObject, useCallback, useMemo, useState } from 'react';

import { useAuth } from '../../hooks/useAuth';
import {
  useRegistrarRelevamiento,
  useRelevamientoCobertura,
  useTramoRelevamiento,
} from '../../hooks/useRelevamiento';
import {
  type UseRoadFlowCrossingsResult,
  useRoadFlowCrossings,
} from '../../hooks/useRoadFlowCrossings';
import type {
  CoberturaResponse,
  RelevamientoTramoCreate,
  TramoRelevamientoDetalle,
} from '../../lib/api/relevamiento';
import type { RoadFlowCrossingFeature } from '../../lib/api/roadFlow';
import { DEFAULT_ROAD_FLOW_AREA_ID } from './map2dConfig';
import { ROAD_FLOW_ALL_KINDS_VISIBLE, type RoadFlowKindVisibility } from './roadFlowLayers';
import { useRoadFlowInteraction } from './useRoadFlowInteraction';

interface GeoLayerAreaLike {
  readonly area_id: string | null;
}

interface UseRoadFlowWiringParams {
  readonly mapRef: RefObject<maplibregl.Map | null>;
  readonly mapReady: boolean;
  /** `vectorVisibility.road_flow` — the single lifecycle switch. */
  readonly active: boolean;
  /** The DEM catalogue the map already loads; its `area_id` wins over the default. */
  readonly geoLayers: readonly GeoLayerAreaLike[];
  /** Turns the layer OFF. Closing the panel and hiding the layer are one act. */
  readonly onDeactivate: () => void;
}

export interface RoadFlowWiring {
  /** Whether the layer is OFFERED in the selector at all (role gate). */
  readonly showRoadFlow: boolean;
  readonly roadFlowActive: boolean;
  readonly crossings: UseRoadFlowCrossingsResult;
  readonly cobertura: CoberturaResponse | undefined;
  readonly kinds: RoadFlowKindVisibility;
  readonly setKinds: (kinds: RoadFlowKindVisibility) => void;
  /** The `features` member of the SAME response the list renders (RFA-R2). */
  readonly mapCollection: FeatureCollection<Point> | null;
  readonly totalFlujoNatural: number;
  readonly onSelectCrossing: (feature: RoadFlowCrossingFeature) => void;
  readonly onSurveyTramo: (tramoRef: string) => void;
  readonly onClose: () => void;
  /** The segment the operator asked for. THE SHEET'S MOUNT CONDITION. */
  readonly tramoRef: string | null;
  readonly tramoDetalle: TramoRelevamientoDetalle | null;
  readonly tramoLoading: boolean;
  readonly tramoError: Error | null;
  /** Re-issues the segment read after a failure. */
  readonly onRetryTramoSurvey: () => void;
  readonly onSubmitTramoSurvey: (payload: RelevamientoTramoCreate) => Promise<unknown>;
  readonly onCloseTramoSurvey: () => void;
}

export function useRoadFlowWiring({
  mapRef,
  mapReady,
  active,
  geoLayers,
  onDeactivate,
}: UseRoadFlowWiringParams): RoadFlowWiring {
  const { isStaff } = useAuth();

  // Prefer the area the DEM catalogue actually reports over the recorded
  // rollout default — `area_id` is a query parameter on purpose (task 2.2).
  const areaId = useMemo(
    () => geoLayers.find((layer) => layer.area_id)?.area_id ?? DEFAULT_ROAD_FLOW_AREA_ID,
    [geoLayers]
  );

  const crossings = useRoadFlowCrossings(active ? areaId : null);
  const { data: cobertura } = useRelevamientoCobertura(areaId, active);
  const [kinds, setKinds] = useState<RoadFlowKindVisibility>(ROAD_FLOW_ALL_KINDS_VISIBLE);

  // The selected segment IS the survey sheet's mount condition — the REF, not
  // the answer to the read. A sheet that mounted on the data left the "Relevar"
  // button doing nothing at all whenever the GET failed.
  const [tramoRef, setTramoRef] = useState<string | null>(null);
  const {
    data: tramoDetalle,
    isLoading: tramoLoading,
    error: tramoError,
    refetch: refetchTramo,
  } = useTramoRelevamiento(tramoRef);
  const registrar = useRegistrarRelevamiento();

  /**
   * Asking for a segment. Asking for the one ALREADY selected re-issues the
   * read instead of writing the same state and changing nothing: with
   * `retry: false` a failed read stays failed, so without this the second tap
   * on the same row would be as silent as the first one was.
   */
  const onSurveyTramo = useCallback(
    (ref: string) => {
      if (ref === tramoRef) {
        refetchTramo();
        return;
      }
      setTramoRef(ref);
    },
    [refetchTramo, tramoRef]
  );

  const { flyToCrossing } = useRoadFlowInteraction({
    mapRef,
    mapReady,
    active,
    onSelectTramo: onSurveyTramo,
  });

  const onCloseTramoSurvey = useCallback(() => setTramoRef(null), []);

  const onSubmitTramoSurvey = useCallback(
    async (payload: RelevamientoTramoCreate) => {
      // Only a SUCCESSFUL save closes the sheet: a rejection propagates to
      // `TramoSurveySheet`, which keeps the three answers on screen. There is no
      // offline queue (design D6), so swallowing it would discard fieldwork.
      const saved = await registrar(payload);
      setTramoRef(null);
      return saved;
    },
    [registrar]
  );

  const onClose = useCallback(() => {
    setTramoRef(null);
    onDeactivate();
  }, [onDeactivate]);

  return {
    showRoadFlow: isStaff,
    roadFlowActive: active,
    crossings,
    cobertura,
    kinds,
    setKinds,
    // One cast, at the ONE boundary where a typed feature collection meets
    // MapLibre's structurally-typed one: `RoadFlowCrossingProperties` is an
    // interface, so it does not satisfy GeoJSON's index-signature properties
    // type even though every field is compatible.
    mapCollection: (crossings.data?.features as unknown as FeatureCollection<Point>) ?? null,
    totalFlujoNatural: crossings.data?.total_flujo_natural ?? 0,
    onSelectCrossing: flyToCrossing,
    onSurveyTramo,
    onClose,
    tramoRef,
    tramoDetalle: tramoDetalle ?? null,
    tramoLoading,
    tramoError,
    onRetryTramoSurvey: refetchTramo,
    onSubmitTramoSurvey,
    onCloseTramoSurvey,
  };
}
