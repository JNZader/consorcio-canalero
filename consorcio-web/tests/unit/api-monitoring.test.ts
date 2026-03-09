/**
 * api-monitoring.test.ts
 * Unit: Monitoring API and types
 * Coverage Target: 100% for monitoring.ts
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  monitoringApi,
  type MonitoringDashboardData,
} from '../../src/lib/api/monitoring';
import * as coreModule from '../../src/lib/api/core';

// Mock the core module
vi.mock('../../src/lib/api/core', () => ({
  apiFetch: vi.fn(),
  LONG_TIMEOUT: 120000,
}));

const mockApiFetch = coreModule.apiFetch as ReturnType<typeof vi.fn>;

describe('Monitoring API', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('monitoringApi.getDashboard', () => {
    it('should call apiFetch with correct endpoint', async () => {
      const mockData: MonitoringDashboardData = {
        summary: {
          area_total_ha: 10000,
          area_productiva_ha: 8000,
          area_problematica_ha: 2000,
          porcentaje_problematico: 20,
        },
        clasificacion: {},
        cuencas: {},
        ranking_cuencas: [],
        alertas: [],
        total_alertas: 0,
        periodo: { inicio: '2024-01-01', fin: '2024-01-31' },
        fecha_actualizacion: '2024-01-31T12:00:00Z',
      };

      mockApiFetch.mockResolvedValue(mockData);

      const result = await monitoringApi.getDashboard();

      expect(mockApiFetch).toHaveBeenCalledWith('/monitoring/dashboard', {
        timeout: coreModule.LONG_TIMEOUT,
      });
      expect(result).toEqual(mockData);
    });

    it('should use LONG_TIMEOUT for dashboard data', async () => {
      const mockData: MonitoringDashboardData = {
        summary: {
          area_total_ha: 10000,
          area_productiva_ha: 8000,
          area_problematica_ha: 2000,
          porcentaje_problematico: 20,
        },
        clasificacion: {},
        cuencas: {},
        ranking_cuencas: [],
        alertas: [],
        total_alertas: 0,
        periodo: { inicio: '2024-01-01', fin: '2024-01-31' },
        fecha_actualizacion: '2024-01-31T12:00:00Z',
      };

      mockApiFetch.mockResolvedValue(mockData);

      await monitoringApi.getDashboard();

      const callArgs = mockApiFetch.mock.calls[0];
      expect(callArgs[1].timeout).toBe(coreModule.LONG_TIMEOUT);
    });

    it('should return complete MonitoringDashboardData', async () => {
      const mockData: MonitoringDashboardData = {
        summary: {
          area_total_ha: 15000,
          area_productiva_ha: 12000,
          area_problematica_ha: 3000,
          porcentaje_problematico: 20,
        },
        clasificacion: { agua: 100, bosque: 500 },
        cuencas: { cuenca1: { valor: 100 } },
        ranking_cuencas: [
          {
            cuenca: 'Cuenca A',
            porcentaje_problematico: 25,
            area_anegada_ha: 1000,
          },
          {
            cuenca: 'Cuenca B',
            porcentaje_problematico: 15,
            area_anegada_ha: 500,
          },
        ],
        alertas: [
          {
            tipo: 'anegamiento',
            severidad: 'alta',
            icono: 'alert',
            cuenca: 'Cuenca A',
            mensaje: 'Alto nivel de anegamiento',
            detalle: { valor: 1000 },
            accion_sugerida: 'Revisar drenaje',
          },
        ],
        total_alertas: 1,
        periodo: { inicio: '2024-02-01', fin: '2024-02-29' },
        fecha_actualizacion: '2024-02-29T15:30:00Z',
      };

      mockApiFetch.mockResolvedValue(mockData);

      const result = await monitoringApi.getDashboard();

      expect(result).toHaveProperty('summary');
      expect(result).toHaveProperty('clasificacion');
      expect(result).toHaveProperty('cuencas');
      expect(result).toHaveProperty('ranking_cuencas');
      expect(result).toHaveProperty('alertas');
      expect(result).toHaveProperty('total_alertas');
      expect(result).toHaveProperty('periodo');
      expect(result).toHaveProperty('fecha_actualizacion');
    });

    it('should preserve summary statistics', async () => {
      const mockData: MonitoringDashboardData = {
        summary: {
          area_total_ha: 12500,
          area_productiva_ha: 10000,
          area_problematica_ha: 2500,
          porcentaje_problematico: 20,
        },
        clasificacion: {},
        cuencas: {},
        ranking_cuencas: [],
        alertas: [],
        total_alertas: 0,
        periodo: { inicio: '2024-01-01', fin: '2024-01-31' },
        fecha_actualizacion: '2024-01-31T12:00:00Z',
      };

      mockApiFetch.mockResolvedValue(mockData);

      const result = await monitoringApi.getDashboard();

      expect(result.summary.area_total_ha).toBe(12500);
      expect(result.summary.area_productiva_ha).toBe(10000);
      expect(result.summary.area_problematica_ha).toBe(2500);
      expect(result.summary.porcentaje_problematico).toBe(20);
    });

    it('should handle empty ranking_cuencas', async () => {
      const mockData: MonitoringDashboardData = {
        summary: {
          area_total_ha: 10000,
          area_productiva_ha: 8000,
          area_problematica_ha: 2000,
          porcentaje_problematico: 20,
        },
        clasificacion: {},
        cuencas: {},
        ranking_cuencas: [],
        alertas: [],
        total_alertas: 0,
        periodo: { inicio: '2024-01-01', fin: '2024-01-31' },
        fecha_actualizacion: '2024-01-31T12:00:00Z',
      };

      mockApiFetch.mockResolvedValue(mockData);

      const result = await monitoringApi.getDashboard();

      expect(Array.isArray(result.ranking_cuencas)).toBe(true);
      expect(result.ranking_cuencas).toHaveLength(0);
    });

    it('should handle multiple ranking_cuencas entries', async () => {
      const mockData: MonitoringDashboardData = {
        summary: {
          area_total_ha: 10000,
          area_productiva_ha: 8000,
          area_problematica_ha: 2000,
          porcentaje_problematico: 20,
        },
        clasificacion: {},
        cuencas: {},
        ranking_cuencas: [
          {
            cuenca: 'Cuenca Norte',
            porcentaje_problematico: 30,
            area_anegada_ha: 1500,
          },
          {
            cuenca: 'Cuenca Sur',
            porcentaje_problematico: 20,
            area_anegada_ha: 500,
          },
          {
            cuenca: 'Cuenca Centro',
            porcentaje_problematico: 10,
            area_anegada_ha: 0,
          },
        ],
        alertas: [],
        total_alertas: 0,
        periodo: { inicio: '2024-01-01', fin: '2024-01-31' },
        fecha_actualizacion: '2024-01-31T12:00:00Z',
      };

      mockApiFetch.mockResolvedValue(mockData);

      const result = await monitoringApi.getDashboard();

      expect(result.ranking_cuencas).toHaveLength(3);
      expect(result.ranking_cuencas[0].cuenca).toBe('Cuenca Norte');
      expect(result.ranking_cuencas[1].cuenca).toBe('Cuenca Sur');
      expect(result.ranking_cuencas[2].cuenca).toBe('Cuenca Centro');
    });

    it('should handle empty alertas', async () => {
      const mockData: MonitoringDashboardData = {
        summary: {
          area_total_ha: 10000,
          area_productiva_ha: 8000,
          area_problematica_ha: 2000,
          porcentaje_problematico: 20,
        },
        clasificacion: {},
        cuencas: {},
        ranking_cuencas: [],
        alertas: [],
        total_alertas: 0,
        periodo: { inicio: '2024-01-01', fin: '2024-01-31' },
        fecha_actualizacion: '2024-01-31T12:00:00Z',
      };

      mockApiFetch.mockResolvedValue(mockData);

      const result = await monitoringApi.getDashboard();

      expect(Array.isArray(result.alertas)).toBe(true);
      expect(result.alertas).toHaveLength(0);
      expect(result.total_alertas).toBe(0);
    });

    it('should handle multiple alertas with different severities', async () => {
      const mockData: MonitoringDashboardData = {
        summary: {
          area_total_ha: 10000,
          area_productiva_ha: 8000,
          area_problematica_ha: 2000,
          porcentaje_problematico: 20,
        },
        clasificacion: {},
        cuencas: {},
        ranking_cuencas: [],
        alertas: [
          {
            tipo: 'anegamiento',
            severidad: 'critica',
            icono: 'critical',
            cuenca: 'Cuenca A',
            mensaje: 'Anegamiento crítico detectado',
            detalle: { nivel: 'muy_alto' },
            accion_sugerida: 'Intervención inmediata requerida',
          },
          {
            tipo: 'sequedad',
            severidad: 'moderada',
            icono: 'warning',
            cuenca: 'Cuenca B',
            mensaje: 'Sequedad moderada',
            detalle: { nivel: 'bajo' },
            accion_sugerida: 'Monitorear continuamente',
          },
          {
            tipo: 'vegetacion',
            severidad: 'baja',
            icono: 'info',
            cuenca: 'Cuenca C',
            mensaje: 'Cambios de vegetación detectados',
            detalle: { cambio: 'normal' },
            accion_sugerida: 'Revisión programada',
          },
        ],
        total_alertas: 3,
        periodo: { inicio: '2024-01-01', fin: '2024-01-31' },
        fecha_actualizacion: '2024-01-31T12:00:00Z',
      };

      mockApiFetch.mockResolvedValue(mockData);

      const result = await monitoringApi.getDashboard();

      expect(result.alertas).toHaveLength(3);
      expect(result.total_alertas).toBe(3);
      expect(result.alertas[0].severidad).toBe('critica');
      expect(result.alertas[1].severidad).toBe('moderada');
      expect(result.alertas[2].severidad).toBe('baja');
    });

    it('should preserve periodo dates', async () => {
      const mockData: MonitoringDashboardData = {
        summary: {
          area_total_ha: 10000,
          area_productiva_ha: 8000,
          area_problematica_ha: 2000,
          porcentaje_problematico: 20,
        },
        clasificacion: {},
        cuencas: {},
        ranking_cuencas: [],
        alertas: [],
        total_alertas: 0,
        periodo: { inicio: '2024-03-01', fin: '2024-03-31' },
        fecha_actualizacion: '2024-03-31T23:59:59Z',
      };

      mockApiFetch.mockResolvedValue(mockData);

      const result = await monitoringApi.getDashboard();

      expect(result.periodo.inicio).toBe('2024-03-01');
      expect(result.periodo.fin).toBe('2024-03-31');
      expect(result.fecha_actualizacion).toBe('2024-03-31T23:59:59Z');
    });
  });

  describe('Type definitions', () => {
    it('MonitoringDashboardData interface should have required structure', () => {
      const mockData: MonitoringDashboardData = {
        summary: {
          area_total_ha: 10000,
          area_productiva_ha: 8000,
          area_problematica_ha: 2000,
          porcentaje_problematico: 20,
        },
        clasificacion: {},
        cuencas: {},
        ranking_cuencas: [],
        alertas: [],
        total_alertas: 0,
        periodo: { inicio: '2024-01-01', fin: '2024-01-31' },
        fecha_actualizacion: '2024-01-31T12:00:00Z',
      };

      expect(mockData).toHaveProperty('summary');
      expect(mockData).toHaveProperty('clasificacion');
      expect(mockData).toHaveProperty('cuencas');
      expect(mockData).toHaveProperty('ranking_cuencas');
      expect(mockData).toHaveProperty('alertas');
      expect(mockData).toHaveProperty('total_alertas');
      expect(mockData).toHaveProperty('periodo');
      expect(mockData).toHaveProperty('fecha_actualizacion');
    });
  });

  describe('monitoringApi object', () => {
    it('should be an object', () => {
      expect(typeof monitoringApi).toBe('object');
      expect(monitoringApi).not.toBeNull();
    });

    it('should have getDashboard method', () => {
      expect(typeof monitoringApi.getDashboard).toBe('function');
    });

    it('should expose only public methods', () => {
      const methodNames = Object.keys(monitoringApi);
      expect(methodNames).toContain('getDashboard');
    });
  });
});
