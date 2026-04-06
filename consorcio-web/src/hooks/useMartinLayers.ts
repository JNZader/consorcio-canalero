/**
 * Martin MVT layer utilities for Leaflet.
 *
 * Martin auto-publishes all PostGIS tables with geometry columns as MVT.
 * Sources we care about: zonas_operativas, puntos_conflicto, canal_suggestions.
 *
 * Flood risk colors are fetched from the backend flood-flow API and applied
 * as fill colors per zona via the vectorgrid styling function.
 */

import { useQuery } from '@tanstack/react-query';

const MARTIN_URL = import.meta.env.VITE_MARTIN_URL || 'http://localhost:3000';

// ─── Source definitions ──────────────────────────────────────────────────────

export interface MartinSource {
  /** Martin table/view name — must match what's auto-published */
  table: string;
  label: string;
  defaultVisible: boolean;
  /** Leaflet vectorgrid styling */
  style: {
    fill: boolean;
    color: string;
    fillColor: string;
    fillOpacity: number;
    weight: number;
    opacity: number;
    radius?: number;
  };
}

export const MARTIN_SOURCES: Record<string, MartinSource> = {
  puntos_conflicto: {
    table: 'puntos_conflicto',
    label: 'Puntos de Conflicto',
    defaultVisible: false,
    style: {
      fill: true,
      color: '#b91c1c',
      fillColor: '#ef4444',
      fillOpacity: 0.85,
      weight: 1,
      opacity: 1,
      radius: 5,
    },
  },
  canal_suggestions: {
    table: 'canal_suggestions',
    label: 'Sugerencias de Canal',
    defaultVisible: false,
    style: {
      fill: true,
      color: '#0369a1',
      fillColor: '#38bdf8',
      fillOpacity: 0.6,
      weight: 2,
      opacity: 0.8,
    },
  },
};

/** Build a Martin MVT tile URL template for a given table name. */
export function getMartinTileUrl(table: string): string {
  return `${MARTIN_URL}/${table}/{z}/{x}/{y}`;
}

// ─── Flood risk color per zona ───────────────────────────────────────────────

const RISK_COLORS: Record<string, string> = {
  bajo: '#22c55e',
  medio: '#f59e0b',
  alto: '#ef4444',
  critico: '#7f1d1d',
};

export interface ZonaRiskEntry {
  zona_id: string;
  nivel_riesgo: string | null;
}

/**
 * Fetch latest flood risk level per zona from backend.
 * Used to color the zonas_operativas MVT layer dynamically.
 */
export function useZonaRiskColors() {
  return useQuery<Record<string, string>>({
    queryKey: ['zona-risk-colors'],
    queryFn: async () => {
      const apiUrl = import.meta.env.VITE_API_URL || '';
      const res = await fetch(`${apiUrl}/api/v2/geo/hydrology/flood-flow/latest`, {
        credentials: 'include',
      });
      if (!res.ok) return {};
      const data: ZonaRiskEntry[] = await res.json();
      const map: Record<string, string> = {};
      for (const entry of data) {
        map[entry.zona_id] = RISK_COLORS[entry.nivel_riesgo ?? ''] ?? '#6b7280';
      }
      return map;
    },
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });
}

/** Returns the fill color for a zona given the risk map. */
export function getZonaFillColor(
  zonaId: string | undefined,
  riskColors: Record<string, string>,
): string {
  if (!zonaId) return '#3b82f6';
  return riskColors[zonaId] ?? '#3b82f6';
}
