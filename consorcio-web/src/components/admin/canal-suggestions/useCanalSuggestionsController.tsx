import { notifications } from '@mantine/notifications';
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  canalSuggestionsApi,
  routingApi,
  type CanalSuggestion,
  type CorridorScenarioListItem,
  type CorridorRoutingResponse,
  type RoutingMode,
  type RoutingProfile,
  type SuggestionTipo,
} from '../../../lib/api';
import { formatDate } from '../../../lib/formatters';
import { logger } from '../../../lib/logger';
import { IconCheck } from '../../ui/icons';
import { buildSuggestionStats, createVisibleTypesSet, sortSuggestions } from './canalSuggestionsUtils';
import { RASTER_WEIGHT_PRESETS, ROUTING_PROFILE_PRESETS } from './corridorRoutingUtils';

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
  const [corridorForm, setCorridorForm] = useState({
    mode: 'network' as RoutingMode,
    profile: 'balanceado' as RoutingProfile,
    fromLon: '' as number | '',
    fromLat: '' as number | '',
    toLon: '' as number | '',
    toLat: '' as number | '',
    corridorWidthM: 50,
    alternativeCount: 2,
    weightSlope: RASTER_WEIGHT_PRESETS.balanceado.slope,
    weightHydric: RASTER_WEIGHT_PRESETS.balanceado.hydric,
    weightProperty: RASTER_WEIGHT_PRESETS.balanceado.property,
  });
  const [corridorLoading, setCorridorLoading] = useState(false);
  const [corridorError, setCorridorError] = useState<string | null>(null);
  const [corridorResult, setCorridorResult] = useState<CorridorRoutingResponse | null>(null);
  const [corridorPickTarget, setCorridorPickTarget] = useState<'from' | 'to' | null>(null);
  const [corridorScenarioName, setCorridorScenarioName] = useState('Escenario corredor');
  const [corridorScenarioNotes, setCorridorScenarioNotes] = useState('');
  const [currentScenarioId, setCurrentScenarioId] = useState<string | null>(null);
  const [corridorScenarios, setCorridorScenarios] = useState<CorridorScenarioListItem[]>([]);
  const [corridorScenarioLoading, setCorridorScenarioLoading] = useState(false);

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

  const fetchCorridorScenarios = useCallback(async () => {
    setCorridorScenarioLoading(true);
    try {
      const data = await routingApi.listScenarios();
      setCorridorScenarios(data.items);
    } catch (err) {
      logger.error('[CanalSuggestions] Error loading corridor scenarios:', err);
    } finally {
      setCorridorScenarioLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCorridorScenarios();
  }, [fetchCorridorScenarios]);

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

  const updateCorridorField = useCallback(
    <K extends keyof typeof corridorForm>(field: K, value: (typeof corridorForm)[K]) => {
      setCorridorForm((prev) => ({ ...prev, [field]: value }));
    },
    [],
  );

  const handleCalculateCorridor = useCallback(async () => {
    if (
      corridorForm.fromLon === '' ||
      corridorForm.fromLat === '' ||
      corridorForm.toLon === '' ||
      corridorForm.toLat === ''
    ) {
      setCorridorError('Completa origen y destino para calcular el corredor.');
      return;
    }

    setCorridorLoading(true);
    setCorridorError(null);

    try {
      const result = await routingApi.getCorridor({
        from_lon: corridorForm.fromLon,
        from_lat: corridorForm.fromLat,
        to_lon: corridorForm.toLon,
        to_lat: corridorForm.toLat,
        mode: corridorForm.mode,
        profile: corridorForm.profile,
        corridor_width_m: corridorForm.corridorWidthM,
        alternative_count: corridorForm.alternativeCount,
        weight_slope: corridorForm.weightSlope,
        weight_hydric: corridorForm.weightHydric,
        weight_property: corridorForm.weightProperty,
      });
      setCorridorResult(result);
      setCurrentScenarioId(null);
      setCorridorScenarioName(
        `Corridor ${corridorForm.profile} ${new Date().toLocaleDateString('es-AR')}`,
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Error al calcular corredor';
      setCorridorError(message);
      logger.error('[CanalSuggestions] Error calculating corridor:', err);
    } finally {
      setCorridorLoading(false);
    }
  }, [corridorForm]);

  const beginCorridorPick = useCallback((target: 'from' | 'to') => {
    setCorridorPickTarget(target);
    setCorridorError(null);
  }, []);

  const handleCorridorMapPick = useCallback((coords: { lon: number; lat: number }) => {
    setCorridorForm((prev) => {
      if (corridorPickTarget === 'from') {
        return { ...prev, fromLon: coords.lon, fromLat: coords.lat };
      }
      if (corridorPickTarget === 'to') {
        return { ...prev, toLon: coords.lon, toLat: coords.lat };
      }
      return prev;
    });

    setCorridorPickTarget((prev) => (prev === 'from' ? 'to' : null));
    setCorridorError(null);
  }, [corridorPickTarget]);

  const cancelCorridorPick = useCallback(() => {
    setCorridorPickTarget(null);
  }, []);

  const handleCorridorProfileChange = useCallback((profile: RoutingProfile) => {
    const preset = ROUTING_PROFILE_PRESETS[profile];
    const weightPreset = RASTER_WEIGHT_PRESETS[profile];
    setCorridorForm((prev) => ({
      ...prev,
      profile,
      corridorWidthM: preset.corridorWidthM,
      alternativeCount: preset.alternativeCount,
      weightSlope: weightPreset.slope,
      weightHydric: weightPreset.hydric,
      weightProperty: weightPreset.property,
    }));
    setCorridorError(null);
  }, []);

  const handleCorridorModeChange = useCallback((mode: RoutingMode) => {
    setCorridorForm((prev) => ({ ...prev, mode }));
    setCorridorError(null);
  }, []);

  const handleSaveCorridorScenario = useCallback(async () => {
    if (!corridorResult) {
      setCorridorError('Primero calcula un corredor antes de guardarlo.');
      return;
    }

    try {
      const saved = await routingApi.saveScenario({
        name: corridorScenarioName.trim() || 'Escenario corredor',
        profile: corridorForm.profile,
        request_payload: {
          from_lon: Number(corridorForm.fromLon),
          from_lat: Number(corridorForm.fromLat),
          to_lon: Number(corridorForm.toLon),
          to_lat: Number(corridorForm.toLat),
          mode: corridorForm.mode,
          profile: corridorForm.profile,
          corridor_width_m: corridorForm.corridorWidthM,
          alternative_count: corridorForm.alternativeCount,
          weight_slope: corridorForm.weightSlope,
          weight_hydric: corridorForm.weightHydric,
          weight_property: corridorForm.weightProperty,
        },
        result_payload: corridorResult,
        notes: corridorScenarioNotes.trim() || undefined,
        previous_version_id: currentScenarioId ?? undefined,
        is_favorite: currentScenarioId
          ? corridorScenarios.find((item) => item.id === currentScenarioId)?.is_favorite ?? false
          : false,
      });
      setCurrentScenarioId(saved.id);
      setCorridorResult(saved.result_payload);
      notifications.show({
        title: 'Escenario guardado',
        message: 'El corridor routing quedó persistido para reutilizarlo luego.',
        color: 'green',
        icon: <IconCheck size={16} />,
      });
      fetchCorridorScenarios();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Error al guardar escenario';
      setCorridorError(message);
      logger.error('[CanalSuggestions] Error saving corridor scenario:', err);
    }
  }, [
    corridorForm,
    corridorResult,
    corridorScenarioName,
    corridorScenarioNotes,
    corridorScenarios,
    currentScenarioId,
    fetchCorridorScenarios,
  ]);

  const handleLoadCorridorScenario = useCallback(async (scenarioId: string) => {
    try {
      const scenario = await routingApi.getScenario(scenarioId);
      setCorridorForm({
        mode: scenario.request_payload.mode ?? 'network',
        profile: scenario.request_payload.profile ?? scenario.profile,
        fromLon: scenario.request_payload.from_lon,
        fromLat: scenario.request_payload.from_lat,
        toLon: scenario.request_payload.to_lon,
        toLat: scenario.request_payload.to_lat,
        corridorWidthM: scenario.request_payload.corridor_width_m ?? 50,
        alternativeCount: scenario.request_payload.alternative_count ?? 2,
        weightSlope: scenario.request_payload.weight_slope ?? RASTER_WEIGHT_PRESETS[scenario.profile].slope,
        weightHydric: scenario.request_payload.weight_hydric ?? RASTER_WEIGHT_PRESETS[scenario.profile].hydric,
        weightProperty: scenario.request_payload.weight_property ?? RASTER_WEIGHT_PRESETS[scenario.profile].property,
      });
      setCurrentScenarioId(scenario.id);
      setCorridorScenarioName(scenario.name);
      setCorridorScenarioNotes(scenario.notes ?? '');
      setCorridorResult(scenario.result_payload);
      setCorridorError(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Error al cargar escenario';
      setCorridorError(message);
      logger.error('[CanalSuggestions] Error loading corridor scenario:', err);
    }
  }, []);

  const handleExportCorridorScenario = useCallback(async (scenarioId: string) => {
    try {
      const featureCollection = await routingApi.exportScenarioGeoJson(scenarioId);
      const blob = new Blob([JSON.stringify(featureCollection, null, 2)], {
        type: 'application/geo+json',
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `corridor-scenario-${scenarioId}.geojson`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Error al exportar escenario';
      setCorridorError(message);
      logger.error('[CanalSuggestions] Error exporting corridor scenario:', err);
    }
  }, []);

  const handleExportCorridorScenarioPdf = useCallback(async (scenarioId: string) => {
    try {
      const blob = await routingApi.exportScenarioPdf(scenarioId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `corridor-scenario-${scenarioId}.pdf`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Error al exportar PDF';
      setCorridorError(message);
      logger.error('[CanalSuggestions] Error exporting corridor scenario pdf:', err);
    }
  }, []);

  const handleApproveCorridorScenario = useCallback(async (scenarioId: string) => {
    try {
      const note = window.prompt('Nota de aprobación (opcional):') ?? undefined;
      const scenario = await routingApi.approveScenario(scenarioId, note);
      if (corridorResult && scenario.id) {
        setCorridorResult(scenario.result_payload);
      }
      notifications.show({
        title: 'Escenario aprobado',
        message: `${scenario.name} quedó marcado como aprobado.`,
        color: 'green',
        icon: <IconCheck size={16} />,
      });
      fetchCorridorScenarios();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Error al aprobar escenario';
      setCorridorError(message);
      logger.error('[CanalSuggestions] Error approving corridor scenario:', err);
    }
  }, [corridorResult, fetchCorridorScenarios]);

  const handleUnapproveCorridorScenario = useCallback(async (scenarioId: string) => {
    try {
      const note = window.prompt('Motivo de desaprobación (opcional):') ?? undefined;
      const scenario = await routingApi.unapproveScenario(scenarioId, note);
      if (corridorResult && scenario.id) {
        setCorridorResult(scenario.result_payload);
      }
      notifications.show({
        title: 'Escenario actualizado',
        message: `${scenario.name} volvió a borrador.`,
        color: 'yellow',
      });
      fetchCorridorScenarios();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Error al desaprobar escenario';
      setCorridorError(message);
      logger.error('[CanalSuggestions] Error unapproving corridor scenario:', err);
    }
  }, [corridorResult, fetchCorridorScenarios]);

  const handleFavoriteCorridorScenario = useCallback(async (scenarioId: string, isFavorite: boolean) => {
    try {
      await routingApi.favoriteScenario(scenarioId, isFavorite);
      fetchCorridorScenarios();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Error al actualizar favorito';
      setCorridorError(message);
      logger.error('[CanalSuggestions] Error toggling favorite corridor scenario:', err);
    }
  }, [fetchCorridorScenarios]);

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
    corridorForm,
    corridorLoading,
    corridorError,
    corridorResult,
    corridorPickTarget,
    corridorScenarioName,
    corridorScenarioNotes,
    currentScenarioId,
    corridorScenarios,
    corridorScenarioLoading,
    updateCorridorField,
    handleCorridorModeChange,
    handleExportCorridorScenarioPdf,
    handleApproveCorridorScenario,
    handleUnapproveCorridorScenario,
    handleFavoriteCorridorScenario,
    handleCorridorProfileChange,
    handleCalculateCorridor,
    beginCorridorPick,
    handleCorridorMapPick,
    cancelCorridorPick,
    setCorridorScenarioName,
    setCorridorScenarioNotes,
    handleSaveCorridorScenario,
    handleLoadCorridorScenario,
    handleExportCorridorScenario,
  };
}
