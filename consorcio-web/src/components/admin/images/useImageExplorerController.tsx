import { useMediaQuery } from '@mantine/hooks';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { useImageComparison } from '../../../hooks/useImageComparison';
import { useSelectedImage } from '../../../hooks/useSelectedImage';
import { API_URL } from '../../../lib/api';
import { logger } from '../../../lib/logger';
import {
  type ImageResultLike,
  type ImageSceneLike,
  type ImageSensor,
  buildVisualizationOptions,
  isOpticalSensor,
  createSelectedImageFromResult,
} from './imageExplorerUtils';
import { useImageExplorerMap } from './useImageExplorerMap';

interface Visualization {
  id: string;
  description: string;
}

interface HistoricFlood {
  id: string;
  name: string;
  date: string;
  description: string;
  severity: string;
}

interface AvailableDatesResponse {
  dates: string[];
}

interface ScenesResponse {
  scenes: ImageSceneLike[];
}

function isVisualization(value: unknown): value is Visualization {
  return (
    !!value &&
    typeof value === 'object' &&
    typeof (value as { id?: unknown }).id === 'string' &&
    typeof (value as { description?: unknown }).description === 'string'
  );
}

function isHistoricFlood(value: unknown): value is HistoricFlood {
  return (
    !!value &&
    typeof value === 'object' &&
    typeof (value as { id?: unknown }).id === 'string' &&
    typeof (value as { name?: unknown }).name === 'string' &&
    typeof (value as { date?: unknown }).date === 'string'
  );
}

function normalizeUniqueDates(values: unknown): string[] {
  if (!Array.isArray(values)) return [];
  return [...new Set(values.filter((value): value is string => typeof value === 'string'))].sort();
}

function isImageScene(value: unknown): value is ImageSceneLike {
  return (
    !!value &&
    typeof value === 'object' &&
    typeof (value as { id?: unknown }).id === 'string' &&
    typeof (value as { label?: unknown }).label === 'string' &&
    typeof (value as { tile_url?: unknown }).tile_url === 'string'
  );
}

const API_BASE = `${API_URL}/api/v2/geo/gee/images`;

