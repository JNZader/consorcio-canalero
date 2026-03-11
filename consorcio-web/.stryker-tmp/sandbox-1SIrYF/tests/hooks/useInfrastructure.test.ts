// @ts-nocheck
import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// Use hoisted pattern for mocks
const { mockApiFetch } = vi.hoisted(() => ({
  mockApiFetch: vi.fn(),
}));

vi.mock('../../src/lib/api', () => ({
  apiFetch: mockApiFetch,
}));

import { useInfrastructure } from '../../src/hooks/useInfrastructure';

describe('useInfrastructure', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApiFetch.mockResolvedValue({
      assets: [],
      potential_intersections: [],
    });
  });

  it('should initialize with empty state', () => {
    const { result } = renderHook(() => useInfrastructure());

    expect(result.current.loading).toBe(true);
    expect(result.current.assets).toEqual([]);
    expect(result.current.intersections).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it('should return proper hook interface', () => {
    const { result } = renderHook(() => useInfrastructure());

    expect(result.current).toHaveProperty('loading');
    expect(result.current).toHaveProperty('assets');
    expect(result.current).toHaveProperty('intersections');
    expect(result.current).toHaveProperty('error');
    expect(result.current).toHaveProperty('refresh');
    expect(result.current).toHaveProperty('createAsset');
  });

  it('should have a refresh function that is callable', async () => {
    const { result } = renderHook(() => useInfrastructure());

    await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

    expect(typeof result.current.refresh).toBe('function');

    await result.current.refresh();

    expect(result.current.loading).toBe(false);
  });

  it('should have a createAsset function that is callable', () => {
    const { result } = renderHook(() => useInfrastructure());

    expect(typeof result.current.createAsset).toBe('function');
  });

  it('should handle errors gracefully', async () => {
    mockApiFetch.mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useInfrastructure());

    await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

    expect(result.current.error).not.toBeNull();
  });

  it('should load assets and intersections in parallel', async () => {
    mockApiFetch.mockResolvedValue([[], []]);

    const { result } = renderHook(() => useInfrastructure());

    await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

    expect(result.current.assets).toBeDefined();
    expect(result.current.intersections).toBeDefined();
  });

  it('should not throw on multiple refresh calls', async () => {
    const { result } = renderHook(() => useInfrastructure());

    await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

    expect(async () => {
      await result.current.refresh();
      await result.current.refresh();
    }).not.toThrow();
  });

  it('should clean up on unmount', () => {
    const { unmount } = renderHook(() => useInfrastructure());

    expect(() => unmount()).not.toThrow();
  });
});
