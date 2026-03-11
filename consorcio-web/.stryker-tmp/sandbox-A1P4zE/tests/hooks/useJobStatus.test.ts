// @ts-nocheck
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
  });

  afterEach(() => {
    vi.clearAllMocks();
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
      vi.useFakeTimers();
      try {
        renderHook(() => useJobStatus(null));

        act(() => {
          vi.advanceTimersByTime(5000);
        });

        expect(mockApiFetch).not.toHaveBeenCalled();
      } finally {
        vi.useRealTimers();
      }
    });

    it('catches mutation: should set status to IDLE when jobId is null', () => {
      const { result } = renderHook(() => useJobStatus(null));
      expect(result.current.status).toBe('IDLE');
    });

    it('catches mutation: should clear result when jobId becomes null', () => {
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

    it('catches mutation: should clear error when jobId becomes null', () => {
      const { result, rerender } = renderHook(
        ({ jobId }: { jobId: string | null }) => useJobStatus(jobId),
        { initialProps: { jobId: 'job-1' } }
      );

      mockApiFetch.mockRejectedValue(new Error('Test error'));

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
      vi.useFakeTimers();
      try {
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
      } finally {
        vi.useRealTimers();
      }
    });

    it('should poll multiple times when job is still pending', () => {
      vi.useFakeTimers();
      try {
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
      } finally {
        vi.useRealTimers();
      }
    });
  });

  // ============================================
  // PARAMETRIZED STATUS TESTS
  // ============================================

  describe('Parametrized status flow tests', () => {
    it('catches mutation: should exactly match PENDING status string', async () => {
      mockApiFetch.mockResolvedValue({
        job_id: 'job-1',
        status: 'PENDING',
      });

      const { result } = renderHook(() => useJobStatus('job-1'));

      expect(result.current.status).toBe('PENDING');
      expect(result.current.status).not.toBe('STARTED');
    }, 15000);



    it('catches mutation: should verify polling interval is 2 seconds between calls', () => {
      vi.useFakeTimers();
      try {
        mockApiFetch.mockResolvedValue({ job_id: 'job-1', status: 'PENDING' });

        renderHook(() => useJobStatus('job-1'));

        // Advance 1999ms - should not call yet
        act(() => {
          vi.advanceTimersByTime(1999);
        });
        const callsBefore2s = mockApiFetch.mock.calls.length;

        // Advance to 2s total - should call
        act(() => {
          vi.advanceTimersByTime(1);
        });
        const callsAt2s = mockApiFetch.mock.calls.length;
        expect(callsAt2s).toBeGreaterThan(callsBefore2s);
      } finally {
        vi.useRealTimers();
      }
    });
  });

  // ============================================
  // SUCCESS STATE
  // ============================================

  describe('SUCCESS status handling', () => {
    it('catches mutation: should call onCompleted callback with exact result value', async () => {
      const testResult = { id: 'test-123', value: 42 };
      const onCompleted = vi.fn();
      mockApiFetch.mockResolvedValue({
        job_id: 'job-1',
        status: 'SUCCESS',
        result: testResult,
      });

      renderHook(() => useJobStatus('job-1', onCompleted));

      // Wait for the callback to be called
      await waitFor(() => {
        expect(onCompleted).toHaveBeenCalledWith(testResult);
        expect(onCompleted).toHaveBeenCalledTimes(1);
      }, { timeout: 5000 });
    }, 15000);

    it('catches mutation: should store result in hook state when SUCCESS', async () => {
      const testResult = { id: 'test-123', value: 42 };
      mockApiFetch.mockResolvedValue({
        job_id: 'job-1',
        status: 'SUCCESS',
        result: testResult,
      });

      const { result } = renderHook(() => useJobStatus('job-1'));

      await waitFor(() => {
        expect(result.current.result).toEqual(testResult);
        expect(result.current.result).not.toBeNull();
      }, { timeout: 5000 });
    }, 15000);

    it('should call onCompleted callback when SUCCESS with result', async () => {
      const onCompleted = vi.fn();
      mockApiFetch.mockResolvedValue({
        job_id: 'job-1',
        status: 'SUCCESS',
        result: { value: 'test' },
      });

      renderHook(() => useJobStatus('job-1', onCompleted));

      await waitFor(() => {
        expect(onCompleted).toHaveBeenCalledWith({ value: 'test' });
      }, { timeout: 5000 });
    }, 15000);

    it('catches mutation: should not call onCompleted if result is undefined', async () => {
      const onCompleted = vi.fn();
      mockApiFetch.mockResolvedValue({
        job_id: 'job-1',
        status: 'SUCCESS',
        result: undefined,
      });

      renderHook(() => useJobStatus('job-1', onCompleted));

      // Wait a bit to ensure the callback doesn't get called
      await new Promise(resolve => setTimeout(resolve, 2500));

      expect(onCompleted).not.toHaveBeenCalled();
    }, 15000);

    it('catches mutation: should clear error when transitioning to SUCCESS', async () => {
      mockApiFetch.mockResolvedValue({
        job_id: 'job-1',
        status: 'SUCCESS',
        result: { value: 'test' },
      });

      const { result } = renderHook(() => useJobStatus('job-1'));

      await waitFor(() => {
        expect(result.current.error).toBeNull();
      }, { timeout: 5000 });
    }, 15000);
  });

  // ============================================
  // FAILURE STATUS
  // ============================================

  describe('FAILURE status handling', () => {
    it('catches mutation: should use fallback error message if error field is missing', async () => {
      mockApiFetch.mockResolvedValue({
        job_id: 'job-1',
        status: 'FAILURE',
      });

      const { result } = renderHook(() => useJobStatus('job-1'));

      // Wait for the fallback error message to be set
      await waitFor(() => {
        expect(result.current.error).toBe('Job failed');
        expect(result.current.error).not.toBeNull();
      }, { timeout: 5000 });
    }, 15000);

    it('should use error message from response', async () => {
      mockApiFetch.mockResolvedValue({
        job_id: 'job-1',
        status: 'FAILURE',
        error: 'Custom error message',
      });

      const { result } = renderHook(() => useJobStatus('job-1'));

      // Wait for the error message to be set
      await waitFor(() => {
        expect(result.current.error).toBe('Custom error message');
        expect(result.current.error).not.toBe('Job failed');
      }, { timeout: 5000 });
    }, 15000);

    it('catches mutation: should clear result when transitioning to FAILURE', async () => {
      mockApiFetch.mockResolvedValue({
        job_id: 'job-1',
        status: 'FAILURE',
        error: 'Job failed',
      });

      const { result } = renderHook(() => useJobStatus('job-1'));

      await waitFor(() => {
        expect(result.current.result).toBeNull();
      }, { timeout: 5000 });
    }, 15000);

    it('catches mutation: should not call onCompleted callback when FAILURE status', async () => {
      const onCompleted = vi.fn();
      mockApiFetch.mockResolvedValue({
        job_id: 'job-1',
        status: 'FAILURE',
        error: 'Job failed',
      });

      renderHook(() => useJobStatus('job-1', onCompleted));

      await new Promise(resolve => setTimeout(resolve, 2500));

      expect(onCompleted).not.toHaveBeenCalled();
    }, 15000);
  });

  // ============================================
  // API ERROR HANDLING
  // ============================================

  describe('API error handling', () => {
    it('should handle API fetch errors', async () => {
      const error = new Error('Network error');
      mockApiFetch.mockRejectedValue(error);

      const { result } = renderHook(() => useJobStatus('job-1'));

      // Wait for the error to be set (may take up to 2.5 seconds for interval)
      await waitFor(
        () => {
          expect(result.current.error).toBe('Network error');
        },
        { timeout: 5000 }
      );

      expect(result.current.isLoading).toBe(false);
    }, 10000);

    it('catches mutation: should extract error message from Error objects', async () => {
      mockApiFetch.mockRejectedValue(new Error('Timeout occurred'));

      const { result } = renderHook(() => useJobStatus('job-1'));

      // Wait for the error to be set
      await waitFor(
        () => {
          expect(result.current.error).toBe('Timeout occurred');
        },
        { timeout: 5000 }
      );
    }, 10000);

    it('catches mutation: should use generic message for non-Error exceptions', async () => {
      mockApiFetch.mockRejectedValue('String error');

      const { result } = renderHook(() => useJobStatus('job-1'));

      // Wait for the generic error message
      await waitFor(
        () => {
          expect(result.current.error).toBe('Error checking job status');
        },
        { timeout: 5000 }
      );
    }, 10000);
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

    it('should not call onCompleted when status is not SUCCESS', async () => {
      const onCompleted = vi.fn();
      mockApiFetch.mockResolvedValue({
        job_id: 'job-1',
        status: 'PENDING',
      });

      renderHook(() => useJobStatus('job-1', onCompleted));

      // Wait for the first polling call
      await waitFor(
        () => {
          expect(mockApiFetch).toHaveBeenCalled();
        },
        { timeout: 5000 }
      );

      expect(onCompleted).not.toHaveBeenCalled();
    }, 10000);

    it('catches mutation: should pass result to callback only when SUCCESS with result', async () => {
      const onCompleted = vi.fn();
      mockApiFetch.mockResolvedValue({
        job_id: 'job-1',
        status: 'SUCCESS',
        result: { value: 42 },
      });

      renderHook(() => useJobStatus('job-1', onCompleted));

      // Wait for the callback to be invoked (may take up to 2.5 seconds for interval)
      await waitFor(() => {
        expect(onCompleted).toHaveBeenCalledWith({ value: 42 });
      }, { timeout: 5000 });
    }, 10000);
  });

  // ============================================
  // CLEANUP
  // ============================================

  describe('Cleanup', () => {
    it('should clean up on unmount', () => {
      const { unmount } = renderHook(() => useJobStatus(null));

      expect(() => unmount()).not.toThrow();
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
      vi.useFakeTimers();
      try {
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
      } finally {
        vi.useRealTimers();
      }
    });

    it('catches mutation: should call apiFetch with correct job ID in path', () => {
      vi.useFakeTimers();
      try {
        mockApiFetch.mockResolvedValue({ job_id: 'custom-job-123', status: 'PENDING' });

        renderHook(() => useJobStatus('custom-job-123'));

        act(() => {
          vi.advanceTimersByTime(2000);
        });

        const hasCalled = mockApiFetch.mock.calls.some((call) =>
          String(call[0]).includes('custom-job-123')
        );
        expect(hasCalled).toBe(true);
      } finally {
        vi.useRealTimers();
      }
    });
  });
});