export function useImageExplorerController() {
  const isMobile = useMediaQuery('(max-width: 768px)');
  const now = new Date();

  const [loading, setLoading] = useState(false);
  const [loadingDates, setLoadingDates] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ImageResultLike | null>(null);
  const [calendarYear, setCalendarYear] = useState(now.getFullYear());
  const [calendarMonth, setCalendarMonth] = useState(now.getMonth());
  const [availableDates, setAvailableDates] = useState<string[]>([]);
  const [selectedDay, setSelectedDay] = useState<string | null>(null);
  // Panel admin/images: el operador necesita ver MÁS imágenes disponibles
  // (incluyendo días parcialmente nubosos) para tener más fechas elegibles.
  // El default global de `config.analysis.default_max_cloud` (20) es para
  // análisis automatizados — acá lo ignoramos a propósito.
  const [maxCloud, setMaxCloud] = useState<string>('80');
  const [visualization, setVisualization] = useState<string>('rgb');
  const [sensor, setSensor] = useState<ImageSensor>('sentinel2');
  const [compositionMode, setCompositionMode] = useState<'scene' | 'composite'>('scene');
  const [scenes, setScenes] = useState<ImageSceneLike[]>([]);
  const [selectedSceneId, setSelectedSceneId] = useState<string | null>(null);
  const [visualizations, setVisualizations] = useState<Visualization[]>([]);
  const [historicFloods, setHistoricFloods] = useState<HistoricFlood[]>([]);

  const { selectedImage, setSelectedImage, clearSelectedImage } = useSelectedImage();
  const {
    comparison,
    setLeftImage,
    setRightImage,
    clearComparison,
    isReady: comparisonReady,
  } = useImageComparison();
  const { mapRef, updateTileLayer } = useImageExplorerMap();

  // GEE requests take seconds: without these guards a stale response can
  // overwrite a newer one, and the generic day-fetch effect would clobber the
  // result loaded by loadHistoricFlood (auditoría 2026-07-09, hallazgos 1 y 4).
  const imageRequestRef = useRef<AbortController | null>(null);
  // Holds the day whose generic fetch must be skipped (set by loadHistoricFlood).
  // Stores the day string — not a boolean — so a re-click on the same flood
  // (where setSelectedDay is an Object.is no-op and the effect never runs)
  // cannot leave a dangling flag that would swallow a later day selection.
  const suppressDayFetchRef = useRef<string | null>(null);

  const availableDatesSet = useMemo(() => new Set(availableDates), [availableDates]);
  const visOptions = buildVisualizationOptions(sensor, visualizations);
  const isCurrentImageSelected = selectedImage?.tile_url === result?.tile_url;

  const fetchImageForDate = useCallback(
    async (dateStr: string) => {
      imageRequestRef.current?.abort();
      const controller = new AbortController();
      imageRequestRef.current = controller;
      setLoading(true);
      setError(null);
      try {
        const endpoint = sensor;
        const isLandsat7Composite = sensor === 'landsat7' && compositionMode === 'composite';
        const params = new URLSearchParams({
          target_date: dateStr,
          days_buffer: isLandsat7Composite ? '20' : '1',
          visualization,
          mode: isLandsat7Composite ? 'composite' : 'scene',
        });
        if (isOpticalSensor(sensor)) params.append('max_cloud', maxCloud);
        const response = await fetch(`${API_BASE}/${endpoint}?${params}`, {
          signal: controller.signal,
        });
        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.detail || 'Error fetching image');
        }
        const data: ImageResultLike = await response.json();
        if (controller.signal.aborted) return;
        setResult(data);
        setSelectedSceneId(null);
        updateTileLayer(data.tile_url);
      } catch (err) {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : 'Error desconocido');
      } finally {
        if (imageRequestRef.current === controller) setLoading(false);
      }
    },
    [compositionMode, maxCloud, sensor, updateTileLayer, visualization]
  );

  const loadHistoricFlood = useCallback(
    async (floodId: string) => {
      imageRequestRef.current?.abort();
      const controller = new AbortController();
      imageRequestRef.current = controller;
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(
          `${API_BASE}/historic-floods/${floodId}?visualization=${visualization}`,
          { signal: controller.signal }
        );
        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.detail || 'Error fetching historic flood');
        }
        const data: ImageResultLike = await response.json();
        if (controller.signal.aborted) return;
        setResult(data);
        updateTileLayer(data.tile_url);
        if (data.flood_info) {
          const floodDate = new Date(data.flood_info.date);
          setCalendarYear(floodDate.getFullYear());
          setCalendarMonth(floodDate.getMonth());
          // Sync the calendar with the flood date WITHOUT letting the generic
          // day-fetch effect replace the historic result we just rendered.
          suppressDayFetchRef.current = data.flood_info.date;
          setSelectedDay(data.flood_info.date);
        }
      } catch (err) {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : 'Error desconocido');
      } finally {
        if (imageRequestRef.current === controller) setLoading(false);
      }
    },
    [updateTileLayer, visualization]
  );

  const handleSelectImage = useCallback(() => {
    const imageData = createSelectedImageFromResult(result);
    if (imageData) setSelectedImage(imageData);
  }, [result, setSelectedImage]);

  const handleSetLeftImage = useCallback(() => {
    const imageData = createSelectedImageFromResult(result);
    if (imageData) setLeftImage(imageData);
  }, [result, setLeftImage]);

  const handleSetRightImage = useCallback(() => {
    const imageData = createSelectedImageFromResult(result);
    if (imageData) setRightImage(imageData);
  }, [result, setRightImage]);

  const handleSelectDay = useCallback((dateStr: string) => {
    // An explicit calendar click must always fetch, even if a historic-flood
    // suppression for this same day is still pending.
    suppressDayFetchRef.current = null;
    setSelectedDay(dateStr);
    setSelectedSceneId(null);
  }, []);

  const handleSelectScene = useCallback(
    (scene: ImageSceneLike) => {
      setResult(scene);
      setSelectedSceneId(scene.id);
      updateTileLayer(scene.tile_url);
    },
    [updateTileLayer]
  );

  // Compute both fields from current state and set each purely. Nesting
  // setCalendarYear inside a setCalendarMonth updater made the year jump by 2
  // on Dec↔Jan crossings: StrictMode double-invokes updaters, firing the
  // nested year setter twice.
  const handlePrevMonth = useCallback(() => {
    if (calendarMonth === 0) {
      setCalendarMonth(11);
      setCalendarYear(calendarYear - 1);
    } else {
      setCalendarMonth(calendarMonth - 1);
    }
    setSelectedDay(null);
  }, [calendarMonth, calendarYear]);

  const handleNextMonth = useCallback(() => {
    const today = new Date();
    const nextMonth = calendarMonth === 11 ? 0 : calendarMonth + 1;
    const nextYear = calendarMonth === 11 ? calendarYear + 1 : calendarYear;
    if (
      nextYear > today.getFullYear() ||
      (nextYear === today.getFullYear() && nextMonth > today.getMonth())
    )
      return;
    setCalendarMonth(nextMonth);
    setCalendarYear(nextYear);
    setSelectedDay(null);
  }, [calendarMonth, calendarYear]);

  const handleMonthYearChange = useCallback((year: number, month: number) => {
    setCalendarYear(year);
    setCalendarMonth(month);
    setSelectedDay(null);
    setResult(null);
    setScenes([]);
    setSelectedSceneId(null);
  }, []);

  useEffect(() => {
    fetch(`${API_BASE}/visualizations`)
      .then(async (res) => {
        if (!res.ok) throw new Error(`Error fetching visualizations (${res.status})`);
        return res.json();
      })
      .then((data: unknown) => {
        const items = Array.isArray(data) ? data.filter(isVisualization) : [];
        setVisualizations(items);
      })
      .catch((err) => {
        logger.error('Error fetching visualizations:', err);
        setVisualizations([]);
      });
    fetch(`${API_BASE}/historic-floods`)
      .then(async (res) => {
        if (!res.ok) throw new Error(`Error fetching historic floods (${res.status})`);
        return res.json();
      })
      .then((data: unknown) => {
        const floods =
          data && typeof data === 'object' && Array.isArray((data as { floods?: unknown[] }).floods)
            ? (data as { floods: unknown[] }).floods.filter(isHistoricFlood)
            : [];
        setHistoricFloods(floods);
      })
      .catch((err) => {
        logger.error('Error fetching historic floods:', err);
        setHistoricFloods([]);
      });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setLoadingDates(true);
    setAvailableDates([]);
    setScenes([]);
    setSelectedSceneId(null);
    const params = new URLSearchParams({
      year: String(calendarYear),
      month: String(calendarMonth + 1),
      sensor,
    });
    if (isOpticalSensor(sensor)) params.append('max_cloud', maxCloud);
    fetch(`${API_BASE}/available-dates?${params}`, { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error('Error fetching available dates');
        return res.json();
      })
      .then((data: AvailableDatesResponse) => setAvailableDates(normalizeUniqueDates(data.dates)))
      .catch((err) => {
        if (controller.signal.aborted) return;
        logger.error('Error fetching available dates:', err);
        setAvailableDates([]);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoadingDates(false);
      });
    return () => controller.abort();
  }, [calendarMonth, calendarYear, sensor, maxCloud]);

  useEffect(() => {
    if (selectedDay) {
      if (suppressDayFetchRef.current === selectedDay) {
        suppressDayFetchRef.current = null;
        return;
      }
      fetchImageForDate(selectedDay);
    } else {
      setScenes([]);
      setSelectedSceneId(null);
    }
  }, [fetchImageForDate, selectedDay]);

  useEffect(() => {
    if (!selectedDay || !sensor.startsWith('landsat')) {
      setScenes([]);
      return;
    }
    const controller = new AbortController();
    const params = new URLSearchParams({
      target_date: selectedDay,
      days_buffer: '1',
      visualization,
      max_cloud: maxCloud,
    });
    fetch(`${API_BASE}/scenes/${sensor}?${params}`, { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error('Error fetching scenes');
        return res.json();
      })
      .then((data: ScenesResponse) => {
        const safeScenes = Array.isArray(data.scenes) ? data.scenes.filter(isImageScene) : [];
        setScenes(safeScenes);
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        logger.error('Error fetching scenes:', err);
        setScenes([]);
      });
    return () => controller.abort();
  }, [maxCloud, selectedDay, sensor, visualization]);

  return {
    isMobile,
    mapRef,
    loading,
    loadingDates,
    error,
    result,
    calendarYear,
    calendarMonth,
    availableDatesSet,
    selectedDay,
    maxCloud,
    visualization,
    sensor,
    compositionMode,
    scenes,
    selectedSceneId,
    historicFloods,
    selectedImage,
    comparison,
    comparisonReady,
    visOptions,
    isCurrentImageSelected,
    setSensor,
    setVisualization,
    setMaxCloud,
    setCompositionMode,
    setSelectedDay,
    setResult,
    clearSelectedImage,
    clearComparison,
    handleSelectDay,
    handleSelectScene,
    handlePrevMonth,
    handleNextMonth,
    handleMonthYearChange,
    handleSelectImage,
    handleSetLeftImage,
    handleSetRightImage,
    loadHistoricFlood,
  };
}
