/**
 * useLandingStats — runtime-computed stats for the landing page.
 *
 * Data sources:
 *   - Area: `CONSORCIO_AREA_HA` (zona polygon, geodesic).
 *   - Caminos: public GEE caminos projection (`metadata.total_km` + per-consorcio
 *     rows). Same unique-geometry kilometres as the map legend — not Σ `lzn`
 *     and not a haversine of `/capas/caminos.geojson`.
 *   - Canales: `useCanales().relevados.features` — sum of `longitud_m`.
 */
import { useMemo } from 'react';

import { CONSORCIO_AREA_HA } from '../constants';
import { useCaminosColoreados } from './useCaminosColoreados';
import { useCanales } from './useCanales';

export interface CanalGroupSummary {
  /** Display name (without "(tramo X de N)" suffix). */
  label: string;
  /** `tramo_folder` for CGIC groups; full `nombre` for single canales. */
  key: string;
  tramos: number;
  km: number;
  source_style: string | null;
}

export interface CaminosConsorcioSummary {
  nombre: string;
  codigo: string;
  km: number;
}

export interface LandingStats {
  areaHa: number;
  caminosKm: number | null;
  canalesKm: number | null;
  /** Ordered (descending km) summary per canal/group for tooltip display. */
  canalesByGroup: CanalGroupSummary[];
  /** Ordered (descending km) GEE caminos rows for the landing tooltip. */
  caminosByConsorcio: CaminosConsorcioSummary[];
  isLoading: boolean;
}

export function useLandingStats(): LandingStats {
  const caminos = useCaminosColoreados();
  const { relevados, isLoading: canalesLoading } = useCanales();

  const caminosKm = caminos.metadata?.total_km ?? null;
  const caminosByConsorcio = useMemo(() => {
    return [...caminos.consorcios]
      .map((c) => ({ nombre: c.nombre, codigo: c.codigo, km: c.longitud_km }))
      .sort((a, b) => b.km - a.km);
  }, [caminos.consorcios]);

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
    caminosByConsorcio,
    isLoading: caminos.loading || canalesLoading,
  };
}
