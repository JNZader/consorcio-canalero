import type { FloodFlowResponse, ZonaFloodFlowResult, ZonaOperativaItem } from '../../../lib/api/floodFlow';

export function fmt(value: number | null | undefined, decimals = 2): string {
  if (value == null) return '—';
  return value.toFixed(decimals);
}

export function yesterday(): Date {
  const date = new Date();
  date.setDate(date.getDate() - 1);
  return date;
}

export function toISODate(date: Date): string {
  return date.toISOString().split('T')[0];
}

export function buildZonaOptions(zonas: ZonaOperativaItem[]) {
  return zonas.map((zona) => ({
    value: zona.id,
    label: `${zona.nombre} — ${zona.cuenca}`,
  }));
}

export function buildFloodFlowStats(result: FloodFlowResponse | null) {
  const maxQ = result ? Math.max(...result.results.map((item) => item.caudal_m3s), 0) : null;
  const zonasEnRiesgo = result
    ? result.results.filter((item) => item.nivel_riesgo === 'alto' || item.nivel_riesgo === 'critico').length
    : null;
  const usandoFallback = result?.results.some((item) => item.intensidad_mm_h === 20) ?? false;

  return { maxQ, zonasEnRiesgo, usandoFallback };
}

export function getHistoryZonaName(
  result: FloodFlowResponse | null,
  historyZona: string | null,
) {
  return result?.results.find((item) => item.zona_id === historyZona)?.zona_nombre ?? historyZona?.slice(0, 8);
}

export function countRiskyZones(results: ZonaFloodFlowResult[]) {
  return results.filter((item) => item.nivel_riesgo === 'alto' || item.nivel_riesgo === 'critico').length;
}
