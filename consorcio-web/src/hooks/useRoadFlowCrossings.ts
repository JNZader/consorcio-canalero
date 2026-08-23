/**
 * useRoadFlowCrossings — ONE fetch, ONE response object (flujo-caminos, D6).
 *
 * ⚠️ THE POINT OF THIS HOOK ⚠️
 * RFA-R2 requires that a crossing selected on the map and the same crossing read
 * in the list "do not disagree about any of those four values". That is
 * guaranteed HERE, structurally: there is exactly one request, and both the
 * ranked list and `ensureGeoJsonSource(map, SOURCE_IDS.ROAD_FLOW, …)` read the
 * SAME `RoadFlowCrossingsResponse` object.
 *
 * Adding a second fetch for the map — even "just for the geometry" — reopens
 * the disagreement this design closed: two requests can straddle a
 * recalculation, and then the list ranks one run while the map draws another.
 * Consume `data.features` for the map. Do not fetch again.
 *
 * There is no `keepPreviousData`: switching area must never show the previous
 * area's crossings under the new area's name.
 */

import { useQuery } from '@tanstack/react-query';

import { type RoadFlowCrossingsResponse, fetchRoadFlowCrossings } from '../lib/api/roadFlow';

export interface UseRoadFlowCrossingsResult {
  readonly data: RoadFlowCrossingsResponse | undefined;
  readonly isLoading: boolean;
  readonly isError: boolean;
  readonly error: Error | null;
  /**
   * True when the area has no registered DEM footprint (the backend's named
   * 404). It is a COVERAGE STATE the panel labels, not a generic failure — an
   * operator who is told "no calculado para esta área" knows what to do next,
   * and one who is shown "Error 404" does not.
   */
  readonly sinCobertura: boolean;
}

/** A 404 from this route means "no DEM footprint for that area", nothing else. */
function isSinCobertura(error: Error | null): boolean {
  return error !== null && /\b404\b|no encontrad|not found/i.test(error.message);
}

export function useRoadFlowCrossings(areaId: string | null): UseRoadFlowCrossingsResult {
  const query = useQuery({
    queryKey: areaId
      ? (['road-flow-crossings', areaId] as const)
      : (['road-flow-crossings', 'idle'] as const),
    queryFn: ({ signal }) => fetchRoadFlowCrossings(areaId as string, signal),
    enabled: areaId !== null,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  const error = (query.error as Error | null) ?? null;
  return {
    data: query.data,
    isLoading: query.isLoading && query.fetchStatus !== 'idle',
    isError: query.isError,
    error,
    sinCobertura: query.isError && isSinCobertura(error),
  };
}
