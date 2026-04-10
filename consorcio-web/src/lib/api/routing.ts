import { apiFetch, API_PREFIX, API_URL, getAuthToken } from './core';

export type RoutingProfile = 'balanceado' | 'hidraulico' | 'evitar_propiedad';
export type RoutingMode = 'network' | 'raster';

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
      edge_count_with_profile_factor: number;
      avg_profile_factor: number;
      max_profile_factor: number;
      min_profile_factor: number;
      parcel_intersections?: number;
      near_parcels?: number;
      avg_hydric_index?: number | null;
      hydraulic_edge_count?: number;
      profile_edge_count?: number;
      weights?: Record<string, number>;
      mode?: RoutingMode;
      property_features?: number;
      hydric_features?: number;
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
}

export interface CorridorScenario {
  id: string;
  name: string;
  profile: RoutingProfile;
  request_payload: CorridorRoutingRequest;
  result_payload: CorridorRoutingResponse;
  notes?: string | null;
  is_approved?: boolean;
  approved_at?: string | null;
  approved_by_id?: string | null;
  created_by_id?: string | null;
  created_at: string;
  updated_at?: string;
}

export interface CorridorScenarioListItem {
  id: string;
  name: string;
  profile: RoutingProfile;
  notes?: string | null;
  is_approved?: boolean;
  approved_at?: string | null;
  created_at: string;
}

export interface CorridorScenarioSaveRequest {
  name: string;
  profile: RoutingProfile;
  request_payload: CorridorRoutingRequest;
  result_payload: CorridorRoutingResponse;
  notes?: string;
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
  saveScenario: (payload: CorridorScenarioSaveRequest): Promise<CorridorScenario> =>
    apiFetch(`${BASE}/corridor/scenarios`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  listScenarios: (): Promise<{ items: CorridorScenarioListItem[]; total: number }> =>
    apiFetch(`${BASE}/corridor/scenarios`),
  getScenario: (scenarioId: string): Promise<CorridorScenario> =>
    apiFetch(`${BASE}/corridor/scenarios/${scenarioId}`),
  approveScenario: (scenarioId: string): Promise<CorridorScenario> =>
    apiFetch(`${BASE}/corridor/scenarios/${scenarioId}/approve`, {
      method: 'POST',
    }),
  exportScenarioGeoJson: (scenarioId: string): Promise<GeoJsonFeatureCollection> =>
    apiFetch(`${BASE}/corridor/scenarios/${scenarioId}/geojson`),
  exportScenarioPdf: (scenarioId: string): Promise<Blob> =>
    fetchBlob(`${BASE}/corridor/scenarios/${scenarioId}/pdf`),
};
