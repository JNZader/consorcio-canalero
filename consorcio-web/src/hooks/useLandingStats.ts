/**
 * useLandingStats — runtime-computed stats for the landing page.
 *
 * Replaces the previously-hardcoded `STATS` array in `HomePage`. Data sources:
 *   - Area: `CONSORCIO_AREA_HA` constant (derived from `zona.geojson` 642-vertex
 *     polygon, 88_484 ha by geodesic area).
 *   - Caminos: `/capas/caminos.geojson` — sum of haversine length per LineString.
 *   - Canales: `useCanales().relevados.features` — sum of `longitud_m`.
 *
 * Static assets are cached forever (`staleTime: Infinity`) — they only change
 * when the ETL re-runs the geojson generation.
 */
import { useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';
import type { Feature, FeatureCollection, LineString, MultiLineString } from 'geojson';

import { CONSORCIO_AREA_HA } from '../constants';
import { useCanales } from './useCanales';

const EARTH_R = 6378137.0;

function haversineMeters(a: number[], b: number[]): number {
  const toRad = (d: number) => (d * Math.PI) / 180;
  const lat1 = toRad(a[1]!);
  const lat2 = toRad(b[1]!);
  const dLat = lat2 - lat1;
  const dLon = toRad(b[0]! - a[0]!);
  const h =
    Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_R * Math.atan2(Math.sqrt(h), Math.sqrt(1 - h));
}

function lineStringLength(coords: number[][]): number {
  let total = 0;
  for (let i = 0; i < coords.length - 1; i += 1) {
    total += haversineMeters(coords[i]!, coords[i + 1]!);
  }
  return total;
}

function featureLength(feat: Feature<LineString | MultiLineString>): number {
  const g = feat.geometry;
  if (g.type === 'LineString') return lineStringLength(g.coordinates);
  if (g.type === 'MultiLineString') {
    return g.coordinates.reduce((acc, ls) => acc + lineStringLength(ls), 0);
  }
  return 0;
}

async function fetchCaminosCollection(): Promise<FeatureCollection<LineString | MultiLineString>> {
  const res = await fetch('/capas/caminos.geojson');
  if (!res.ok) throw new Error(`Failed to fetch caminos.geojson (${res.status})`);
  return (await res.json()) as FeatureCollection<LineString | MultiLineString>;
}

export interface CanalGroupSummary {
  /** Display name (without "(tramo X de N)" suffix). */
  label: string;
  /** `tramo_folder` for CGIC groups; full `nombre` for single canales. */
  key: string;
  tramos: number;
  km: number;
  source_style: string | null;
}

export interface LandingStats {
  areaHa: number;
  caminosKm: number | null;
  canalesKm: number | null;
  /** Ordered (descending km) summary per canal/group for tooltip display. */
  canalesByGroup: CanalGroupSummary[];
  isLoading: boolean;
}

export function useLandingStats(): LandingStats {
  const caminos = useQuery({
    queryKey: ['landing', 'caminos'] as const,
    queryFn: fetchCaminosCollection,
    staleTime: Number.POSITIVE_INFINITY,
  });

  const { relevados, isLoading: canalesLoading } = useCanales();

  const caminosKm = useMemo(() => {
    if (!caminos.data) return null;
    const m = caminos.data.features.reduce((acc, f) => acc + featureLength(f), 0);
    return m / 1000;
  }, [caminos.data]);

  const { canalesKm, canalesByGroup } = useMemo(() => {
    if (!relevados) return { canalesKm: null, canalesByGroup: [] as CanalGroupSummary[] };
    const groups = new Map<string, CanalGroupSummary>();
    let totalM = 0;
    for (const f of relevados.features) {
      const p = f.properties;
      const folder = p.tramo_folder ?? null;
      const key = folder ?? p.nombre;
      const label = folder ? p.nombre.replace(/\s*\(tramo\s+\d+\s+de\s+\d+\)\s*$/i, '') : p.nombre;
      const prev = groups.get(key);
      if (prev) {
        prev.tramos += 1;
        prev.km += p.longitud_m / 1000;
      } else {
        groups.set(key, {
          label,
          key,
          tramos: 1,
          km: p.longitud_m / 1000,
          source_style: p.source_style,
        });
      }
      totalM += p.longitud_m;
    }
    const arr = Array.from(groups.values()).sort((a, b) => b.km - a.km);
    return { canalesKm: totalM / 1000, canalesByGroup: arr };
  }, [relevados]);

  return {
    areaHa: CONSORCIO_AREA_HA,
    caminosKm,
    canalesKm,
    canalesByGroup,
    isLoading: caminos.isLoading || canalesLoading,
  };
}
