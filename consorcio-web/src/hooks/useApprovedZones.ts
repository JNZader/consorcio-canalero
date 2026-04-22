import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { FeatureCollection } from 'geojson';
import { API_URL, getAuthToken } from '../lib/api';
import { queryKeys } from '../lib/query';

type ApprovedZonesPayload = {
  readonly id: string;
  readonly nombre: string;
  readonly version: number;
  readonly cuenca: string | null;
  readonly featureCollection: FeatureCollection;
  readonly assignments: Record<string, string>;
  readonly zone_names: Record<string, string>;
  readonly notes?: string | null;
  readonly approvedAt: string;
  readonly approvedById: string | null;
  readonly approvedByName?: string | null;
};

async function fetchApprovedZones() {
  const response = await fetch(`${API_URL}/api/v2/geo/basins/approved-zones/current`);
  if (!response.ok) {
    throw new Error(`Error fetching approved zones: ${response.status}`);
  }
  const data = (await response.json()) as ApprovedZonesPayload | null;
  return data;
}

async function saveApprovedZonesRequest(
  featureCollection: FeatureCollection,
  options?: {
    assignments?: Record<string, string>;
    zoneNames?: Record<string, string>;
    nombre?: string;
    cuenca?: string | null;
    notes?: string | null;
  }
) {
  const token = await getAuthToken();
  const response = await fetch(`${API_URL}/api/v2/geo/basins/approved-zones/current`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      featureCollection,
      assignments: options?.assignments ?? {},
      zone_names: options?.zoneNames ?? {},
      nombre: options?.nombre ?? 'Zonificación Consorcio aprobada',
      cuenca: options?.cuenca ?? null,
      notes: options?.notes ?? null,
    }),
  });
  if (!response.ok) {
    throw new Error(`Error saving approved zones: ${response.status}`);
  }
  return (await response.json()) as ApprovedZonesPayload;
}

async function clearApprovedZonesRequest(cuenca?: string | null) {
  const token = await getAuthToken();
  const url = new URL(`${API_URL}/api/v2/geo/basins/approved-zones/current`);
  if (cuenca) url.searchParams.set('cuenca', cuenca);
  const response = await fetch(url.toString(), {
    method: 'DELETE',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) {
    throw new Error(`Error clearing approved zones: ${response.status}`);
  }
}

async function fetchApprovedZonesHistory() {
  const response = await fetch(`${API_URL}/api/v2/geo/basins/approved-zones/history`);
  if (!response.ok) {
    throw new Error(`Error fetching approved zones history: ${response.status}`);
  }
  return (await response.json()) as ApprovedZonesPayload[];
}

async function restoreApprovedZonesRequest(id: string) {
  const token = await getAuthToken();
  const response = await fetch(`${API_URL}/api/v2/geo/basins/approved-zones/${id}/restore`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) {
    throw new Error(`Error restoring approved zones: ${response.status}`);
  }
  return (await response.json()) as ApprovedZonesPayload;
}

export function useApprovedZones() {
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: queryKeys.approvedZones(),
    queryFn: fetchApprovedZones,
    staleTime: 1000 * 60,
  });

  const historyQuery = useQuery({
    queryKey: queryKeys.approvedZonesHistory(),
    queryFn: fetchApprovedZonesHistory,
    staleTime: 1000 * 60,
  });

  const saveMutation = useMutation({
    mutationFn: ({
      featureCollection,
      assignments,
      zoneNames,
      nombre,
      cuenca,
      notes,
    }: {
      featureCollection: FeatureCollection;
      assignments?: Record<string, string>;
      zoneNames?: Record<string, string>;
      nombre?: string;
      cuenca?: string | null;
      notes?: string | null;
    }) =>
      saveApprovedZonesRequest(featureCollection, {
        assignments,
        zoneNames,
        nombre,
        cuenca,
        notes,
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(queryKeys.approvedZones(), data);
      queryClient.invalidateQueries({ queryKey: queryKeys.approvedZonesHistory() });
    },
  });

  const clearMutation = useMutation({
    mutationFn: ({ cuenca }: { cuenca?: string | null } = {}) => clearApprovedZonesRequest(cuenca),
    onSuccess: () => {
      queryClient.setQueryData(queryKeys.approvedZones(), null);
      queryClient.invalidateQueries({ queryKey: queryKeys.approvedZonesHistory() });
    },
  });

  const restoreMutation = useMutation({
    mutationFn: ({ id }: { id: string }) => restoreApprovedZonesRequest(id),
    onSuccess: (data) => {
      queryClient.setQueryData(queryKeys.approvedZones(), data);
      queryClient.invalidateQueries({ queryKey: queryKeys.approvedZonesHistory() });
    },
  });

  return {
    approvedZoneRecord: query.data ?? null,
    approvedZones: query.data?.featureCollection ?? null,
    approvedAt: query.data?.approvedAt ?? null,
    approvedVersion: query.data?.version ?? null,
    hasApprovedZones: !!query.data?.featureCollection,
    approvedZonesHistory: historyQuery.data ?? [],
    saveApprovedZones: async (
      featureCollection: FeatureCollection,
      options?: {
        assignments?: Record<string, string>;
        zoneNames?: Record<string, string>;
        nombre?: string;
        cuenca?: string | null;
        notes?: string | null;
      }
    ) =>
      saveMutation.mutateAsync({
        featureCollection,
        assignments: options?.assignments,
        zoneNames: options?.zoneNames,
        nombre: options?.nombre,
        cuenca: options?.cuenca,
        notes: options?.notes,
      }),
    clearApprovedZones: async (options?: { cuenca?: string | null }) =>
      clearMutation.mutateAsync({ cuenca: options?.cuenca }),
    restoreApprovedZonesVersion: async (id: string) => restoreMutation.mutateAsync({ id }),
    loading: query.isLoading,
    historyLoading: historyQuery.isLoading,
    saving: saveMutation.isPending,
    clearing: clearMutation.isPending,
    restoring: restoreMutation.isPending,
  };
}
