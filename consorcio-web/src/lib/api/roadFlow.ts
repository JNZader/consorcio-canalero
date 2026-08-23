/**
 * Road-flow crossings API client (flujo-caminos — Slice 4).
 *
 * Mirrors `gee-backend/app/domains/geo/intelligence/router.py::get_cruces_camino`
 * (`GET /api/v2/geo/intelligence/cruces-camino`), an operator-only route
 * (`require_admin_or_operator`). The payload is deliberately ONE object: the
 * ranked list and the map layer consume the same response, so the two surfaces
 * cannot disagree about a direction, a contributing area, a rank or a segment
 * identity (RFA-R2). Do not add a second fetch for the map.
 *
 * Nothing here carries a volume, a flow rate, a depth, a cuneta size or a
 * return period, because the backend publishes none: the capability derives a
 * DIRECTION and a RELATIVE ORDER, not a hydraulic magnitude.
 */

import type { Feature, FeatureCollection, Point } from 'geojson';

import { apiFetch } from './core';

/** The two crossing kinds. Only `flujo_natural` is ever ranked. */
export const ROAD_FLOW_KINDS = {
  FLUJO_NATURAL: 'flujo_natural',
  CANAL: 'canal',
} as const;

export type RoadFlowKind = (typeof ROAD_FLOW_KINDS)[keyof typeof ROAD_FLOW_KINDS];

/**
 * Orientation confidence, as stored by the three-band crossing predicate
 * (design D3). `baja` means the flow/road angle fell inside the D8 quantization
 * band — the point is still ranked and still shown; marking is not demotion.
 */
export const ROAD_FLOW_CONFIANZAS = {
  ALTA: 'alta',
  BAJA: 'baja',
} as const;

export type RoadFlowConfianza = (typeof ROAD_FLOW_CONFIANZAS)[keyof typeof ROAD_FLOW_CONFIANZAS];

/** Feature properties, verbatim from `cruces_camino_service.get_cruces_camino`. */
export interface RoadFlowCrossingProperties {
  readonly id: string;
  readonly tipo: RoadFlowKind;
  readonly tramo_ref: string;
  readonly canal_ref: string | null;
  readonly direccion_flujo_deg: number | null;
  readonly rumbo_camino_deg: number | null;
  readonly lado_cruce: string | null;
  readonly area_aporte_ha: number | null;
  /** NULL on every `canal` row (`ck_cruce_canal_sin_rank`). */
  readonly orden_ranking: number | null;
  readonly confianza: RoadFlowConfianza | null;
  /** The server-authored reason a row is low confidence. Never re-derived here. */
  readonly nota: string | null;
}

export type RoadFlowCrossingFeature = Feature<Point, RoadFlowCrossingProperties>;
export type RoadFlowCrossingCollection = FeatureCollection<Point, RoadFlowCrossingProperties>;

/** One reported exclusion: a candidate that did NOT become a crossing, with its reason. */
export interface RoadFlowExclusion {
  readonly motivo: string;
  readonly tramo_ref?: string;
  readonly [key: string]: unknown;
}

export interface RoadFlowCrossingsResponse {
  readonly area_id: string;
  /** ISO timestamp of the run. Always rendered — a rank without its age is unreadable. */
  readonly calculada_en: string | null;
  readonly desactualizado: boolean;
  /** M in the `N.º de M` label. NEVER the total row count (Law 7). */
  readonly total_flujo_natural: number;
  readonly total_canal: number;
  readonly features: RoadFlowCrossingCollection;
  readonly excluidos: readonly RoadFlowExclusion[];
  readonly parametros: Record<string, unknown>;
  readonly variante: string | null;
  readonly segmentos_parcialmente_cubiertos: number;
}

/**
 * Read the crossings of one area. Operator-only server side; a citizen session
 * gets a 403 that discloses nothing, surfaced by `apiFetch` as an Error.
 *
 * An area with no registered DEM footprint answers 404 naming the area — that
 * is a coverage STATE for the caller to render, not a generic failure.
 */
export async function fetchRoadFlowCrossings(
  areaId: string,
  signal?: AbortSignal
): Promise<RoadFlowCrossingsResponse> {
  const query = new URLSearchParams({ area_id: areaId });
  return apiFetch<RoadFlowCrossingsResponse>(`/geo/intelligence/cruces-camino?${query}`, {
    signal,
  });
}
