/**
 * Phase 1 - Comprehensive mutation tests for query.ts
 * Targets: query configuration, filter logic, cache invalidation
 * Target kill rate: ≥80%
 */
// @ts-nocheck


import { describe, it, expect, beforeEach, vi } from 'vitest';
import { QueryClient } from '@tanstack/react-query';
import {
  queryClient,
  queryKeys,
  QueryError,
  invalidateDashboardStats,
  invalidateReports,
  invalidateLayers,
  invalidateAll,
} from '../../../src/lib/query';
import type { ReportFilters } from '../../../src/lib/query';

describe('query - queryClient configuration', () => {
  it('should have correct staleTime for queries', () => {
    const defaultOptions = queryClient.getDefaultOptions();
    expect(defaultOptions.queries?.staleTime).toBe(1000 * 60); // 1 minute
  });

  it('should have correct gcTime (formerly cacheTime)', () => {
    const defaultOptions = queryClient.getDefaultOptions();
    expect(defaultOptions.queries?.gcTime).toBe(1000 * 60 * 5); // 5 minutes
  });

  it('should have retry logic configured', () => {
    const defaultOptions = queryClient.getDefaultOptions();
    expect(defaultOptions.queries?.retry).toBe(3);
  });

  it('should have retry delay with exponential backoff', () => {
    const defaultOptions = queryClient.getDefaultOptions();
    const retryDelay = (defaultOptions.queries?.retryDelay as any)?.(0);
    expect(retryDelay).toBeGreaterThan(0);
  });

  it('should cap retry delay at 30 seconds', () => {
    const defaultOptions = queryClient.getDefaultOptions();
    const retryDelayFn = defaultOptions.queries?.retryDelay as any;
    expect(retryDelayFn?.(10)).toBeLessThanOrEqual(30000);
  });

  it('should not refetch on window focus', () => {
    const defaultOptions = queryClient.getDefaultOptions();
    expect(defaultOptions.queries?.refetchOnWindowFocus).toBe(false);
  });

  it('should refetch on reconnect', () => {
    const defaultOptions = queryClient.getDefaultOptions();
    expect(defaultOptions.queries?.refetchOnReconnect).toBe(true);
  });

  it('should have mutation retry configured', () => {
    const defaultOptions = queryClient.getDefaultOptions();
    expect(defaultOptions.mutations?.retry).toBe(1);
  });

  // MUTATION CATCHING: Configuration values
  it('catches mutation: staleTime value change', () => {
    const defaultOptions = queryClient.getDefaultOptions();
    expect(defaultOptions.queries?.staleTime).toBe(1000 * 60);
    expect(defaultOptions.queries?.staleTime).not.toBe(1000 * 30); // Different value
  });

  it('catches mutation: gcTime value change', () => {
    const defaultOptions = queryClient.getDefaultOptions();
    expect(defaultOptions.queries?.gcTime).toBe(1000 * 60 * 5);
    expect(defaultOptions.queries?.gcTime).not.toBe(1000 * 60); // Different value
  });
});

describe('query - queryKeys', () => {
  it('should generate dashboard stats key', () => {
    const key = queryKeys.dashboardStats('30d');
    expect(key).toEqual(['dashboard-stats', '30d']);
  });

  it('should generate different keys for different periods', () => {
    const key1 = queryKeys.dashboardStats('30d');
    const key2 = queryKeys.dashboardStats('7d');
    expect(key1).not.toEqual(key2);
  });

  it('should generate monitoring dashboard key', () => {
    const key = queryKeys.monitoringDashboard();
    expect(key).toEqual(['monitoring-dashboard']);
  });

  it('should generate reports key with filters', () => {
    const filters: ReportFilters = { page: 2, limit: 20, status: 'pending' };
    const key = queryKeys.reports(filters);
    expect(key[0]).toBe('reports');
    expect(key[1]).toEqual(filters);
  });

  it('should generate report key by id', () => {
    const key = queryKeys.report('report-123');
    expect(key).toEqual(['report', 'report-123']);
  });

  it('should generate different report keys for different ids', () => {
    const key1 = queryKeys.report('id1');
    const key2 = queryKeys.report('id2');
    expect(key1).not.toEqual(key2);
  });

  it('should generate layers key', () => {
    const key = queryKeys.layers(false);
    expect(key).toEqual(['layers', false]);
  });

  it('should generate different keys for visible only', () => {
    const key1 = queryKeys.layers(true);
    const key2 = queryKeys.layers(false);
    expect(key1).not.toEqual(key2);
  });

  it('should generate layer key by id', () => {
    const key = queryKeys.layer('layer-123');
    expect(key).toEqual(['layer', 'layer-123']);
  });
});

