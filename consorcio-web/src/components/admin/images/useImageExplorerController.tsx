import { useCallback, useEffect, useMemo, useState } from 'react';
import { useMediaQuery } from '@mantine/hooks';

import { API_URL } from '../../../lib/api';
import { logger } from '../../../lib/logger';
import { useSelectedImage } from '../../../hooks/useSelectedImage';
import { useImageComparison } from '../../../hooks/useImageComparison';
import { useConfigStore } from '../../../stores/configStore';
import { createSelectedImageFromResult, type ImageResultLike, buildVisualizationOptions } from './imageExplorerUtils';
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

function isVisualization(value: unknown): value is Visualization {
  return !!value && typeof value === 'object' && typeof (value as { id?: unknown }).id === 'string' && typeof (value as { description?: unknown }).description === 'string';
}

function isHistoricFlood(value: unknown): value is HistoricFlood {
  return !!value && typeof value === 'object'
    && typeof (value as { id?: unknown }).id === 'string'
    && typeof (value as { name?: unknown }).name === 'string'
    && typeof (value as { date?: unknown }).date === 'string';
}

function normalizeUniqueDates(values: unknown): string[] {
  if (!Array.isArray(values)) return [];
  return [...new Set(values.filter((value): value is string => typeof value === 'string'))].sort();
}

const API_BASE = `${API_URL}/api/v2/geo/gee/images`;

export function useImageExplorerController() {
  const config = useConfigStore((state) => state.config);
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
  const [maxCloud, setMaxCloud] = useState<string>(config?.analysis.default_max_cloud?.toString() || '40');
  const [visualization, setVisualization] = useState<string>('rgb');
  const [sensor, setSensor] = useState<'sentinel2' | 'sentinel1'>('sentinel2');
  const [visualizations, setVisualizations] = useState<Visualization[]>([]);
  const [historicFloods, setHistoricFloods] = useState<HistoricFlood[]>([]);

  const { selectedImage, setSelectedImage, clearSelectedImage } = useSelectedImage();
  const { comparison, setLeftImage, setRightImage, clearComparison, isReady: comparisonReady } = useImageComparison();
  const { mapRef, updateTileLayer } = useImageExplorerMap();

  const availableDatesSet = useMemo(() => new Set(availableDates), [availableDates]);
  const visOptions = buildVisualizationOptions(sensor, visualizations);
  const isCurrentImageSelected = selectedImage?.tile_url === result?.tile_url;

  const fetchImageForDate = useCallback(async (dateStr: string) => {
    setLoading(true);
    setError(null);
    try {
      const endpoint = sensor === 'sentinel2' ? 'sentinel2' : 'sentinel1';
      const params = new URLSearchParams({ target_date: dateStr, days_buffer: '1', visualization });
      if (sensor === 'sentinel2') params.append('max_cloud', maxCloud);
      const response = await fetch(`${API_BASE}/${endpoint}?${params}`);
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Error fetching image');
      }
      const data: ImageResultLike = await response.json();
      setResult(data);
      updateTileLayer(data.tile_url);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido');
    } finally {
      setLoading(false);
    }
  }, [maxCloud, sensor, updateTileLayer, visualization]);

  const loadHistoricFlood = useCallback(async (floodId: string) => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/historic-floods/${floodId}?visualization=${visualization}`);
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Error fetching historic flood');
      }
      const data: ImageResultLike = await response.json();
      setResult(data);
      updateTileLayer(data.tile_url);
      if (data.flood_info) {
        const floodDate = new Date(data.flood_info.date);
        setCalendarYear(floodDate.getFullYear());
        setCalendarMonth(floodDate.getMonth());
        setSelectedDay(data.flood_info.date);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido');
    } finally {
      setLoading(false);
    }
  }, [updateTileLayer, visualization]);

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
    setSelectedDay(dateStr);
  }, []);

  const handlePrevMonth = useCallback(() => {
    setCalendarMonth((prev) => {
      if (prev === 0) {
        setCalendarYear((y) => y - 1);
        return 11;
      }
      return prev - 1;
    });
    setSelectedDay(null);
  }, []);

  const handleNextMonth = useCallback(() => {
    const today = new Date();
    setCalendarMonth((prev) => {
      const nextMonth = prev === 11 ? 0 : prev + 1;
      const nextYear = prev === 11 ? calendarYear + 1 : calendarYear;
      if (nextYear > today.getFullYear() || (nextYear === today.getFullYear() && nextMonth > today.getMonth())) return prev;
      if (prev === 11) setCalendarYear((y) => y + 1);
      return nextMonth;
    });
    setSelectedDay(null);
  }, [calendarYear]);

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
        const floods = data && typeof data === 'object' && Array.isArray((data as { floods?: unknown[] }).floods)
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
    setLoadingDates(true);
    setAvailableDates([]);
    const params = new URLSearchParams({ year: String(calendarYear), month: String(calendarMonth + 1), sensor });
    if (sensor === 'sentinel2') params.append('max_cloud', maxCloud);
    fetch(`${API_BASE}/available-dates?${params}`)
      .then((res) => {
        if (!res.ok) throw new Error('Error fetching available dates');
        return res.json();
      })
      .then((data: AvailableDatesResponse) => setAvailableDates(normalizeUniqueDates(data.dates)))
      .catch((err) => {
        logger.error('Error fetching available dates:', err);
        setAvailableDates([]);
      })
      .finally(() => setLoadingDates(false));
  }, [calendarMonth, calendarYear, sensor, maxCloud]);

  useEffect(() => {
    if (selectedDay) {
      fetchImageForDate(selectedDay);
    }
  }, [fetchImageForDate, selectedDay]);

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
    historicFloods,
    selectedImage,
    comparison,
    comparisonReady,
    visOptions,
    isCurrentImageSelected,
    setSensor,
    setVisualization,
    setMaxCloud,
    setSelectedDay,
    setResult,
    clearSelectedImage,
    clearComparison,
    handleSelectDay,
    handlePrevMonth,
    handleNextMonth,
    handleSelectImage,
    handleSetLeftImage,
    handleSetRightImage,
    loadHistoricFlood,
  };
}
