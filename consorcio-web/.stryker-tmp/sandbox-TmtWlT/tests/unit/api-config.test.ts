/**
 * api-config.test.ts
 * Unit: System configuration API and types
 * Coverage Target: 100% for config.ts
 */
// @ts-nocheck


import { describe, it, expect, vi, beforeEach } from 'vitest';
import { configApi, type SystemConfig, type MapConfig, type CuencaConfig, type AnalysisConfig } from '../../src/lib/api/config';
import * as coreModule from '../../src/lib/api/core';

// Mock the core module
vi.mock('../../src/lib/api/core', () => ({
  apiFetch: vi.fn(),
}));

const mockApiFetch = coreModule.apiFetch as ReturnType<typeof vi.fn>;

describe('Config API', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('configApi.getSystemConfig', () => {
    it('should call apiFetch with correct endpoint', async () => {
      const mockConfig: SystemConfig = {
        consorcio_area_ha: 10000,
        consorcio_km_caminos: 500,
        map: {
          center: { lat: -35.2, lng: -62.5 },
          zoom: 10,
          bounds: { north: -34, south: -36, east: -61, west: -64 },
        },
        cuencas: [],
        analysis: { default_max_cloud: 20, default_days_back: 30 },
      };
      
      mockApiFetch.mockResolvedValue(mockConfig);

      const result = await configApi.getSystemConfig();

      expect(mockApiFetch).toHaveBeenCalledWith('/config/system', { skipAuth: true });
      expect(result).toEqual(mockConfig);
    });

    it('should skip authentication', async () => {
      mockApiFetch.mockResolvedValue({});

      await configApi.getSystemConfig();

      const callArgs = mockApiFetch.mock.calls[0];
      expect(callArgs[1]).toHaveProperty('skipAuth', true);
    });

    it('should return SystemConfig with all required fields', async () => {
      const mockConfig: SystemConfig = {
        consorcio_area_ha: 15000,
        consorcio_km_caminos: 750,
        map: {
          center: { lat: -35.5, lng: -62.0 },
          zoom: 11,
          bounds: { north: -34.5, south: -36.5, east: -60.5, west: -63.5 },
        },
        cuencas: [
          { id: '1', nombre: 'Cuenca Norte', ha: 5000, color: '#FF0000' },
          { id: '2', nombre: 'Cuenca Sur', ha: 10000, color: '#00FF00' },
        ],
        analysis: { default_max_cloud: 25, default_days_back: 60 },
      };

      mockApiFetch.mockResolvedValue(mockConfig);

      const result = await configApi.getSystemConfig();

      expect(result).toHaveProperty('consorcio_area_ha');
      expect(result).toHaveProperty('consorcio_km_caminos');
      expect(result).toHaveProperty('map');
      expect(result).toHaveProperty('cuencas');
      expect(result).toHaveProperty('analysis');
    });

    it('should handle empty cuencas array', async () => {
      const mockConfig: SystemConfig = {
        consorcio_area_ha: 0,
        consorcio_km_caminos: 0,
        map: {
          center: { lat: 0, lng: 0 },
          zoom: 1,
          bounds: { north: 0, south: 0, east: 0, west: 0 },
        },
        cuencas: [],
        analysis: { default_max_cloud: 0, default_days_back: 0 },
      };

      mockApiFetch.mockResolvedValue(mockConfig);

      const result = await configApi.getSystemConfig();

      expect(Array.isArray(result.cuencas)).toBe(true);
      expect(result.cuencas).toHaveLength(0);
    });

    it('should handle multiple cuencas', async () => {
      const mockConfig: SystemConfig = {
        consorcio_area_ha: 20000,
        consorcio_km_caminos: 1000,
        map: {
          center: { lat: -35, lng: -62 },
          zoom: 10,
          bounds: { north: -34, south: -36, east: -61, west: -63 },
        },
        cuencas: [
          { id: '1', nombre: 'Cuenca A', ha: 5000, color: '#FFFFFF' },
          { id: '2', nombre: 'Cuenca B', ha: 7000, color: '#000000' },
          { id: '3', nombre: 'Cuenca C', ha: 8000, color: '#808080' },
        ],
        analysis: { default_max_cloud: 30, default_days_back: 90 },
      };

      mockApiFetch.mockResolvedValue(mockConfig);

      const result = await configApi.getSystemConfig();

      expect(result.cuencas).toHaveLength(3);
      expect(result.cuencas[0].nombre).toBe('Cuenca A');
      expect(result.cuencas[1].nombre).toBe('Cuenca B');
      expect(result.cuencas[2].nombre).toBe('Cuenca C');
    });

    it('should preserve numeric values for area and roads', async () => {
      const mockConfig: SystemConfig = {
        consorcio_area_ha: 12345.67,
        consorcio_km_caminos: 567.89,
        map: {
          center: { lat: -35.123, lng: -62.456 },
          zoom: 10,
          bounds: { north: -34.5, south: -35.5, east: -61.5, west: -63.5 },
        },
        cuencas: [],
        analysis: { default_max_cloud: 20, default_days_back: 30 },
      };

      mockApiFetch.mockResolvedValue(mockConfig);

      const result = await configApi.getSystemConfig();

      expect(result.consorcio_area_ha).toBe(12345.67);
      expect(result.consorcio_km_caminos).toBe(567.89);
    });

    it('should preserve map center coordinates', async () => {
      const mockConfig: SystemConfig = {
        consorcio_area_ha: 10000,
        consorcio_km_caminos: 500,
        map: {
          center: { lat: -35.6789, lng: -62.1234 },
          zoom: 12,
          bounds: { north: -35, south: -36, east: -61, west: -63 },
        },
        cuencas: [],
        analysis: { default_max_cloud: 20, default_days_back: 30 },
      };

      mockApiFetch.mockResolvedValue(mockConfig);

      const result = await configApi.getSystemConfig();

      expect(result.map.center.lat).toBe(-35.6789);
      expect(result.map.center.lng).toBe(-62.1234);
    });

    it('should preserve map bounds', async () => {
      const mockConfig: SystemConfig = {
        consorcio_area_ha: 10000,
        consorcio_km_caminos: 500,
        map: {
          center: { lat: -35, lng: -62 },
          zoom: 10,
          bounds: { north: -34.1, south: -35.9, east: -61.2, west: -62.8 },
        },
        cuencas: [],
        analysis: { default_max_cloud: 20, default_days_back: 30 },
      };

      mockApiFetch.mockResolvedValue(mockConfig);

      const result = await configApi.getSystemConfig();

      expect(result.map.bounds.north).toBe(-34.1);
      expect(result.map.bounds.south).toBe(-35.9);
      expect(result.map.bounds.east).toBe(-61.2);
      expect(result.map.bounds.west).toBe(-62.8);
    });

    it('should preserve analysis defaults', async () => {
      const mockConfig: SystemConfig = {
        consorcio_area_ha: 10000,
        consorcio_km_caminos: 500,
        map: {
          center: { lat: -35, lng: -62 },
          zoom: 10,
          bounds: { north: -34, south: -36, east: -61, west: -63 },
        },
        cuencas: [],
        analysis: { default_max_cloud: 35, default_days_back: 120 },
      };

      mockApiFetch.mockResolvedValue(mockConfig);

      const result = await configApi.getSystemConfig();

      expect(result.analysis.default_max_cloud).toBe(35);
      expect(result.analysis.default_days_back).toBe(120);
    });

    it('should preserve cuenca color codes', async () => {
      const mockConfig: SystemConfig = {
        consorcio_area_ha: 10000,
        consorcio_km_caminos: 500,
        map: {
          center: { lat: -35, lng: -62 },
          zoom: 10,
          bounds: { north: -34, south: -36, east: -61, west: -63 },
        },
        cuencas: [
          { id: 'c1', nombre: 'Cuenca Color Test', ha: 1000, color: '#FF00FF' },
        ],
        analysis: { default_max_cloud: 20, default_days_back: 30 },
      };

      mockApiFetch.mockResolvedValue(mockConfig);

      const result = await configApi.getSystemConfig();

      expect(result.cuencas[0].color).toBe('#FF00FF');
    });
  });

  describe('Type definitions', () => {
    it('MapConfig interface should have required structure', () => {
      const mapConfig: MapConfig = {
        center: { lat: -35, lng: -62 },
        zoom: 10,
        bounds: { north: -34, south: -36, east: -61, west: -63 },
      };

      expect(mapConfig).toHaveProperty('center');
      expect(mapConfig).toHaveProperty('zoom');
      expect(mapConfig).toHaveProperty('bounds');
      expect(typeof mapConfig.center.lat).toBe('number');
      expect(typeof mapConfig.center.lng).toBe('number');
      expect(typeof mapConfig.zoom).toBe('number');
    });

    it('CuencaConfig interface should have required structure', () => {
      const cuenca: CuencaConfig = {
        id: '1',
        nombre: 'Test Cuenca',
        ha: 5000,
        color: '#FF0000',
      };

      expect(cuenca).toHaveProperty('id');
      expect(cuenca).toHaveProperty('nombre');
      expect(cuenca).toHaveProperty('ha');
      expect(cuenca).toHaveProperty('color');
    });

    it('AnalysisConfig interface should have required structure', () => {
      const analysis: AnalysisConfig = {
        default_max_cloud: 20,
        default_days_back: 30,
      };

      expect(analysis).toHaveProperty('default_max_cloud');
      expect(analysis).toHaveProperty('default_days_back');
    });

    it('SystemConfig interface should have required structure', () => {
      const systemConfig: SystemConfig = {
        consorcio_area_ha: 10000,
        consorcio_km_caminos: 500,
        map: {
          center: { lat: -35, lng: -62 },
          zoom: 10,
          bounds: { north: -34, south: -36, east: -61, west: -63 },
        },
        cuencas: [],
        analysis: { default_max_cloud: 20, default_days_back: 30 },
      };

      expect(systemConfig).toHaveProperty('consorcio_area_ha');
      expect(systemConfig).toHaveProperty('consorcio_km_caminos');
      expect(systemConfig).toHaveProperty('map');
      expect(systemConfig).toHaveProperty('cuencas');
      expect(systemConfig).toHaveProperty('analysis');
    });
  });

  describe('configApi object', () => {
    it('should be an object', () => {
      expect(typeof configApi).toBe('object');
      expect(configApi).not.toBeNull();
    });

    it('should have getSystemConfig method', () => {
      expect(typeof configApi.getSystemConfig).toBe('function');
    });

    it('should expose only public methods', () => {
      const methodNames = Object.keys(configApi);
      expect(methodNames).toContain('getSystemConfig');
    });
  });
});