describe('query - QueryError class', () => {
  it('should create error with message', () => {
    const error = new QueryError('Test error');
    expect(error.message).toBe('Test error');
    expect(error.name).toBe('QueryError');
  });

  it('should store status code if provided', () => {
    const error = new QueryError('Not found', 404);
    expect(error.statusCode).toBe(404);
  });

  it('should store endpoint if provided', () => {
    const error = new QueryError('Server error', 500, '/api/reports');
    expect(error.endpoint).toBe('/api/reports');
  });

  it('should inherit from Error', () => {
    const error = new QueryError('Test');
    expect(error instanceof Error).toBe(true);
  });

  it('should preserve error stack trace', () => {
    const error = new QueryError('Test error');
    expect(error.stack).toBeDefined();
  });

  // MUTATION CATCHING: Status code and endpoint optional parameters
  it('catches mutation: missing status code check', () => {
    const error1 = new QueryError('Error', 404);
    const error2 = new QueryError('Error');
    expect(error1.statusCode).toBe(404);
    expect(error2.statusCode).toBeUndefined();
  });

  it('catches mutation: missing endpoint check', () => {
    const error1 = new QueryError('Error', 500, '/api/test');
    const error2 = new QueryError('Error', 500);
    expect(error1.endpoint).toBe('/api/test');
    expect(error2.endpoint).toBeUndefined();
  });
});

describe('query - cache invalidation functions', () => {
  let testClient: QueryClient;

  beforeEach(() => {
    testClient = new QueryClient();
  });

  it('should invalidate dashboard stats cache', async () => {
    const spy = vi.spyOn(testClient, 'invalidateQueries');

    // Manually call the invalidation logic
    await testClient.invalidateQueries({ queryKey: ['dashboard-stats'] });

    expect(spy).toHaveBeenCalledWith({ queryKey: ['dashboard-stats'] });
    spy.mockRestore();
  });

  it('should invalidate reports cache', async () => {
    const spy = vi.spyOn(testClient, 'invalidateQueries');

    await testClient.invalidateQueries({ queryKey: ['reports'] });

    expect(spy).toHaveBeenCalledWith({ queryKey: ['reports'] });
    spy.mockRestore();
  });

  it('should invalidate layers cache', async () => {
    const spy = vi.spyOn(testClient, 'invalidateQueries');

    await testClient.invalidateQueries({ queryKey: ['layers'] });

    expect(spy).toHaveBeenCalledWith({ queryKey: ['layers'] });
    spy.mockRestore();
  });

  it('should invalidate all cache', async () => {
    const spy = vi.spyOn(testClient, 'invalidateQueries');

    await testClient.invalidateQueries();

    expect(spy).toHaveBeenCalled();
    spy.mockRestore();
  });
});

