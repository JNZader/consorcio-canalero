import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { notifications } from '@mantine/notifications';
import { useDisclosure, useMediaQuery } from '@mantine/hooks';

import { API_URL } from '../../../lib/api';
import { floodCalibrationApi } from '../../../lib/api/floodCalibration';
import type {
  BackfillStatusResponse,
  FloodEventDetailResponse,
  NdwiBaselineResponse,
  RainfallSuggestion,
} from '../../../lib/api/floodCalibration';
import { logger } from '../../../lib/logger';
import {
  selectCanSave,
  selectLabeledCount,
  selectSuggestionsCount,
  useFloodCalibrationStore,
} from '../../../stores/floodCalibrationStore';
import { IconCloudRain, IconDroplet } from '../../ui/icons';
import { useFloodCalibrationMap } from './useFloodCalibrationMap';

export function useFloodCalibrationController() {
  const isMobile = useMediaQuery('(max-width: 768px)');

  const selectedDate = useFloodCalibrationStore((s) => s.selectedDate);
  const labeledZones = useFloodCalibrationStore((s) => s.labeledZones);
  const events = useFloodCalibrationStore((s) => s.events);
  const eventsLoading = useFloodCalibrationStore((s) => s.eventsLoading);
  const trainingResult = useFloodCalibrationStore((s) => s.trainingResult);
  const trainingLoading = useFloodCalibrationStore((s) => s.trainingLoading);
  const savingEvent = useFloodCalibrationStore((s) => s.savingEvent);
  const eventDescription = useFloodCalibrationStore((s) => s.eventDescription);
  const labeledCount = useFloodCalibrationStore(selectLabeledCount);
  const canSave = useFloodCalibrationStore(selectCanSave);
  const suggestionsCount = useFloodCalibrationStore(selectSuggestionsCount);
  const rainfallByDate = useFloodCalibrationStore((s) => s.rainfallByDate);
  const rainfallLoading = useFloodCalibrationStore((s) => s.rainfallLoading);
  const suggestions = useFloodCalibrationStore((s) => s.suggestions);
  const suggestionsLoading = useFloodCalibrationStore((s) => s.suggestionsLoading);

  const {
    setSelectedDate,
    clearLabels,
    setEvents,
    setEventsLoading,
    removeEvent,
    setTrainingResult,
    setTrainingLoading,
    setSavingEvent,
    setEventDescription,
    setRainfallByDate,
    setRainfallLoading,
    setSuggestions,
    setSuggestionsLoading,
  } = useFloodCalibrationStore.getState();

  const [ndwiBaselines, setNdwiBaselines] = useState<NdwiBaselineResponse[]>([]);
  const [baselineLoading, setBaselineLoading] = useState(false);
  const [expandedEventId, setExpandedEventId] = useState<string | null>(null);
  const [expandedEventDetail, setExpandedEventDetail] = useState<FloodEventDetailResponse | null>(null);
  const [expandedEventLoading, setExpandedEventLoading] = useState(false);
  const [backfillLoading, setBackfillLoading] = useState(false);
  const [backfillSource, setBackfillSource] = useState<'CHIRPS' | 'IMERG'>('CHIRPS');
  const [backfillStatus, setBackfillStatus] = useState<BackfillStatusResponse | null>(null);
  const backfillPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const now = new Date();
  const [calendarYear, setCalendarYear] = useState(now.getFullYear());
  const [calendarMonth, setCalendarMonth] = useState(now.getMonth());
  const [availableDates, setAvailableDates] = useState<string[]>([]);
  const [loadingDates, setLoadingDates] = useState(false);

  const [deleteConfirmOpened, { open: openDeleteConfirm, close: closeDeleteConfirm }] =
    useDisclosure(false);
  const [trainConfirmOpened, { open: openTrainConfirm, close: closeTrainConfirm }] =
    useDisclosure(false);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [suggestionsExpanded, setSuggestionsExpanded] = useState(true);
  const [rainfallSource, setRainfallSource] = useState<'CHIRPS' | 'IMERG' | 'best'>('best');

  const { mapRef, loadingImage, error, fetchImageForDate } = useFloodCalibrationMap();
  const availableDatesSet = useMemo(() => new Set(availableDates), [availableDates]);

  const stopPolling = useCallback(() => {
    if (backfillPollRef.current) {
      clearInterval(backfillPollRef.current);
      backfillPollRef.current = null;
    }
  }, []);

  const fetchEvents = useCallback(async () => {
    setEventsLoading(true);
    try {
      const data = await floodCalibrationApi.listEvents();
      setEvents(Array.isArray(data) ? data : []);
    } catch (err) {
      logger.error('Error fetching flood events:', err);
      notifications.show({ title: 'Error', message: 'No se pudieron cargar los eventos', color: 'red' });
    } finally {
      setEventsLoading(false);
    }
  }, [setEvents, setEventsLoading]);

  const fetchSuggestions = useCallback(async () => {
    setSuggestionsLoading(true);
    try {
      const data = await floodCalibrationApi.getRainfallSuggestions({ threshold_mm: 20, window_days: 3 });
      setSuggestions(Array.isArray(data) ? data : []);
    } catch (err) {
      logger.warn('Error cargando sugerencias de lluvia:', err);
      setSuggestions([]);
    } finally {
      setSuggestionsLoading(false);
    }
  }, [setSuggestions, setSuggestionsLoading]);

  const handleBackfill = useCallback(async () => {
    setBackfillLoading(true);
    setBackfillStatus(null);
    try {
      const endDate = new Date().toISOString().split('T')[0];
      const startDate = new Date(Date.now() - 730 * 86400000).toISOString().split('T')[0];
      const { job_id } = await floodCalibrationApi.triggerBackfill(startDate, endDate, backfillSource);
      backfillPollRef.current = setInterval(async () => {
        try {
          const status = await floodCalibrationApi.getBackfillStatus(job_id);
          setBackfillStatus(status);
          if (status.state === 'SUCCESS' || status.state === 'FAILURE') {
            stopPolling();
            setBackfillLoading(false);
            notifications.show(
              status.state === 'SUCCESS'
                ? {
                    title: 'Carga completada',
                    message: `${status.records.toLocaleString()} registros guardados en ${status.current} batches.`,
                    color: 'green',
                    icon: <IconCloudRain size={16} />,
                  }
                : { title: 'Error en backfill', message: status.error ?? 'El proceso falló', color: 'red' },
            );
          }
        } catch {
          // ignore polling hiccups
        }
      }, 4000);
    } catch (err) {
      setBackfillLoading(false);
      notifications.show({
        title: 'Error',
        message: err instanceof Error ? err.message : 'No se pudo iniciar la carga de datos',
        color: 'red',
      });
    }
  }, [backfillSource, stopPolling]);

  const handleComputeBaseline = useCallback(async () => {
    setBaselineLoading(true);
    try {
      await floodCalibrationApi.computeNdwiBaseline();
      notifications.show({
        title: 'Baseline NDWI',
        message: 'Cálculo iniciado. Los resultados estarán disponibles en unos minutos.',
        color: 'blue',
        icon: <IconDroplet size={16} />,
      });
    } catch (err) {
      notifications.show({
        title: 'Error',
        message: err instanceof Error ? err.message : 'No se pudo iniciar el cálculo',
        color: 'red',
      });
    } finally {
      setBaselineLoading(false);
    }
  }, []);

  const handleToggleEvent = useCallback(async (eventId: string) => {
    if (expandedEventId === eventId) {
      setExpandedEventId(null);
      setExpandedEventDetail(null);
      return;
    }
    setExpandedEventId(eventId);
    setExpandedEventDetail(null);
    setExpandedEventLoading(true);
    try {
      const detail = await floodCalibrationApi.getEvent(eventId);
      setExpandedEventDetail(detail);
    } catch (err) {
      logger.warn('Error cargando detalle del evento:', err);
    } finally {
      setExpandedEventLoading(false);
    }
  }, [expandedEventId]);

  const handleSelectDay = useCallback((dateStr: string) => {
    setSelectedDate(dateStr);
    clearLabels();
    fetchImageForDate(dateStr);
  }, [clearLabels, fetchImageForDate, setSelectedDate]);

  const handlePrevMonth = useCallback(() => {
    if (calendarMonth === 0) {
      setCalendarYear((y) => y - 1);
      setCalendarMonth(11);
    } else {
      setCalendarMonth((m) => m - 1);
    }
  }, [calendarMonth]);

  const handleNextMonth = useCallback(() => {
    const today = new Date();
    const nextMonth = calendarMonth === 11 ? 0 : calendarMonth + 1;
    const nextYear = calendarMonth === 11 ? calendarYear + 1 : calendarYear;
    if (
      nextYear > today.getFullYear() ||
      (nextYear === today.getFullYear() && nextMonth > today.getMonth())
    ) return;
    setCalendarYear(nextYear);
    setCalendarMonth(nextMonth);
  }, [calendarMonth, calendarYear]);

  const handleSuggestionClick = useCallback((suggestion: RainfallSuggestion) => {
    const suggestedDate = suggestion.suggested_image_date;
    const [yearStr, monthStr] = suggestedDate.split('-');
    setCalendarYear(Number.parseInt(yearStr, 10));
    setCalendarMonth(Number.parseInt(monthStr, 10) - 1);
    setSelectedDate(suggestedDate);
    clearLabels();
    fetchImageForDate(suggestedDate);
  }, [clearLabels, fetchImageForDate, setSelectedDate]);

  const handleSaveEvent = useCallback(async () => {
    if (!selectedDate || Object.keys(labeledZones).length === 0) return;
    setSavingEvent(true);
    try {
      await floodCalibrationApi.createEvent({
        event_date: selectedDate,
        description: eventDescription || null,
        labeled_zones: labeledZones,
      });
      notifications.show({
        title: 'Evento guardado',
        message: `Evento del ${selectedDate} guardado con ${Object.keys(labeledZones).length} zonas`,
        color: 'green',
      });
      clearLabels();
      fetchEvents();
    } catch (err) {
      notifications.show({
        title: 'Error al guardar',
        message: err instanceof Error ? err.message : 'Error desconocido',
        color: 'red',
      });
    } finally {
      setSavingEvent(false);
    }
  }, [clearLabels, eventDescription, fetchEvents, labeledZones, selectedDate, setSavingEvent]);

  const handleConfirmDelete = useCallback(async () => {
    if (!pendingDeleteId) return;
    closeDeleteConfirm();
    try {
      await floodCalibrationApi.deleteEvent(pendingDeleteId);
      removeEvent(pendingDeleteId);
      notifications.show({ title: 'Evento eliminado', message: 'El evento fue eliminado correctamente', color: 'green' });
    } catch (err) {
      notifications.show({
        title: 'Error al eliminar',
        message: err instanceof Error ? err.message : 'Error desconocido',
        color: 'red',
      });
    } finally {
      setPendingDeleteId(null);
    }
  }, [closeDeleteConfirm, pendingDeleteId, removeEvent]);

  const handleConfirmTrain = useCallback(async () => {
    closeTrainConfirm();
    setTrainingLoading(true);
    setTrainingResult(null);
    try {
      const result = await floodCalibrationApi.trainModel();
      setTrainingResult(result);
      notifications.show({
        title: 'Entrenamiento completado',
        message: `Modelo entrenado con ${result.events_used} eventos. Loss: ${result.initial_loss.toFixed(4)} -> ${result.final_loss.toFixed(4)}`,
        color: 'green',
      });
    } catch (err) {
      notifications.show({
        title: 'Error al entrenar',
        message: err instanceof Error ? err.message : 'Error desconocido',
        color: 'red',
      });
    } finally {
      setTrainingLoading(false);
    }
  }, [closeTrainConfirm, setTrainingLoading, setTrainingResult]);

  useEffect(() => stopPolling, [stopPolling]);
  useEffect(() => { fetchSuggestions(); }, [fetchSuggestions]);
  useEffect(() => { fetchEvents(); }, [fetchEvents]);

  useEffect(() => {
    setRainfallLoading(true);
    const startDate = `${calendarYear}-${String(calendarMonth + 1).padStart(2, '0')}-01`;
    const daysInMonth = new Date(calendarYear, calendarMonth + 1, 0).getDate();
    const endDate = `${calendarYear}-${String(calendarMonth + 1).padStart(2, '0')}-${String(daysInMonth).padStart(2, '0')}`;
    const sourceParam = rainfallSource === 'best' ? undefined : rainfallSource;
    floodCalibrationApi
      .getRainfallDaily(startDate, endDate, sourceParam)
      .then((records) => {
        const byDate: Record<string, number> = {};
        for (const r of records) byDate[r.date] = r.precipitation_mm;
        setRainfallByDate(byDate);
      })
      .catch((err) => {
        logger.warn('Error cargando datos de lluvia:', err);
        setRainfallByDate({});
      })
      .finally(() => setRainfallLoading(false));
  }, [calendarMonth, calendarYear, rainfallSource, setRainfallByDate, setRainfallLoading]);

  useEffect(() => {
    floodCalibrationApi.getNdwiBaselines().then(setNdwiBaselines).catch((err) => logger.warn('Error cargando baselines NDWI:', err));
  }, []);

  useEffect(() => {
    setLoadingDates(true);
    setAvailableDates([]);
    const params = new URLSearchParams({
      year: String(calendarYear),
      month: String(calendarMonth + 1),
      sensor: 'sentinel2',
      max_cloud: '40',
    });
    fetch(`${API_URL}/api/v2/geo/gee/images/available-dates?${params}`)
      .then((res) => {
        if (!res.ok) throw new Error('Error al obtener fechas disponibles');
        return res.json();
      })
      .then((data: { dates: string[] }) => setAvailableDates(data.dates))
      .catch((err) => {
        logger.error('Error fetching available dates:', err);
        setAvailableDates([]);
      })
      .finally(() => setLoadingDates(false));
  }, [calendarMonth, calendarYear]);

  return {
    isMobile,
    selectedDate,
    events,
    trainingResult,
    trainingLoading,
    savingEvent,
    eventDescription,
    labeledCount,
    canSave,
    suggestionsCount,
    rainfallByDate,
    rainfallLoading,
    suggestions,
    suggestionsLoading,
    ndwiBaselines,
    baselineLoading,
    expandedEventId,
    expandedEventDetail,
    expandedEventLoading,
    backfillLoading,
    backfillSource,
    backfillStatus,
    mapRef,
    calendarYear,
    calendarMonth,
    availableDatesSet,
    loadingDates,
    loadingImage,
    error,
    deleteConfirmOpened,
    closeDeleteConfirm,
    trainConfirmOpened,
    closeTrainConfirm,
    suggestionsExpanded,
    rainfallSource,
    setBackfillSource,
    setEventDescription,
    setSuggestionsExpanded,
    setRainfallSource,
    handleBackfill,
    handleSelectDay,
    handlePrevMonth,
    handleNextMonth,
    handleSaveEvent,
    clearLabels,
    fetchSuggestions,
    handleSuggestionClick,
    fetchEvents,
    eventsLoading,
    handleToggleEvent,
    handleComputeBaseline,
    openTrainConfirm,
    handleConfirmTrain,
    handleConfirmDelete,
    openDeleteConfirm,
    setPendingDeleteId,
  };
}
