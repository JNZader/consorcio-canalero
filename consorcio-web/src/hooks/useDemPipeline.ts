/**
 * useDemPipeline - Hook for managing the DEM pipeline workflow.
 *
 * Handles:
 * - Submitting a pipeline job
 * - Polling job status with progress percentage
 * - Fetching results (layers, basins)
 * - Loading/error state management
 */

import { notifications } from '@mantine/notifications';
import { useCallback, useEffect, useRef, useState } from 'react';
import { demPipelineApi } from '../lib/api/demPipeline';
import type { BasinsGeoJSON, GeoJobResponse, GeoLayerResponse } from '../lib/api/demPipeline';
import { logger } from '../lib/logger';

type PipelineState = 'idle' | 'submitting' | 'polling' | 'completed' | 'failed';

interface UseDemPipelineResult {
  state: PipelineState;
  jobId: string | null;
  progress: number;
  job: GeoJobResponse | null;
  layers: GeoLayerResponse[];
  basins: BasinsGeoJSON | null;
  error: string | null;
  submit: (areaId?: string, minBasinAreaHa?: number) => Promise<void>;
  reset: () => void;
  fetchLayers: () => Promise<void>;
  fetchBasins: () => Promise<void>;
}

export function useDemPipeline(): UseDemPipelineResult {
  const [state, setState] = useState<PipelineState>('idle');
  const [jobId, setJobId] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [job, setJob] = useState<GeoJobResponse | null>(null);
  const [layers, setLayers] = useState<GeoLayerResponse[]>([]);
  const [basins, setBasins] = useState<BasinsGeoJSON | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => stopPolling();
  }, [stopPolling]);

  const fetchLayers = useCallback(async () => {
    try {
      const response = await demPipelineApi.getLayers();
      setLayers(response.items);
    } catch (err) {
      logger.error('Error fetching DEM layers:', err);
    }
  }, []);

  const fetchBasins = useCallback(async () => {
    try {
      const data = await demPipelineApi.getBasins();
      setBasins(data);
    } catch (err) {
      logger.error('Error fetching basins:', err);
    }
  }, []);

  const pollStatus = useCallback(
    (id: string) => {
      setState('polling');
      pollRef.current = setInterval(async () => {
        try {
          const jobData = await demPipelineApi.getJob(id);
          setJob(jobData);
          setProgress(jobData.progreso ?? 0);

          if (jobData.estado === 'completed') {
            stopPolling();
            setState('completed');
            notifications.show({
              title: 'Pipeline completado',
              message: 'El analisis DEM se completo exitosamente.',
              color: 'green',
            });
            // Fetch results
            await fetchLayers();
            await fetchBasins();
          } else if (jobData.estado === 'failed') {
            stopPolling();
            setError(jobData.error || 'Error desconocido en el pipeline');
            setState('failed');
            notifications.show({
              title: 'Pipeline fallido',
              message: jobData.error || 'Error en el procesamiento DEM.',
              color: 'red',
            });
          }
        } catch (err) {
          logger.error('Error polling DEM pipeline status:', err);
          // Don't stop polling on transient errors
        }
      }, 5000);
    },
    [stopPolling, fetchLayers, fetchBasins]
  );

  const submit = useCallback(
    async (areaId?: string, minBasinAreaHa?: number) => {
      setState('submitting');
      setError(null);
      setJob(null);
      setLayers([]);
      setBasins(null);
      setProgress(0);

      try {
        const response = await demPipelineApi.submit({
          area_id: areaId,
          min_basin_area_ha: minBasinAreaHa,
        });
        setJobId(response.job_id);
        notifications.show({
          title: 'Pipeline iniciado',
          message: 'El pipeline DEM fue despachado. Esperando resultados...',
          color: 'blue',
        });
        pollStatus(response.job_id);
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Error al iniciar pipeline';
        setError(message);
        setState('failed');
        notifications.show({
          title: 'Error',
          message,
          color: 'red',
        });
      }
    },
    [pollStatus]
  );

  const reset = useCallback(() => {
    stopPolling();
    setState('idle');
    setJobId(null);
    setProgress(0);
    setJob(null);
    setLayers([]);
    setBasins(null);
    setError(null);
  }, [stopPolling]);

  return {
    state,
    jobId,
    progress,
    job,
    layers,
    basins,
    error,
    submit,
    reset,
    fetchLayers,
    fetchBasins,
  };
}
