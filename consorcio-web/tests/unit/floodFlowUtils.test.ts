import { describe, expect, it, vi } from 'vitest';

import { buildFloodFlowStats, buildZonaOptions, countRiskyZones, fmt, getHistoryZonaName, toISODate, yesterday } from '../../src/components/admin/flood-flow/floodFlowUtils';

describe('floodFlowUtils', () => {
  it('formats numbers and dates', () => {
    expect(fmt(null)).toBe('—');
    expect(fmt(12.3456)).toBe('12.35');
    expect(fmt(12.3456, 1)).toBe('12.3');
    expect(toISODate(new Date('2026-04-09T10:20:30.000Z'))).toBe('2026-04-09');
  });

  it('computes yesterday relative to now', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-04-09T12:00:00.000Z'));
    expect(toISODate(yesterday())).toBe('2026-04-08');
    vi.useRealTimers();
  });

  it('builds options and summary stats', () => {
    expect(buildZonaOptions([{ id: 'z1', nombre: 'Zona 1', cuenca: 'Cuenca A', superficie_ha: 10 }])).toEqual([
      { value: 'z1', label: 'Zona 1 — Cuenca A' },
    ]);

    const result = {
      total_zonas: 2,
      fecha_lluvia: '2026-04-08',
      results: [
        {
          zona_id: 'z1', zona_nombre: 'Zona 1', tc_minutos: 10, c_escorrentia: 0.4, c_source: 'landcover', intensidad_mm_h: 20,
          area_km2: 1, caudal_m3s: 3, capacidad_m3s: 2, porcentaje_capacidad: 150, nivel_riesgo: 'alto', fecha_lluvia: '2026-04-08', fecha_calculo: '2026-04-09',
        },
        {
          zona_id: 'z2', zona_nombre: 'Zona 2', tc_minutos: 12, c_escorrentia: 0.3, c_source: 'fallback', intensidad_mm_h: 18,
          area_km2: 2, caudal_m3s: 5, capacidad_m3s: 8, porcentaje_capacidad: 62.5, nivel_riesgo: 'bajo', fecha_lluvia: '2026-04-08', fecha_calculo: '2026-04-09',
        },
      ],
      errors: [],
    } as const;

    expect(buildFloodFlowStats(result)).toEqual({ maxQ: 5, zonasEnRiesgo: 1, usandoFallback: true });
    expect(countRiskyZones(result.results as any)).toBe(1);
    expect(getHistoryZonaName(result as any, 'z1')).toBe('Zona 1');
    expect(getHistoryZonaName(null, 'abcdefghi')).toBe('abcdefgh');
  });
});
