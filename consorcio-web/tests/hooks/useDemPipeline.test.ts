import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { submitMock, getJobMock, getLayersMock, getBasinsMock } = vi.hoisted(() => ({
  submitMock: vi.fn(),
  getJobMock: vi.fn(),
  getLayersMock: vi.fn(),
  getBasinsMock: vi.fn(),
}));

vi.mock('../../src/lib/api/demPipeline', () => ({
  demPipelineApi: {
    submit: submitMock,
    getJob: getJobMock,
    getLayers: getLayersMock,
    getBasins: getBasinsMock,
  },
}));

vi.mock('../../src/lib/notifications', () => ({
  showError: vi.fn(),
  showInfo: vi.fn(),
  showSuccess: vi.fn(),
}));

vi.mock('../../src/lib/logger', () => ({
  logger: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
}));

import { useDemPipeline } from '../../src/hooks/useDemPipeline';

describe('useDemPipeline polling lifecycle', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    getLayersMock.mockResolvedValue({ items: [] });
    getBasinsMock.mockResolvedValue({ type: 'FeatureCollection', features: [] });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('stops the previous polling interval when submit is called twice', async () => {
    submitMock
      .mockResolvedValueOnce({ job_id: 'job-1', tipo: 'dem', estado: 'queued' })
      .mockResolvedValueOnce({ job_id: 'job-2', tipo: 'dem', estado: 'queued' });
    getJobMock.mockResolvedValue({
      id: 'job-2',
      tipo: 'dem',
      estado: 'running',
      progreso: 35,
      parametros: null,
      resultado: null,
      error: null,
      celery_task_id: null,
      created_at: '',
      updated_at: '',
    });

    const { result } = renderHook(() => useDemPipeline());

    await act(async () => {
      await result.current.submit('area-1');
    });
    await act(async () => {
      await result.current.submit('area-2');
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });

    // Only job-2 should have been polled once (not both job-1 and job-2)
    expect(getJobMock).toHaveBeenCalledTimes(1);
    expect(getJobMock).toHaveBeenCalledWith(
      'job-2',
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    );
  });

  it('clears the polling interval and aborts in-flight poll requests on unmount', async () => {
    submitMock.mockResolvedValueOnce({ job_id: 'job-1', tipo: 'dem', estado: 'queued' });
    let capturedSignal: AbortSignal | undefined;
    getJobMock.mockImplementation((_id: string, opts?: { signal?: AbortSignal }) => {
      capturedSignal = opts?.signal;
      return new Promise(() => {});
    });

    const { result, unmount } = renderHook(() => useDemPipeline());

    await act(async () => {
      await result.current.submit('area-1');
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });

    expect(capturedSignal).toBeInstanceOf(AbortSignal);
    expect(capturedSignal?.aborted).toBe(false);

    unmount();

    expect(capturedSignal?.aborted).toBe(true);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(15000);
    });
    expect(getJobMock).toHaveBeenCalledTimes(1);
  });
});