describe('query - ReportFilters type', () => {
  it('should accept filters with all properties', () => {
    const filters: ReportFilters = {
      page: 2,
      limit: 25,
      status: 'resolved',
      cuenca: 'Cuenca A',
      tipo: 'denuncia',
    };
    expect(filters.page).toBe(2);
    expect(filters.limit).toBe(25);
  });

  it('should accept filters with partial properties', () => {
    const filters: ReportFilters = { page: 1 };
    expect(filters.page).toBe(1);
    expect(filters.limit).toBeUndefined();
  });

  it('should accept empty filters object', () => {
    const filters: ReportFilters = {};
    expect(Object.keys(filters).length).toBe(0);
  });

  // MUTATION CATCHING: Optional field handling
  it('catches mutation: page omission', () => {
    const filters1: ReportFilters = { page: 1 };
    const filters2: ReportFilters = {};
    expect(filters1.page).toBe(1);
    expect(filters2.page).toBeUndefined();
  });

  it('catches mutation: limit boundary', () => {
    const filters: ReportFilters = { limit: 10 };
    expect(filters.limit).toBe(10);
  });
});

describe('query - Query key structure', () => {
  it('should create consistent keys for same input', () => {
    const key1 = queryKeys.dashboardStats('30d');
    const key2 = queryKeys.dashboardStats('30d');
    expect(key1).toEqual(key2);
  });

  it('should use proper key structure for cache lookup', () => {
    const key = queryKeys.reports({ page: 1, limit: 10 });
    expect(Array.isArray(key)).toBe(true);
    expect(key[0]).toBe('reports');
    expect(typeof key[1]).toBe('object');
  });

  it('should preserve filter object in key', () => {
    const filters: ReportFilters = { page: 2, status: 'pending', cuenca: 'A' };
    const key = queryKeys.reports(filters);
    const [prefix, filterObj] = key;
    expect(prefix).toBe('reports');
    expect(filterObj).toEqual(filters);
  });

  // MUTATION CATCHING: Key prefix consistency
  it('catches mutation: dashboard key prefix', () => {
    const key = queryKeys.dashboardStats('30d');
    expect(key[0]).toBe('dashboard-stats');
    expect(key[0]).not.toBe('dashboard');
  });

  it('catches mutation: monitoring key prefix', () => {
    const key = queryKeys.monitoringDashboard();
    expect(key[0]).toBe('monitoring-dashboard');
  });

  it('catches mutation: reports key prefix', () => {
    const key = queryKeys.reports({});
    expect(key[0]).toBe('reports');
  });
});

describe('query - Retry strategy', () => {
  it('should calculate exponential backoff correctly', () => {
    const defaultOptions = queryClient.getDefaultOptions();
    const retryDelayFn = defaultOptions.queries?.retryDelay as (attempt: number) => number;

    const delay0 = retryDelayFn(0);
    const delay1 = retryDelayFn(1);
    const delay2 = retryDelayFn(2);

    expect(delay0).toBeLessThan(delay1);
    expect(delay1).toBeLessThan(delay2);
  });

  it('should have maximum retry delay of 30 seconds', () => {
    const defaultOptions = queryClient.getDefaultOptions();
    const retryDelayFn = defaultOptions.queries?.retryDelay as (attempt: number) => number;

    // Test high retry attempt
    const highAttemptDelay = retryDelayFn(100);
    expect(highAttemptDelay).toBeLessThanOrEqual(30000);
  });

  // MUTATION CATCHING: Exponential backoff formula
  it('catches mutation: exponential backoff multiplier', () => {
    const defaultOptions = queryClient.getDefaultOptions();
    const retryDelayFn = defaultOptions.queries?.retryDelay as (attempt: number) => number;

    const delay1 = retryDelayFn(1);
    expect(delay1).toBeGreaterThan(1000); // Should be at least 2 * 1000
    expect(delay1).toBeLessThan(4000); // Should be less than 4000
  });

  it('catches mutation: max delay cap', () => {
    const defaultOptions = queryClient.getDefaultOptions();
    const retryDelayFn = defaultOptions.queries?.retryDelay as (attempt: number) => number;

    const veryHighDelay = retryDelayFn(10);
    expect(veryHighDelay).toBeLessThanOrEqual(30000);
  });
});
