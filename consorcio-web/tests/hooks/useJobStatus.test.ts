import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { mockApiFetch } = vi.hoisted(() => ({
  mockApiFetch: vi.fn(),
}));

vi.mock('../../src/lib/api', () => ({
  apiFetch: mockApiFetch,
}));

import { useJobStatus } from '../../src/hooks/useJobStatus';

async function advancePolling(ms = 2000) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe('useJobStatus', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it('stays idle when jobId is null', async () => {
    const { result } = renderHook(() => useJobStatus(null));

    expect(result.current).toEqual({
      status: 'IDLE',
      result: null,
      error: null,
      isLoading: false,
    });

    await advancePolling(10000);

    expect(mockApiFetch).not.toHaveBeenCalled();
  });

  it('starts pending and polls the job endpoint every 2 seconds', async () => {
    mockApiFetch.mockResolvedValue({ job_id: 'job-1', status: 'PENDING' });

    const { result } = renderHook(() => useJobStatus('job-1'));

    expect(result.current.status).toBe('PENDING');
    expect(result.current.isLoading).toBe(true);
    expect(mockApiFetch).not.toHaveBeenCalled();

    await advancePolling(1999);
    expect(mockApiFetch).not.toHaveBeenCalled();

    await advancePolling(1);
    expect(mockApiFetch).toHaveBeenCalledWith('/geo/jobs/job-1');
    expect(result.current.status).toBe('PENDING');

    await advancePolling(2000);
    expect(mockApiFetch).toHaveBeenCalledTimes(2);
  });

  it('stores the result and calls onCompleted once when the job succeeds', async () => {
    vi.useRealTimers();
    const onCompleted = vi.fn();
    const completedResult = { url: '/tiles/final' };

    mockApiFetch.mockResolvedValue({
      job_id: 'job-1',
      status: 'SUCCESS',
      result: completedResult,
    });

    const { result } = renderHook(() => useJobStatus('job-1', onCompleted));

    await waitFor(() => expect(onCompleted).toHaveBeenCalledWith(completedResult), { timeout: 2500 });

    expect(result.current.result).toEqual(completedResult);
    expect(result.current.error).toBeNull();
    expect(onCompleted).toHaveBeenCalledTimes(1);
  }, 5000);

  it('stores response errors for failed jobs and stops loading', async () => {
    vi.useRealTimers();
    mockApiFetch.mockResolvedValue({
      job_id: 'job-1',
      status: 'FAILURE',
      error: 'Processing failed',
    });

    const { result } = renderHook(() => useJobStatus('job-1'));

    await waitFor(() => expect(result.current.error).toBe('Processing failed'), { timeout: 2500 });

    expect(result.current.result).toBeNull();
  }, 5000);

  it('falls back to "Job failed" when a failed response has no message', async () => {
    vi.useRealTimers();
    mockApiFetch.mockResolvedValue({
      job_id: 'job-1',
      status: 'FAILURE',
    });

    const { result } = renderHook(() => useJobStatus('job-1'));

    await waitFor(() => expect(result.current.error).toBe('Job failed'), { timeout: 2500 });
  }, 5000);

  it('surfaces thrown Error messages from the polling request', async () => {
    mockApiFetch.mockRejectedValue(new Error('Network timeout'));

    const { result } = renderHook(() => useJobStatus('job-1'));

    await advancePolling();

    expect(result.current.status).toBe('PENDING');
    expect(result.current.result).toBeNull();
    expect(result.current.error).toBe('Network timeout');
    expect(result.current.isLoading).toBe(false);
  });

  it('uses a generic message for non-Error thrown values', async () => {
    mockApiFetch.mockRejectedValue('boom');

    const { result } = renderHook(() => useJobStatus('job-1'));

    await advancePolling();

    expect(result.current.error).toBe('Error checking job status');
    expect(result.current.isLoading).toBe(false);
  });

  it('resets state when jobId becomes null', async () => {
    mockApiFetch.mockRejectedValue(new Error('Temporary failure'));

    const { result, rerender } = renderHook(
      ({ jobId }: { jobId: string | null }) => useJobStatus(jobId),
      { initialProps: { jobId: 'job-1' } }
    );

    await advancePolling();
    expect(result.current.error).toBe('Temporary failure');

    rerender({ jobId: null });

    expect(result.current).toEqual({
      status: 'IDLE',
      result: null,
      error: null,
      isLoading: false,
    });
  });

  it('starts fresh polling when the jobId changes', async () => {
    mockApiFetch.mockResolvedValue({ job_id: 'job-1', status: 'PENDING' });

    const { result, rerender } = renderHook(
      ({ jobId }: { jobId: string | null }) => useJobStatus(jobId),
      { initialProps: { jobId: 'job-1' } }
    );

    await advancePolling();
    expect(mockApiFetch).toHaveBeenLastCalledWith('/geo/jobs/job-1');

    mockApiFetch.mockClear();
    mockApiFetch.mockResolvedValue({ job_id: 'job-2', status: 'STARTED' });

    rerender({ jobId: 'job-2' });

    expect(result.current.status).toBe('PENDING');
    expect(result.current.result).toBeNull();
    expect(result.current.error).toBeNull();
    expect(result.current.isLoading).toBe(true);

    await advancePolling();

    expect(mockApiFetch).toHaveBeenCalledTimes(1);
    expect(mockApiFetch).toHaveBeenLastCalledWith('/geo/jobs/job-2');
  });
});
