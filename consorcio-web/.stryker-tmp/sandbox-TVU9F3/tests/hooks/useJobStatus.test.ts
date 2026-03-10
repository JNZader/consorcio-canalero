// @ts-nocheck
import { renderHook, act } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// Use hoisted pattern for mocks
const { mockApiFetch } = vi.hoisted(() => ({
  mockApiFetch: vi.fn(),
}));

vi.mock('../../src/lib/api', () => ({
  apiFetch: mockApiFetch,
}));

import { useJobStatus } from '../../src/hooks/useJobStatus';

describe('useJobStatus', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('should initialize with null jobId', () => {
    const { result } = renderHook(() => useJobStatus(null));

    expect(result.current.status).toBe('IDLE');
    expect(result.current.isLoading).toBe(false);
    expect(result.current.result).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it('should return proper hook interface', () => {
    const { result } = renderHook(() => useJobStatus(null));

    expect(result.current).toHaveProperty('status');
    expect(result.current).toHaveProperty('isLoading');
    expect(result.current).toHaveProperty('result');
    expect(result.current).toHaveProperty('error');
  });

  it('should handle generic typing with result parameter', () => {
    interface TestResult {
      value: string;
    }

    const { result } = renderHook(() => useJobStatus<TestResult>(null));

    expect(result.current.result).toBeNull();
  });

  it('should not poll when jobId is null', () => {
    renderHook(() => useJobStatus(null));

    act(() => {
      vi.advanceTimersByTime(5000);
    });

    expect(mockApiFetch).not.toHaveBeenCalled();
  });

  it('should accept onCompleted callback', () => {
    const callback = vi.fn();

    renderHook(() => useJobStatus(null, callback));

    expect(mockApiFetch).not.toHaveBeenCalled();
  });

  it('should clean up on unmount', () => {
    const { unmount } = renderHook(() => useJobStatus(null));

    expect(() => unmount()).not.toThrow();
  });
});
