/**
 * useDemPipeline - Hook for managing the DEM pipeline workflow.
 *
 * Handles:
 * - Submitting a pipeline job
 * - Polling job status with progress percentage
 * - Fetching results (layers, basins)
 * - Loading/error state management
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import type { BasinsGeoJSON, GeoJobResponse, GeoLayerResponse } from '../lib/api/demPipeline';
import { demPipelineApi } from '../lib/api/demPipeline';
import { isAbortError } from '../lib/abortUtils';
import { logger } from '../lib/logger';
import { showError, showInfo, showSuccess } from '../lib/notifications';
import { erroresUi, textoError } from '../lib/userFacingError';

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
  const mountedRef = useRef(true);
  const activeJobIdRef = useRef<string | null>(null);
  const pollInFlightRef = useRef(false);
  const pollAbortRef = useRef<AbortController | null>(null);
  const submitSeqRef = useRef(0);
  const layersAbortRef = useRef<AbortController | null>(null);
  const layersSeqRef = useRef(0);
  const basinsAbortRef = useRef<AbortController | null>(null);
  const basinsSeqRef = useRef(0);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    pollAbortRef.current?.abort();
    pollAbortRef.current = null;
    pollInFlightRef.current = false;
    activeJobIdRef.current = null;
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      stopPolling();
      layersAbortRef.current?.abort();
      basinsAbortRef.current?.abort();
    };
  }, [stopPolling]);

  const fetchLayers = useCallback(async () => {
    layersAbortRef.current?.abort();
    const controller = new AbortController();
    layersAbortRef.current = controller;
    const seq = ++layersSeqRef.current;

    try {
      const response = await demPipelineApi.getLayers(undefined, { signal: controller.signal });
      if (!mountedRef.current || controller.signal.aborted || seq !== layersSeqRef.current) return;
      setLayers(response.items);
    } catch (err) {
      if (!mountedRef.current || isAbortError(err, controller.signal) || seq !== layersSeqRef.current) {
        return;
      }
      logger.error('Error fetching DEM layers:', err);
    }
  }, []);

  const fetchBasins = useCallback(async () => {
    basinsAbortRef.current?.abort();
    const controller = new AbortController();
    basinsAbortRef.current = controller;
    const seq = ++basinsSeqRef.current;

    try {
      const data = await demPipelineApi.getBasins({ signal: controller.signal });
      if (!mountedRef.current || controller.signal.aborted || seq !== basinsSeqRef.current) return;
      setBasins(data);
    } catch (err) {
      if (!mountedRef.current || isAbortError(err, controller.signal) || seq !== basinsSeqRef.current) {
        return;
      }
      logger.error('Error fetching basins:', err);
    }
  }, []);

  const pollStatus = useCallback(
    (id: string) => {
      stopPolling();
      if (!mountedRef.current) return;

      activeJobIdRef.current = id;
      setState('polling');
      pollRef.current = setInterval(async () => {
        if (!mountedRef.current || activeJobIdRef.current !== id || pollInFlightRef.current) {
          return;
        }
        pollInFlightRef.current = true;
        const controller = new AbortController();
        pollAbortRef.current = controller;
        try {
          const jobData = await demPipelineApi.getJob(id, { signal: controller.signal });
          if (!mountedRef.current || controller.signal.aborted || activeJobIdRef.current !== id) {
            return;
          }
          setJob(jobData);
          setProgress(jobData.progreso ?? 0);

          if (jobData.estado === 'completed') {
            stopPolling();
            if (!mountedRef.current) return;
            setState('completed');
            showSuccess('Pipeline completado', 'El análisis DEM se completó exitosamente.');
            // Fetch results
            await fetchLayers();
            await fetchBasins();
          } else if (jobData.estado === 'failed') {
            stopPolling();
            if (!mountedRef.current) return;
            setError(jobData.error || 'Error desconocido en el pipeline');
            setState('failed');
            showError('Pipeline fallido', jobData.error || 'Error en el procesamiento DEM.');
          }
        } catch (err) {
          if (!mountedRef.current || isAbortError(err, controller.signal)) {
            return;
          }
          logger.error('Error polling DEM pipeline status:', err);
          // Don't stop polling on transient errors
        } finally {
          pollInFlightRef.current = false;
        }
      }, 5000);
    },
    [stopPolling, fetchLayers, fetchBasins]
  );

  const submit = useCallback(
    async (areaId?: string, minBasinAreaHa?: number) => {
      stopPolling();
      const seq = ++submitSeqRef.current;
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
        if (!mountedRef.current || seq !== submitSeqRef.current) return;
        setJobId(response.job_id);
        showInfo('Pipeline iniciado', 'El pipeline DEM fue despachado. Esperando resultados...');
        pollStatus(response.job_id);
      } catch (err) {
        if (!mountedRef.current || seq !== submitSeqRef.current) return;
        const message = err instanceof Error ? err.message : textoError(erroresUi.iniciarPipeline);
        setError(message);
        setState('failed');
        showError(erroresUi.iniciarPipeline.titulo, message);
      }
    },
    [pollStatus, stopPolling]
  );

  const reset = useCallback(() => {
    submitSeqRef.current += 1;
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
