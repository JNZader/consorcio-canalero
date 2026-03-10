import { renderHook, act, waitFor } from '@testing-library/react';
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

  // ============================================
  // INITIAL STATE
  // ============================================

  describe('Initial state', () => {
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
  });

  // ============================================
  // NULL JOB ID HANDLING
  // ============================================

  describe('Null jobId handling', () => {
    it('should not poll when jobId is null', () => {
      renderHook(() => useJobStatus(null));

      act(() => {
        vi.advanceTimersByTime(5000);
      });

      expect(mockApiFetch).not.toHaveBeenCalled();
    });

    it('catches mutation: should set status to IDLE when jobId is null', () => {
      const { result } = renderHook(() => useJobStatus(null));
      expect(result.current.status).toBe('IDLE');
    });

    it('catches mutation: should clear result when jobId becomes null', async () => {
      const { result, rerender } = renderHook(
        ({ jobId }: { jobId: string | null }) => useJobStatus(jobId),
        { initialProps: { jobId: 'job-1' } }
      );

      expect(result.current.status).toBe('PENDING');

      // Change to null
      rerender({ jobId: null });

      expect(result.current.result).toBeNull();
      expect(result.current.error).toBeNull();
      expect(result.current.status).toBe('IDLE');
    });

    it('catches mutation: should clear error when jobId becomes null', async () => {
      const { result, rerender } = renderHook(
        ({ jobId }: { jobId: string | null }) => useJobStatus(jobId),
        { initialProps: { jobId: 'job-1' } }
      );

      mockApiFetch.mockRejectedValue(new Error('Test error'));

      act(() => {
        vi.advanceTimersByTime(2000);
      });

      rerender({ jobId: null });

      expect(result.current.error).toBeNull();
    });
  });

  // ============================================
  // POLLING BEHAVIOR
  // ============================================

  describe('Polling behavior', () => {
    it('should set status to PENDING initially when jobId is provided', () => {
      const { result } = renderHook(() => useJobStatus('job-1'));

      expect(result.current.status).toBe('PENDING');
      expect(result.current.isLoading).toBe(true);
    });

    it('catches mutation: should poll every 2 seconds not 1 second', () => {
      mockApiFetch.mockResolvedValue({ job_id: 'job-1', status: 'PENDING' });

      renderHook(() => useJobStatus('job-1'));

      act(() => {
        vi.advanceTimersByTime(1000); // 1 second
      });

      const callCount1 = mockApiFetch.mock.calls.length;

      act(() => {
        vi.advanceTimersByTime(999); // 1.999 seconds total
      });

      const callCount2 = mockApiFetch.mock.calls.length;
      expect(callCount2).toBe(callCount1); // Should NOT have called again yet

      act(() => {
        vi.advanceTimersByTime(1); // 2 seconds total
      });

      expect(mockApiFetch.mock.calls.length).toBeGreaterThan(callCount1);
    });

    it('should poll multiple times when job is still pending', () => {
      mockApiFetch.mockResolvedValue({ job_id: 'job-1', status: 'PENDING' });

      renderHook(() => useJobStatus('job-1'));

      // First interval
      act(() => {
        vi.advanceTimersByTime(2000);
      });

      const callCount1 = mockApiFetch.mock.calls.length;
      expect(callCount1).toBeGreaterThan(0);

      // Second interval
      act(() => {
        vi.advanceTimersByTime(2000);
      });

      const callCount2 = mockApiFetch.mock.calls.length;
      expect(callCount2).toBeGreaterThan(callCount1);

      // Third interval
      act(() => {
        vi.advanceTimersByTime(2000);
      });

      const callCount3 = mockApiFetch.mock.calls.length;
      expect(callCount3).toBeGreaterThan(callCount2);
    });
  });

  // ============================================
  // SUCCESS STATE
  // ============================================

  describe('SUCCESS status handling', () => {
    it('catches mutation: should set isLoading to false on SUCCESS', async () => {
      mockApiFetch.mockResolvedValue({
        job_id: 'job-1',
        status: 'SUCCESS',
        result: 'done',
      });

      const { result } = renderHook(() => useJobStatus('job-1'));

      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000);
      });

      expect(result.current.isLoading).toBe(false);
    });

    it('should call onCompleted callback when SUCCESS with result', async () => {
      const onCompleted = vi.fn();
      mockApiFetch.mockResolvedValue({
        job_id: 'job-1',
        status: 'SUCCESS',
        result: { value: 'test' },
      });

      renderHook(() => useJobStatus('job-1', onCompleted));

      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000);
      });

      expect(onCompleted).toHaveBeenCalledWith({ value: 'test' });
    });

    it('catches mutation: should not call onCompleted if result is undefined', async () => {
      const onCompleted = vi.fn();
      mockApiFetch.mockResolvedValue({
        job_id: 'job-1',
        status: 'SUCCESS',
        result: undefined,
      });

      renderHook(() => useJobStatus('job-1', onCompleted));

      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000);
      });

      expect(onCompleted).not.toHaveBeenCalled();
    });
  });

  // ============================================
  // FAILURE STATE
  // ============================================

  describe('FAILURE status handling', () => {
    it('catches mutation: should set isLoading to false on FAILURE', async () => {
      mockApiFetch.mockResolvedValue({
        job_id: 'job-1',
        status: 'FAILURE',
        error: 'Job failed',
      });

      const { result } = renderHook(() => useJobStatus('job-1'));

      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000);
      });

      expect(result.current.isLoading).toBe(false);
    });

    it('catches mutation: should use fallback error message if error field is missing', async () => {
      mockApiFetch.mockResolvedValue({
        job_id: 'job-1',
        status: 'FAILURE',
      });

      const { result } = renderHook(() => useJobStatus('job-1'));

      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000);
      });

      expect(result.current.error).toBe('Job failed');
    });

    it('should use error message from response', async () => {
      mockApiFetch.mockResolvedValue({
        job_id: 'job-1',
        status: 'FAILURE',
        error: 'Custom error message',
      });

      const { result } = renderHook(() => useJobStatus('job-1'));

      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000);
      });

      expect(result.current.error).toBe('Custom error message');
    });
  });

  // ============================================
  // API ERROR HANDLING
  // ============================================

  describe('API error handling', () => {
    it('should handle API fetch errors', async () => {
      const error = new Error('Network error');
      mockApiFetch.mockRejectedValue(error);

      const { result } = renderHook(() => useJobStatus('job-1'));

      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000);
      });

      expect(result.current.error).toBe('Network error');
      expect(result.current.isLoading).toBe(false);
    });

    it('catches mutation: should extract error message from Error objects', async () => {
      mockApiFetch.mockRejectedValue(new Error('Timeout occurred'));

      const { result } = renderHook(() => useJobStatus('job-1'));

      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000);
      });

      expect(result.current.error).toBe('Timeout occurred');
    });

    it('catches mutation: should use generic message for non-Error exceptions', async () => {
      mockApiFetch.mockRejectedValue('String error');

      const { result } = renderHook(() => useJobStatus('job-1'));

      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000);
      });

      expect(result.current.error).toBe('Error checking job status');
    });
  });

  // ============================================
  // CALLBACK HANDLING
  // ============================================

  describe('Callback handling', () => {
    it('should accept onCompleted callback', () => {
      const callback = vi.fn();

      renderHook(() => useJobStatus(null, callback));

      expect(mockApiFetch).not.toHaveBeenCalled();
    });

    it('should not call onCompleted when status is not SUCCESS', () => {
      const onCompleted = vi.fn();
      mockApiFetch.mockResolvedValue({
        job_id: 'job-1',
        status: 'PENDING',
      });

      renderHook(() => useJobStatus('job-1', onCompleted));

      act(() => {
        vi.advanceTimersByTime(2000);
      });

      expect(onCompleted).not.toHaveBeenCalled();
    });

    it('catches mutation: should pass result to callback only when SUCCESS with result', async () => {
      const onCompleted = vi.fn();
      mockApiFetch.mockResolvedValue({
        job_id: 'job-1',
        status: 'SUCCESS',
        result: { value: 42 },
      });

      renderHook(() => useJobStatus('job-1', onCompleted));

      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000);
      });

      expect(onCompleted).toHaveBeenCalledWith({ value: 42 });
    });
  });

  // ============================================
  // CLEANUP
  // ============================================

  describe('Cleanup', () => {
    it('should clean up on unmount', () => {
      const { unmount } = renderHook(() => useJobStatus(null));

      expect(() => unmount()).not.toThrow();
    });

    it('should clean up interval on unmount when polling', () => {
      mockApiFetch.mockResolvedValue({ job_id: 'job-1', status: 'PENDING' });

      const { unmount } = renderHook(() => useJobStatus('job-1'));

      act(() => {
        vi.advanceTimersByTime(2000);
      });

      const callCount = mockApiFetch.mock.calls.length;

      unmount();

      act(() => {
        vi.advanceTimersByTime(2000);
      });

      // Should not have called again after unmount
      expect(mockApiFetch.mock.calls.length).toBe(callCount);
    });

    it('catches mutation: should clear all state values on jobId change to null', () => {
      const { result, rerender } = renderHook(
        ({ jobId }: { jobId: string | null }) => useJobStatus(jobId),
        { initialProps: { jobId: 'job-1' } }
      );

      expect(result.current.status).toBe('PENDING');
      expect(result.current.isLoading).toBe(true);

      rerender({ jobId: null });

      expect(result.current.status).toBe('IDLE');
      expect(result.current.result).toBeNull();
      expect(result.current.error).toBeNull();
      expect(result.current.isLoading).toBe(false);
    });
  });

  // ============================================
  // JOB ID CHANGES
  // ============================================

  describe('Job ID changes', () => {
    it('catches mutation: should reset state when jobId changes', () => {
      const { result, rerender } = renderHook(
        ({ jobId }: { jobId: string | null }) => useJobStatus(jobId),
        { initialProps: { jobId: 'job-1' } }
      );

      expect(result.current.status).toBe('PENDING');

      mockApiFetch.mockResolvedValue({ job_id: 'job-2', status: 'PENDING' });

      rerender({ jobId: 'job-2' });

      expect(result.current.status).toBe('PENDING');
      expect(result.current.isLoading).toBe(true);
      expect(result.current.result).toBeNull();
      expect(result.current.error).toBeNull();
    });

    it('should start fresh polling for new jobId', () => {
      mockApiFetch.mockResolvedValue({ job_id: 'job-1', status: 'PENDING' });

      const { rerender } = renderHook(
        ({ jobId }: { jobId: string | null }) => useJobStatus(jobId),
        { initialProps: { jobId: 'job-1' } }
      );

      act(() => {
        vi.advanceTimersByTime(2000);
      });

      mockApiFetch.mockClear();
      mockApiFetch.mockResolvedValue({ job_id: 'job-2', status: 'PENDING' });

      rerender({ jobId: 'job-2' });

      act(() => {
        vi.advanceTimersByTime(2000);
      });

      // Should have called for job-2
      const lastCall = mockApiFetch.mock.calls[mockApiFetch.mock.calls.length - 1];
      expect(lastCall?.[0]).toContain('job-2');
    });

    it('catches mutation: should call apiFetch with correct job ID in path', () => {
      mockApiFetch.mockResolvedValue({ job_id: 'custom-job-123', status: 'PENDING' });

      renderHook(() => useJobStatus('custom-job-123'));

      act(() => {
        vi.advanceTimersByTime(2000);
      });

      const hasCalled = mockApiFetch.mock.calls.some((call) =>
        String(call[0]).includes('custom-job-123')
      );
      expect(hasCalled).toBe(true);
    });
  });
});
