import { apiFetch, API_PREFIX, API_URL, getAuthToken, GEE_TIMEOUT } from './core';

export type RoutingProfile = 'balanceado' | 'hidraulico' | 'evitar_propiedad';
export type RoutingMode = 'network' | 'raster';
export type AutoAnalysisScopeType = 'cuenca' | 'subcuenca' | 'consorcio' | 'punto';

export interface RoutingVertexRef {
  id: number | string;
  geometry?: unknown;
  distance_m?: number;
}

export interface CorridorFeatureCollection {
  type: 'FeatureCollection';
  features: Array<Record<string, unknown>>;
}

export interface CorridorFeature {
  type: 'Feature';
  geometry: Record<string, unknown> | null;
  properties: Record<string, unknown>;
}

export interface CorridorAlternative {
  rank: number;
  total_distance_m: number;
  edges: number;
  edge_ids: number[];
  geojson: CorridorFeatureCollection;
}

export interface CorridorRoutingResponse {
  source: RoutingVertexRef;
  target: RoutingVertexRef;
  summary: {
    mode?: RoutingMode;
    profile: RoutingProfile;
    total_distance_m: number;
    edges: number;
    corridor_width_m: number;
    penalty_factor?: number;
    edge_ids?: number[];
    cost_breakdown?: {
      profile: RoutingProfile;
      edge_count_with_profile_factor?: number;
      avg_profile_factor?: number;
      max_profile_factor?: number;
      min_profile_factor?: number;
      parcel_intersections?: number;
      near_parcels?: number;
      avg_hydric_index?: number | null;
      hydraulic_edge_count?: number;
      profile_edge_count?: number;
      weights?: Record<string, number>;
      mode?: RoutingMode;
      property_features?: number;
      hydric_features?: number;
      landcover_features?: number;
      existing_network_overlap_m?: number;
      overlap_ratio?: number;
    };
  };
  centerline: CorridorFeatureCollection;
  corridor: CorridorFeature | null;
  alternatives: CorridorAlternative[];
}

export interface CorridorRoutingRequest {
  from_lon: number;
  from_lat: number;
  to_lon: number;
  to_lat: number;
  mode?: RoutingMode;
  area_id?: string;
  profile?: RoutingProfile;
  corridor_width_m?: number;
  alternative_count?: number;
  penalty_factor?: number;
  weight_slope?: number;
  weight_hydric?: number;
  weight_property?: number;
  weight_landcover?: number;
}

export interface CorridorScenarioApprovalEvent {
  id: string;
  scenario_id: string;
  action: 'approved' | 'unapproved' | string;
  note?: string | null;
  acted_by_id?: string | null;
  acted_at: string;
}

export interface CorridorScenario {
  id: string;
  name: string;
  profile: RoutingProfile;
  version?: number;
  previous_version_id?: string | null;
  request_payload: CorridorRoutingRequest;
  result_payload: CorridorRoutingResponse;
  notes?: string | null;
  approval_note?: string | null;
  is_approved?: boolean;
  is_favorite?: boolean;
  approved_at?: string | null;
  approved_by_id?: string | null;
  created_by_id?: string | null;
  created_at: string;
  updated_at?: string;
  approval_history?: CorridorScenarioApprovalEvent[];
}

export interface CorridorScenarioListItem {
  id: string;
  name: string;
  profile: RoutingProfile;
  version?: number;
  notes?: string | null;
  approval_note?: string | null;
  is_approved?: boolean;
  is_favorite?: boolean;
  approved_at?: string | null;
  created_at: string;
}

export interface CorridorScenarioSaveRequest {
  name: string;
  profile: RoutingProfile;
  request_payload: CorridorRoutingRequest;
  result_payload: CorridorRoutingResponse;
  notes?: string;
  previous_version_id?: string;
  is_favorite?: boolean;
}

export interface AutoCorridorAnalysisRequest {
  scope_type: AutoAnalysisScopeType;
  scope_id?: string | null;
  point_lon?: number | null;
  point_lat?: number | null;
  mode?: RoutingMode;
  profile?: RoutingProfile;
  max_candidates?: number;
  corridor_width_m?: number;
  alternative_count?: number;
  penalty_factor?: number;
  weight_slope?: number;
  weight_hydric?: number;
  weight_property?: number;
  weight_landcover?: number;
  include_unroutable?: boolean;
}

