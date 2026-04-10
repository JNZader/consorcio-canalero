import { notifications } from '@mantine/notifications';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { canalSuggestionsApi, type CanalSuggestion, type SuggestionTipo } from '../../../lib/api';
import { formatDate } from '../../../lib/formatters';
import { logger } from '../../../lib/logger';
import { IconCheck } from '../../ui/icons';
import { buildSuggestionStats, createVisibleTypesSet, sortSuggestions } from './canalSuggestionsUtils';

export function useCanalSuggestionsController() {
  const [suggestions, setSuggestions] = useState<CanalSuggestion[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [batchId, setBatchId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filterTipo, setFilterTipo] = useState<string>('');
  const [analyzing, setAnalyzing] = useState(false);
  const [lastAnalysis, setLastAnalysis] = useState<string | null>(null);
  const [visibleTypes, setVisibleTypes] = useState<Set<SuggestionTipo>>(createVisibleTypesSet);
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  const fetchResults = useCallback(async (tipo?: string) => {
    setLoading(true);
    setError(null);
    try {
      const params: { tipo?: SuggestionTipo; limit?: number } = { limit: 100 };
      if (tipo) params.tipo = tipo as SuggestionTipo;
      const data = await canalSuggestionsApi.getResults(params);
      setSuggestions(data.items);
      setTotalCount(data.total);
      setBatchId(data.batch_id);
      if (data.items.length > 0) {
        setLastAnalysis(data.items[0].created_at);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Error al cargar resultados';
      setError(message);
      logger.error('[CanalSuggestions] Error fetching results:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchResults();
  }, [fetchResults]);

  const handleFilterChange = useCallback(
    (value: string | null) => {
      const tipo = value ?? '';
      setFilterTipo(tipo);
      fetchResults(tipo || undefined);
    },
    [fetchResults],
  );

  const toggleLayerType = useCallback((tipo: SuggestionTipo) => {
    setVisibleTypes((prev) => {
      const next = new Set(prev);
      if (next.has(tipo)) next.delete(tipo);
      else next.add(tipo);
      return next;
    });
  }, []);

  const handleAnalyze = useCallback(async () => {
    setAnalyzing(true);
    try {
      const res = await canalSuggestionsApi.postAnalyze();
      notifications.show({
        title: 'Analisis iniciado',
        message: `Tarea enviada (ID: ${res.task_id}). Los resultados se actualizaran cuando finalice.`,
        color: 'blue',
        autoClose: 8000,
      });

      const pollIntervals = [5000, 10000, 15000, 20000, 30000];
      for (const delay of pollIntervals) {
        await new Promise((resolve) => setTimeout(resolve, delay));
        try {
          const data = await canalSuggestionsApi.getResults({ limit: 1 });
          if (data.batch_id && data.batch_id !== batchId) {
            notifications.show({
              title: 'Analisis completado',
              message: 'Los resultados se han actualizado.',
              color: 'green',
              icon: <IconCheck size={16} />,
            });
            fetchResults(filterTipo || undefined);
            setAnalyzing(false);
            return;
          }
        } catch {
          // continue polling
        }
      }

      notifications.show({
        title: 'Analisis en progreso',
        message: 'El analisis continua en segundo plano. Recarga manualmente para ver resultados.',
        color: 'yellow',
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Error al iniciar analisis';
      notifications.show({
        title: 'Error',
        message,
        color: 'red',
      });
      logger.error('[CanalSuggestions] Error triggering analysis:', err);
    } finally {
      setAnalyzing(false);
    }
  }, [batchId, fetchResults, filterTipo]);

  const sortedSuggestions = useMemo(() => sortSuggestions(suggestions, sortDir), [suggestions, sortDir]);
  const stats = useMemo(() => buildSuggestionStats(suggestions), [suggestions]);
  const formattedLastAnalysis = useMemo(
    () => (lastAnalysis ? formatDate(lastAnalysis) : null),
    [lastAnalysis],
  );

  return {
    suggestions,
    totalCount,
    loading,
    error,
    setError,
    filterTipo,
    analyzing,
    visibleTypes,
    sortDir,
    setSortDir,
    fetchResults,
    handleFilterChange,
    toggleLayerType,
    handleAnalyze,
    sortedSuggestions,
    stats,
    formattedLastAnalysis,
  };
}
