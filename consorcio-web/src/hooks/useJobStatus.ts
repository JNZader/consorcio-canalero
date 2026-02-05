import { useState, useEffect, useCallback } from 'react';
import { apiFetch } from '../lib/api';

export type JobStatus = 'PENDING' | 'STARTED' | 'SUCCESS' | 'FAILURE' | 'RETRY' | 'REVOKED';

interface JobResponse<T> {
  job_id: string;
  status: JobStatus;
  result?: T;
  error?: string;
}

/**
 * Hook to track the status of a background job with automatic polling.
 */
export function useJobStatus<T>(jobId: string | null, onCompleted?: (result: T) => void) {
  const [status, setStatus] = useState<JobStatus | 'IDLE'>('IDLE');
  const [result, setResult] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const checkStatus = useCallback(async () => {
    if (!jobId) return;

    try {
      const data = await apiFetch<JobResponse<T>>(`/jobs/${jobId}`);
      setStatus(data.status);

      if (data.status === 'SUCCESS' && data.result) {
        setResult(data.result);
        setIsLoading(false);
        if (onCompleted) onCompleted(data.result);
      } else if (data.status === 'FAILURE') {
        setError(data.error || 'Job failed');
        setIsLoading(false);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error checking job status');
      setIsLoading(false);
    }
  }, [jobId, onCompleted]);

  useEffect(() => {
    if (!jobId) {
      setStatus('IDLE');
      setResult(null);
      setError(null);
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setStatus('PENDING');
    
    // Start polling
    const interval = setInterval(() => {
      if (status !== 'SUCCESS' && status !== 'FAILURE') {
        checkStatus();
      } else {
        clearInterval(interval);
      }
    }, 2000); // Check every 2 seconds

    return () => clearInterval(interval);
  }, [jobId, status, checkStatus]);

  return { status, result, error, isLoading };
}