export interface AutoCorridorAnalysisCandidate {
  candidate_id: string;
  candidate_type: string;
  source_zone_id: string;
  source_zone_name: string;
  target_zone_id: string;
  target_zone_name: string;
  from_lon: number;
  from_lat: number;
  to_lon: number;
  to_lat: number;
  zone_pair_distance_deg: number;
  priority_score: number;
  reason: string;
  status: 'routed' | 'unroutable';
  score: number;
  rank?: number;
  ranking_breakdown: {
    status: 'routed' | 'unroutable';
    priority_score: number;
    distance_score?: number;
    profile_score?: number;
    hydric_score?: number;
    route_distance_m?: number;
    avg_profile_factor?: number;
    avg_hydric_index?: number | null;
    parcel_intersections?: number;
    near_parcels?: number;
    explanation: string;
  };
  routing_result: CorridorRoutingResponse;
}

export interface AutoCorridorAnalysisResponse {
  analysis_id: string;
  scope: {
    type: AutoAnalysisScopeType;
    id?: string | null;
    zone_count: number;
    point?: [number, number] | null;
  };
  summary: {
    mode: RoutingMode;
    profile: RoutingProfile;
    generated_candidates: number;
    returned_candidates: number;
    routed_candidates: number;
    unroutable_candidates: number;
    avg_score: number;
    max_score: number;
  };
  candidates: AutoCorridorAnalysisCandidate[];
  ranking: string[];
  stats: {
    critical_zones: number;
    scope_zone_names: string[];
  };
}

export interface GeoJsonFeatureCollection {
  type: 'FeatureCollection';
  features: Array<Record<string, unknown>>;
}

const BASE = '/geo/routing';

async function fetchBlob(endpoint: string): Promise<Blob> {
  const token = await getAuthToken();
  const response = await fetch(`${API_URL}${API_PREFIX}${endpoint}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!response.ok) {
    throw new Error(`API Error: ${response.status}`);
  }
  return response.blob();
}

export const routingApi = {
  getCorridor: (
    payload: CorridorRoutingRequest,
  ): Promise<CorridorRoutingResponse> =>
    apiFetch(`${BASE}/corridor`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  getAutoAnalysis: (
    payload: AutoCorridorAnalysisRequest,
  ): Promise<AutoCorridorAnalysisResponse> =>
    apiFetch(`${BASE}/auto-analysis`, {
      method: 'POST',
      body: JSON.stringify(payload),
      timeout: GEE_TIMEOUT,
    }),
  saveScenario: (payload: CorridorScenarioSaveRequest): Promise<CorridorScenario> =>
    apiFetch(`${BASE}/corridor/scenarios`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  listScenarios: (): Promise<{ items: CorridorScenarioListItem[]; total: number }> =>
    apiFetch(`${BASE}/corridor/scenarios`, {
      timeout: GEE_TIMEOUT,
    }),
  getScenario: (scenarioId: string): Promise<CorridorScenario> =>
    apiFetch(`${BASE}/corridor/scenarios/${scenarioId}`, {
      timeout: GEE_TIMEOUT,
    }),
  approveScenario: (scenarioId: string, note?: string): Promise<CorridorScenario> =>
    apiFetch(`${BASE}/corridor/scenarios/${scenarioId}/approve`, {
      method: 'POST',
      body: JSON.stringify(note ? { note } : {}),
    }),
  unapproveScenario: (scenarioId: string, note?: string): Promise<CorridorScenario> =>
    apiFetch(`${BASE}/corridor/scenarios/${scenarioId}/unapprove`, {
      method: 'POST',
      body: JSON.stringify(note ? { note } : {}),
    }),
  favoriteScenario: (
    scenarioId: string,
    is_favorite: boolean,
  ): Promise<CorridorScenario> =>
    apiFetch(`${BASE}/corridor/scenarios/${scenarioId}/favorite`, {
      method: 'POST',
      body: JSON.stringify({ is_favorite }),
    }),
  exportScenarioGeoJson: (scenarioId: string): Promise<GeoJsonFeatureCollection> =>
    apiFetch(`${BASE}/corridor/scenarios/${scenarioId}/geojson`),
  exportScenarioPdf: (scenarioId: string): Promise<Blob> =>
    fetchBlob(`${BASE}/corridor/scenarios/${scenarioId}/pdf`),
};
