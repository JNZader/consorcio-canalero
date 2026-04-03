/**
 * FloodCalibrationPanel - Main page for flood model calibration.
 *
 * 3-panel layout:
 * - Left: Timeline/date picker + events list
 * - Right: Leaflet map with GEE tile overlay + zone labeling
 *
 * Allows users to:
 * 1. Select a date and view satellite imagery
 * 2. Click zones to label them as flooded/not-flooded
 * 3. Save labeled events
 * 4. Train the flood prediction model
 */

import {
  ActionIcon,
  Alert,
  Badge,
  Button,
  Card,
  Divider,
  Group,
  Loader,
  Modal,
  Paper,
  Skeleton,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
  Tooltip,
} from '@mantine/core';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import type { Feature, FeatureCollection } from 'geojson';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { notifications } from '@mantine/notifications';
import { useMediaQuery, useDisclosure } from '@mantine/hooks';

import { MAP_CENTER, MAP_DEFAULT_ZOOM } from '../../constants';
import { useConfigStore } from '../../stores/configStore';
import {
  useFloodCalibrationStore,
  selectLabeledCount,
  selectCanSave,
  selectSuggestionsCount,
} from '../../stores/floodCalibrationStore';
import { floodCalibrationApi } from '../../lib/api/floodCalibration';
import type { RainfallSuggestion } from '../../lib/api/floodCalibration';
import { API_URL } from '../../lib/api';
import { logger } from '../../lib/logger';
import {
  IconAlertTriangle,
  IconArrowLeft,
  IconArrowRight,
  IconCalendar,
  IconCheck,
  IconChevronDown,
  IconChevronUp,
  IconCloudRain,
  IconDroplet,
  IconEye,
  IconPlayerPlay,
  IconRefresh,
  IconSatellite,
  IconTrash,
  IconWaveSine,
} from '../ui/icons';

// ─── Constants ────────────────────────────────────────────────────────

const API_BASE = `${API_URL}/api/v2/geo/gee/images`;
const BASINS_URL = `${API_URL}/api/v2/geo/basins`;

const MONTH_NAMES = [
  'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
  'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre',
];

const DAY_NAMES = ['Lu', 'Ma', 'Mi', 'Ju', 'Vi', 'Sa', 'Do'];

/** Zone style by label state */
function getZoneStyle(zonaId: string, labeledZones: Record<string, boolean>): L.PathOptions {
  const label = labeledZones[zonaId];
  if (label === true) {
    // Flooded - red
    return { color: '#ef4444', weight: 2, fillOpacity: 0.4, fillColor: '#ef4444' };
  }
  if (label === false) {
    // Not flooded - green
    return { color: '#22c55e', weight: 2, fillOpacity: 0.4, fillColor: '#22c55e' };
  }
  // Unlabeled - default
  return { color: '#6b7280', weight: 2, fillOpacity: 0.1, fillColor: '#9ca3af' };
}

function getLabelBadge(zonaId: string, labeledZones: Record<string, boolean>) {
  const label = labeledZones[zonaId];
  if (label === true) return <Badge color="red" size="xs">Inundado</Badge>;
  if (label === false) return <Badge color="green" size="xs">No inundado</Badge>;
  return <Badge color="gray" size="xs">Sin etiquetar</Badge>;
}

// ─── Rainfall color helpers ──────────────────────────────────────────

/**
 * Returns a background color based on rainfall intensity (mm).
 * - No data: transparent
 * - 0-10mm: light blue
 * - 10-30mm: medium blue
 * - 30-50mm: dark blue
 * - >50mm: red/dark red
 */
function getRainfallColor(mm: number | undefined): string | undefined {
  if (mm == null || mm <= 0) return undefined;
  if (mm <= 10) return 'rgba(147, 197, 253, 0.5)'; // light blue
  if (mm <= 30) return 'rgba(59, 130, 246, 0.5)'; // medium blue
  if (mm <= 50) return 'rgba(29, 78, 216, 0.5)'; // dark blue
  return 'rgba(220, 38, 38, 0.55)'; // red for >50mm
}

function getRainfallLabel(mm: number): string {
  if (mm <= 10) return 'Lluvia leve';
  if (mm <= 30) return 'Lluvia moderada';
  if (mm <= 50) return 'Lluvia intensa';
  return 'Lluvia muy intensa';
}

// ─── Calendar Grid (reused from ImageExplorerPanel pattern) ────────

interface CalendarGridProps {
  year: number;
  month: number;
  availableDates: Set<string>;
  selectedDay: string | null;
  loadingDates: boolean;
  onSelectDay: (dateStr: string) => void;
  onPrevMonth: () => void;
  onNextMonth: () => void;
  /** Map of date (YYYY-MM-DD) to rainfall mm for overlay coloring */
  rainfallByDate?: Record<string, number>;
}

function CalendarGrid({
  year,
  month,
  availableDates,
  selectedDay,
  loadingDates,
  onSelectDay,
  onPrevMonth,
  onNextMonth,
  rainfallByDate = {},
}: CalendarGridProps) {
  const today = new Date();
  const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;

  const firstDay = new Date(year, month, 1);
  let startDow = firstDay.getDay() - 1;
  if (startDow < 0) startDow = 6;

  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const cells: Array<{ day: number; dateStr: string } | null> = [];

  for (let i = 0; i < startDow; i++) {
    cells.push(null);
  }

  for (let d = 1; d <= daysInMonth; d++) {
    const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
    cells.push({ day: d, dateStr });
  }

  const canGoNext = year < today.getFullYear() || (year === today.getFullYear() && month < today.getMonth());

  return (
    <Paper p="md" withBorder radius="md">
      <Group justify="space-between" mb="sm">
        <ActionIcon variant="subtle" onClick={onPrevMonth} aria-label="Mes anterior">
          <IconArrowLeft size={18} />
        </ActionIcon>
        <Text fw={600} size="lg">
          {MONTH_NAMES[month]} {year}
        </Text>
        <ActionIcon
          variant="subtle"
          onClick={onNextMonth}
          disabled={!canGoNext}
          aria-label="Mes siguiente"
        >
          <IconArrowRight size={18} />
        </ActionIcon>
      </Group>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 2, marginBottom: 4 }}>
        {DAY_NAMES.map((name) => (
          <Text key={name} ta="center" size="xs" fw={600} c="dimmed">
            {name}
          </Text>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 2, position: 'relative' }}>
        {loadingDates && (
          <div
            style={{
              position: 'absolute',
              inset: 0,
              background: 'rgba(255,255,255,0.7)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              zIndex: 10,
              borderRadius: 'var(--mantine-radius-sm)',
            }}
          >
            <Loader size="sm" />
          </div>
        )}

        {cells.map((cell, idx) => {
          if (!cell) {
            return <div key={`empty-${idx}`} />;
          }

          const isAvailable = availableDates.has(cell.dateStr);
          const isSelected = selectedDay === cell.dateStr;
          const isFuture = cell.dateStr > todayStr;
          const rainfallMm = rainfallByDate[cell.dateStr];
          const rainfallBg = getRainfallColor(rainfallMm);

          const cellButton = (
            <button
              type="button"
              key={cell.dateStr}
              disabled={!isAvailable || isFuture}
              onClick={() => isAvailable && !isFuture && onSelectDay(cell.dateStr)}
              style={{
                aspectRatio: '1',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                borderRadius: 'var(--mantine-radius-sm)',
                border: isSelected
                  ? '2px solid var(--mantine-color-blue-6)'
                  : '1px solid transparent',
                background: isSelected
                  ? 'var(--mantine-color-blue-0)'
                  : rainfallBg
                    ? rainfallBg
                    : isAvailable && !isFuture
                      ? 'var(--mantine-color-green-0)'
                      : 'transparent',
                opacity: isFuture ? 0.3 : isAvailable ? 1 : 0.5,
                cursor: isAvailable && !isFuture ? 'pointer' : 'default',
                transition: 'all 150ms ease',
                position: 'relative',
              }}
            >
              <Text
                size="sm"
                fw={isSelected ? 700 : isAvailable ? 500 : 400}
                c={isSelected ? 'blue.7' : rainfallMm != null && rainfallMm > 30 ? 'white' : isAvailable ? 'dark' : 'dimmed'}
              >
                {cell.day}
              </Text>
              {isAvailable && !isFuture && (
                <div
                  style={{
                    width: 6,
                    height: 6,
                    borderRadius: '50%',
                    background: isSelected
                      ? 'var(--mantine-color-blue-6)'
                      : 'var(--mantine-color-green-6)',
                    position: 'absolute',
                    bottom: 3,
                  }}
                />
              )}
            </button>
          );

          // Wrap with Tooltip if there is rainfall data
          if (rainfallMm != null && rainfallMm > 0) {
            return (
              <Tooltip
                key={cell.dateStr}
                label={`${rainfallMm.toFixed(1)} mm — ${getRainfallLabel(rainfallMm)}`}
                position="top"
                withArrow
              >
                {cellButton}
              </Tooltip>
            );
          }

          return cellButton;
        })}
      </div>

      <Group gap="lg" mt="sm" wrap="wrap">
        <Group gap={4}>
          <div style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--mantine-color-green-6)' }} />
          <Text size="xs" c="dimmed">Con imagenes ({availableDates.size})</Text>
        </Group>
        <Group gap={4}>
          <div style={{ width: 8, height: 8, borderRadius: 2, background: 'rgba(147, 197, 253, 0.7)' }} />
          <Text size="xs" c="dimmed">0-10mm</Text>
        </Group>
        <Group gap={4}>
          <div style={{ width: 8, height: 8, borderRadius: 2, background: 'rgba(59, 130, 246, 0.7)' }} />
          <Text size="xs" c="dimmed">10-30mm</Text>
        </Group>
        <Group gap={4}>
          <div style={{ width: 8, height: 8, borderRadius: 2, background: 'rgba(29, 78, 216, 0.7)' }} />
          <Text size="xs" c="dimmed">30-50mm</Text>
        </Group>
        <Group gap={4}>
          <div style={{ width: 8, height: 8, borderRadius: 2, background: 'rgba(220, 38, 38, 0.7)' }} />
          <Text size="xs" c="dimmed">&gt;50mm</Text>
        </Group>
      </Group>
    </Paper>
  );
}

// ─── Main Component ────────────────────────────────────────────────────

export default function FloodCalibrationPanel() {
  const config = useConfigStore((state) => state.config);
  const isMobile = useMediaQuery('(max-width: 768px)');

  // Store
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

  // Rainfall state
  const rainfallByDate = useFloodCalibrationStore((s) => s.rainfallByDate);
  const rainfallLoading = useFloodCalibrationStore((s) => s.rainfallLoading);
  const suggestions = useFloodCalibrationStore((s) => s.suggestions);
  const suggestionsLoading = useFloodCalibrationStore((s) => s.suggestionsLoading);

  const {
    setSelectedDate,
    toggleZoneLabel,
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

  // Map refs
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);
  const tileLayerRef = useRef<L.TileLayer | null>(null);
  const zonasLayerRef = useRef<L.GeoJSON | null>(null);
  const zonasDataRef = useRef<FeatureCollection | null>(null);

  // Calendar state
  const now = new Date();
  const [calendarYear, setCalendarYear] = useState(now.getFullYear());
  const [calendarMonth, setCalendarMonth] = useState(now.getMonth());
  const [availableDates, setAvailableDates] = useState<string[]>([]);
  const [loadingDates, setLoadingDates] = useState(false);
  const [loadingImage, setLoadingImage] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Confirmation dialogs
  const [deleteConfirmOpened, { open: openDeleteConfirm, close: closeDeleteConfirm }] = useDisclosure(false);
  const [trainConfirmOpened, { open: openTrainConfirm, close: closeTrainConfirm }] = useDisclosure(false);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);

  const availableDatesSet = useMemo(() => new Set(availableDates), [availableDates]);

  // Suggestions panel collapse state
  const [suggestionsExpanded, setSuggestionsExpanded] = useState(true);

  // ─── Fetch rainfall data for visible month ────────────────────

  useEffect(() => {
    setRainfallLoading(true);
    const startDate = `${calendarYear}-${String(calendarMonth + 1).padStart(2, '0')}-01`;
    const daysInMonth = new Date(calendarYear, calendarMonth + 1, 0).getDate();
    const endDate = `${calendarYear}-${String(calendarMonth + 1).padStart(2, '0')}-${String(daysInMonth).padStart(2, '0')}`;

    floodCalibrationApi
      .getRainfallSummary(startDate, endDate)
      .then(() => {
        // Summary is zone-level; we also need daily data.
        // Use first zone or aggregate — for calendar overlay, fetch all zones' daily data
        // and show max per day (worst-case rainfall for any zone).
        return floodCalibrationApi.getRainfallForZone('all', startDate, endDate);
      })
      .then((records) => {
        const byDate: Record<string, number> = {};
        for (const r of records) {
          // Keep max across zones if backend returns multiple per date
          byDate[r.date] = Math.max(byDate[r.date] ?? 0, r.precipitation_mm);
        }
        setRainfallByDate(byDate);
      })
      .catch((err) => {
        // Rainfall data is optional — degrade gracefully
        logger.warn('Error cargando datos de lluvia:', err);
        setRainfallByDate({});
      })
      .finally(() => setRainfallLoading(false));
  }, [calendarYear, calendarMonth, setRainfallByDate, setRainfallLoading]);

  // ─── Fetch rainfall suggestions ─────────────────────────────

  const fetchSuggestions = useCallback(async () => {
    setSuggestionsLoading(true);
    try {
      const data = await floodCalibrationApi.getRainfallSuggestions();
      setSuggestions(Array.isArray(data) ? data : []);
    } catch (err) {
      logger.warn('Error cargando sugerencias de lluvia:', err);
      setSuggestions([]);
    } finally {
      setSuggestionsLoading(false);
    }
  }, [setSuggestions, setSuggestionsLoading]);

  useEffect(() => {
    fetchSuggestions();
  }, [fetchSuggestions]);

  // ─── Initialize map ─────────────────────────────────────────

  useEffect(() => {
    if (!mapRef.current || mapInstanceRef.current) return;

    const center = config?.map.center
      ? ([config.map.center.lat, config.map.center.lng] as [number, number])
      : MAP_CENTER;
    const zoom = config?.map.zoom ?? MAP_DEFAULT_ZOOM;

    const map = L.map(mapRef.current, { center, zoom, zoomControl: true });

    L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      { attribution: 'Tiles &copy; Esri', maxZoom: 18 },
    ).addTo(map);

    L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',
      { maxZoom: 18 },
    ).addTo(map);

    mapInstanceRef.current = map;

    return () => {
      map.remove();
      mapInstanceRef.current = null;
    };
  }, [config?.map.center, config?.map.zoom]);

  // ─── Load zonas_operativas ──────────────────────────────────

  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;

    fetch(BASINS_URL)
      .then((res) => {
        if (res.ok) return res.json();
        throw new Error('No se pudieron cargar las zonas operativas');
      })
      .then((geojson: FeatureCollection) => {
        zonasDataRef.current = geojson;
        renderZonas(map, geojson);
      })
      .catch((err) => logger.warn('Error cargando zonas operativas:', err));

    return () => {
      if (zonasLayerRef.current && map) {
        map.removeLayer(zonasLayerRef.current);
        zonasLayerRef.current = null;
      }
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ─── Render / update zone styles ───────────────────────────

  const renderZonas = useCallback((map: L.Map, geojson: FeatureCollection) => {
    if (zonasLayerRef.current) {
      map.removeLayer(zonasLayerRef.current);
    }

    const currentLabels = useFloodCalibrationStore.getState().labeledZones;

    const layer = L.geoJSON(geojson, {
      style: (feature) => {
        const zonaId = feature?.properties?.id || feature?.id;
        return getZoneStyle(String(zonaId), currentLabels);
      },
      onEachFeature: (feature: Feature, featureLayer: L.Layer) => {
        const zonaId = String(feature.properties?.id || feature.id);
        const zonaName = feature.properties?.nombre || feature.properties?.name || zonaId;

        // Tooltip with zone name
        (featureLayer as L.Path).bindTooltip(zonaName, {
          sticky: true,
          className: 'zona-tooltip',
        });

        // Click to toggle label
        featureLayer.on('click', () => {
          toggleZoneLabel(zonaId);
        });
      },
    }).addTo(map);

    zonasLayerRef.current = layer;
  }, [toggleZoneLabel]);

  // Re-render zone styles when labels change
  useEffect(() => {
    const map = mapInstanceRef.current;
    const geojson = zonasDataRef.current;
    if (!map || !geojson) return;

    renderZonas(map, geojson);
  }, [labeledZones, renderZonas]);

  // ─── Fetch available dates ──────────────────────────────────

  useEffect(() => {
    setLoadingDates(true);
    setAvailableDates([]);

    const params = new URLSearchParams({
      year: String(calendarYear),
      month: String(calendarMonth + 1),
      sensor: 'sentinel2',
      max_cloud: '40',
    });

    fetch(`${API_BASE}/available-dates?${params}`)
      .then((res) => {
        if (!res.ok) throw new Error('Error al obtener fechas disponibles');
        return res.json();
      })
      .then((data: { dates: string[] }) => {
        setAvailableDates(data.dates);
      })
      .catch((err) => {
        logger.error('Error fetching available dates:', err);
        setAvailableDates([]);
      })
      .finally(() => setLoadingDates(false));
  }, [calendarYear, calendarMonth]);

  // ─── Fetch satellite image for a date ───────────────────────

  const fetchImageForDate = useCallback(
    async (dateStr: string) => {
      setLoadingImage(true);
      setError(null);

      try {
        const params = new URLSearchParams({
          target_date: dateStr,
          days_buffer: '1',
          visualization: 'rgb',
          max_cloud: '40',
        });

        const response = await fetch(`${API_BASE}/sentinel2?${params}`);

        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.detail || 'Error al obtener imagen');
        }

        const data = await response.json();
        updateTileLayer(data.tile_url);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Error desconocido');
      } finally {
        setLoadingImage(false);
      }
    },
    [],
  );

  const updateTileLayer = useCallback((tileUrl: string) => {
    const map = mapInstanceRef.current;
    if (!map) return;

    if (tileLayerRef.current) {
      map.removeLayer(tileLayerRef.current);
    }

    const layer = L.tileLayer(tileUrl, {
      attribution: 'Imagery &copy; Google Earth Engine',
      maxZoom: 18,
      opacity: 0.85,
    }).addTo(map);

    tileLayerRef.current = layer;
  }, []);

  // ─── Calendar navigation ───────────────────────────────────

  const handleSelectDay = useCallback(
    (dateStr: string) => {
      setSelectedDate(dateStr);
      clearLabels();
      fetchImageForDate(dateStr);
    },
    [fetchImageForDate, setSelectedDate, clearLabels],
  );

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

    if (nextYear > today.getFullYear() || (nextYear === today.getFullYear() && nextMonth > today.getMonth())) {
      return;
    }

    setCalendarYear(nextYear);
    setCalendarMonth(nextMonth);
  }, [calendarMonth, calendarYear]);

  // ─── Handle suggestion click: navigate calendar to suggested date ──

  const handleSuggestionClick = useCallback(
    (suggestion: RainfallSuggestion) => {
      const suggestedDate = suggestion.suggested_image_date;
      const [yearStr, monthStr] = suggestedDate.split('-');
      const targetYear = parseInt(yearStr, 10);
      const targetMonth = parseInt(monthStr, 10) - 1; // 0-indexed

      // Navigate calendar to the target month
      setCalendarYear(targetYear);
      setCalendarMonth(targetMonth);

      // Select the suggested date and fetch its satellite image
      setSelectedDate(suggestedDate);
      clearLabels();
      fetchImageForDate(suggestedDate);
    },
    [setSelectedDate, clearLabels, fetchImageForDate],
  );

  // ─── Events CRUD ───────────────────────────────────────────

  const fetchEvents = useCallback(async () => {
    setEventsLoading(true);
    try {
      const data = await floodCalibrationApi.listEvents();
      setEvents(Array.isArray(data) ? data : []);
    } catch (err) {
      logger.error('Error fetching flood events:', err);
      notifications.show({
        title: 'Error',
        message: 'No se pudieron cargar los eventos',
        color: 'red',
      });
    } finally {
      setEventsLoading(false);
    }
  }, [setEvents, setEventsLoading]);

  // Fetch events on mount
  useEffect(() => {
    fetchEvents();
  }, [fetchEvents]);

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
  }, [selectedDate, labeledZones, eventDescription, clearLabels, fetchEvents, setSavingEvent]);

  const handleRequestDelete = useCallback((id: string) => {
    setPendingDeleteId(id);
    openDeleteConfirm();
  }, [openDeleteConfirm]);

  const handleConfirmDelete = useCallback(async () => {
    if (!pendingDeleteId) return;
    closeDeleteConfirm();
    try {
      await floodCalibrationApi.deleteEvent(pendingDeleteId);
      removeEvent(pendingDeleteId);
      notifications.show({
        title: 'Evento eliminado',
        message: 'El evento fue eliminado correctamente',
        color: 'green',
      });
    } catch (err) {
      notifications.show({
        title: 'Error al eliminar',
        message: err instanceof Error ? err.message : 'Error desconocido',
        color: 'red',
      });
    } finally {
      setPendingDeleteId(null);
    }
  }, [pendingDeleteId, removeEvent, closeDeleteConfirm]);

  const handleRequestTrain = useCallback(() => {
    openTrainConfirm();
  }, [openTrainConfirm]);

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
  }, [setTrainingLoading, setTrainingResult, closeTrainConfirm]);

  // ─── Render ────────────────────────────────────────────────

  return (
    <Stack gap="md">
      {/* Header */}
      <Group justify="space-between">
        <Group gap="xs">
          <IconDroplet size={24} />
          <Title order={3}>Calibracion de Modelo de Inundacion</Title>
        </Group>
        <Badge variant="light" color="blue" size="lg">
          {events.length} eventos guardados
        </Badge>
      </Group>

      {error && (
        <Alert color="red" icon={<IconAlertTriangle />} title="Error">
          {error}
        </Alert>
      )}

      {/* Main layout */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: isMobile ? '1fr' : 'minmax(280px, 340px) 1fr',
          gap: 16,
        }}
      >
        {/* Left column: Calendar + Save controls */}
        <Stack gap="md">
          <CalendarGrid
            year={calendarYear}
            month={calendarMonth}
            availableDates={availableDatesSet}
            selectedDay={selectedDate}
            loadingDates={loadingDates || rainfallLoading}
            onSelectDay={handleSelectDay}
            onPrevMonth={handlePrevMonth}
            onNextMonth={handleNextMonth}
            rainfallByDate={rainfallByDate}
          />

          {/* Labeling controls */}
          {selectedDate && (
            <Paper p="md" withBorder radius="md">
              <Stack gap="sm">
                <Group justify="space-between">
                  <Text fw={600} size="sm">
                    <IconCalendar size={16} style={{ verticalAlign: 'middle', marginRight: 4 }} />
                    {selectedDate}
                  </Text>
                  <Badge color={labeledCount > 0 ? 'blue' : 'gray'}>
                    {labeledCount} zona{labeledCount !== 1 ? 's' : ''} etiquetada{labeledCount !== 1 ? 's' : ''}
                  </Badge>
                </Group>

                <TextInput
                  label="Descripcion (opcional)"
                  placeholder="Ej: Inundacion post-tormenta"
                  value={eventDescription}
                  onChange={(e) => setEventDescription(e.currentTarget.value)}
                  size="sm"
                />

                <Group gap="sm">
                  <Button
                    fullWidth
                    onClick={handleSaveEvent}
                    disabled={!canSave}
                    loading={savingEvent}
                    leftSection={<IconCheck size={16} />}
                    color="green"
                  >
                    Guardar Evento
                  </Button>
                  <Button
                    fullWidth
                    variant="light"
                    color="gray"
                    onClick={clearLabels}
                    disabled={labeledCount === 0}
                  >
                    Limpiar Etiquetas
                  </Button>
                </Group>

                {/* Legend */}
                <Divider />
                <Text size="xs" c="dimmed" fw={500}>Leyenda (click en zona para alternar):</Text>
                <Group gap="md">
                  <Group gap={4}>
                    <div style={{ width: 12, height: 12, borderRadius: 2, background: '#ef4444' }} />
                    <Text size="xs">Inundado</Text>
                  </Group>
                  <Group gap={4}>
                    <div style={{ width: 12, height: 12, borderRadius: 2, background: '#22c55e' }} />
                    <Text size="xs">No inundado</Text>
                  </Group>
                  <Group gap={4}>
                    <div style={{ width: 12, height: 12, borderRadius: 2, background: '#9ca3af' }} />
                    <Text size="xs">Sin etiquetar</Text>
                  </Group>
                </Group>
              </Stack>
            </Paper>
          )}
        </Stack>

        {/* Right column: Map */}
        <Card
          padding={0}
          radius="md"
          withBorder
          style={{ minHeight: 500, position: 'relative' }}
        >
          <div
            ref={mapRef}
            style={{ width: '100%', height: 500, borderRadius: 'var(--mantine-radius-md)' }}
          />

          {loadingImage && (
            <div
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                right: 0,
                bottom: 0,
                background: 'rgba(255,255,255,0.8)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                borderRadius: 'var(--mantine-radius-md)',
              }}
            >
              <Stack align="center">
                <Loader size="lg" />
                <Text>Cargando imagen satelital...</Text>
              </Stack>
            </div>
          )}

          {!selectedDate && !loadingImage && (
            <div
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                right: 0,
                bottom: 0,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                pointerEvents: 'none',
              }}
            >
              <Paper p="lg" radius="md" shadow="sm" style={{ pointerEvents: 'auto', textAlign: 'center' }}>
                <IconSatellite size={32} style={{ opacity: 0.4, marginBottom: 8 }} />
                <Text c="dimmed" size="sm">
                  Selecciona un dia del calendario
                </Text>
                <Text c="dimmed" size="xs">
                  para ver la imagen satelital y etiquetar zonas
                </Text>
              </Paper>
            </div>
          )}
        </Card>
      </div>

      {/* Eventos Sugeridos panel */}
      <Paper p="md" withBorder radius="md">
        <Group justify="space-between" mb={suggestionsExpanded ? 'md' : 0}>
          <Group gap="xs">
            <IconCloudRain size={18} />
            <Title order={5}>Eventos Sugeridos</Title>
            {suggestionsCount > 0 && (
              <Badge color="blue" variant="filled" size="sm">
                {suggestionsCount}
              </Badge>
            )}
          </Group>
          <Group gap="xs">
            <ActionIcon variant="subtle" onClick={fetchSuggestions} loading={suggestionsLoading}>
              <IconRefresh size={18} />
            </ActionIcon>
            <ActionIcon
              variant="subtle"
              onClick={() => setSuggestionsExpanded((prev) => !prev)}
              aria-label={suggestionsExpanded ? 'Colapsar' : 'Expandir'}
            >
              {suggestionsExpanded ? <IconChevronUp size={18} /> : <IconChevronDown size={18} />}
            </ActionIcon>
          </Group>
        </Group>

        {suggestionsExpanded && (
          <>
            {suggestionsLoading && (
              <Stack gap="xs">
                {Array.from({ length: 3 }).map((_, i) => (
                  <Skeleton key={i} height={56} radius="sm" />
                ))}
              </Stack>
            )}

            {!suggestionsLoading && suggestions.length === 0 && (
              <Text c="dimmed" size="sm" ta="center" py="lg">
                No hay eventos de lluvia detectados para sugerir imagenes.
              </Text>
            )}

            {!suggestionsLoading && suggestions.length > 0 && (
              <Stack gap="xs">
                {suggestions.map((suggestion, idx) => (
                  <Paper key={`${suggestion.event_date}-${idx}`} p="sm" withBorder radius="sm">
                    <Group justify="space-between" wrap="nowrap">
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <Group gap="xs" wrap="wrap">
                          <IconCloudRain size={14} />
                          <Text size="sm" fw={500}>
                            Evento: {suggestion.event_date}
                          </Text>
                          <Badge size="xs" color="blue" variant="light">
                            {suggestion.accumulated_mm.toFixed(1)} mm
                          </Badge>
                          <Badge size="xs" color="gray" variant="light">
                            {suggestion.cloud_cover.toFixed(0)}% nubes
                          </Badge>
                        </Group>
                        <Text size="xs" c="dimmed" mt={2}>
                          Zonas: {suggestion.zone_names.join(', ')}
                        </Text>
                        <Text size="xs" c="dimmed">
                          Imagen sugerida: {suggestion.suggested_image_date}
                        </Text>
                      </div>
                      <Tooltip label="Ver imagen en el calendario">
                        <Button
                          size="xs"
                          variant="light"
                          color="blue"
                          leftSection={<IconEye size={14} />}
                          onClick={() => handleSuggestionClick(suggestion)}
                        >
                          Ver imagen
                        </Button>
                      </Tooltip>
                    </Group>
                  </Paper>
                ))}
              </Stack>
            )}
          </>
        )}
      </Paper>

      {/* Bottom section: Events list + Training controls */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr',
          gap: 16,
        }}
      >
        {/* Events list */}
        <Paper p="md" withBorder radius="md">
          <Group justify="space-between" mb="md">
            <Title order={5}>
              <Group gap="xs">
                <IconWaveSine size={18} />
                Eventos Guardados
              </Group>
            </Title>
            <ActionIcon variant="subtle" onClick={fetchEvents} loading={eventsLoading}>
              <IconRefresh size={18} />
            </ActionIcon>
          </Group>

          {eventsLoading && (
            <Stack gap="xs">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} height={56} radius="sm" />
              ))}
            </Stack>
          )}

          {!eventsLoading && events.length === 0 && (
            <Text c="dimmed" size="sm" ta="center" py="xl">
              No hay eventos guardados. Selecciona una fecha, etiqueta zonas y guarda un evento.
            </Text>
          )}

          {!eventsLoading && events.length > 0 && (
            <Stack gap="xs">
              {events.map((event) => (
                <Paper key={event.id} p="sm" withBorder radius="sm">
                  <Group justify="space-between" wrap="nowrap">
                    <div>
                      <Group gap="xs">
                        <IconCalendar size={14} />
                        <Text size="sm" fw={500}>{event.event_date}</Text>
                        <Badge size="xs" variant="light">
                          {event.label_count} zona{event.label_count !== 1 ? 's' : ''}
                        </Badge>
                      </Group>
                      {event.description && (
                        <Text size="xs" c="dimmed" mt={2}>{event.description}</Text>
                      )}
                    </div>
                    <Tooltip label="Eliminar evento">
                      <ActionIcon
                        variant="subtle"
                        color="red"
                        size="sm"
                        onClick={() => handleRequestDelete(event.id)}
                      >
                        <IconTrash size={14} />
                      </ActionIcon>
                    </Tooltip>
                  </Group>
                </Paper>
              ))}
            </Stack>
          )}
        </Paper>

        {/* Training controls */}
        <Paper p="md" withBorder radius="md">
          <Title order={5} mb="md">
            <Group gap="xs">
              <IconPlayerPlay size={18} />
              Entrenamiento del Modelo
            </Group>
          </Title>

          <Stack gap="md">
            <Group gap="lg">
              <div>
                <Text size="xs" c="dimmed">Eventos totales</Text>
                <Text size="lg" fw={700}>{events.length}</Text>
              </div>
            </Group>

            <Tooltip
              label={events.length < 5 ? `Se necesitan al menos 5 eventos (actual: ${events.length})` : 'Entrenar modelo con los eventos guardados'}
            >
              <Button
                fullWidth
                onClick={handleRequestTrain}
                disabled={events.length < 5}
                loading={trainingLoading}
                leftSection={<IconPlayerPlay size={16} />}
                color="blue"
              >
                Entrenar Modelo
              </Button>
            </Tooltip>

            {/* Training results */}
            {trainingResult && (
              <Paper p="sm" withBorder radius="sm" bg="green.0">
                <Stack gap="sm">
                  <Group gap="xs">
                    <IconCheck size={16} color="var(--mantine-color-green-7)" />
                    <Text size="sm" fw={600} c="green.7">Entrenamiento completado</Text>
                  </Group>

                  <Group gap="lg">
                    <div>
                      <Text size="xs" c="dimmed">Eventos usados</Text>
                      <Text fw={600}>{trainingResult.events_used}</Text>
                    </div>
                    <div>
                      <Text size="xs" c="dimmed">Epocas</Text>
                      <Text fw={600}>{trainingResult.epochs}</Text>
                    </div>
                    <div>
                      <Text size="xs" c="dimmed">Loss inicial</Text>
                      <Text fw={600}>{trainingResult.initial_loss.toFixed(4)}</Text>
                    </div>
                    <div>
                      <Text size="xs" c="dimmed">Loss final</Text>
                      <Text fw={600} c="green.7">{trainingResult.final_loss.toFixed(4)}</Text>
                    </div>
                  </Group>

                  <Divider />
                  <Text size="xs" fw={500}>Pesos del modelo:</Text>
                  <Table striped>
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>Feature</Table.Th>
                        <Table.Th>Peso</Table.Th>
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {Object.entries(trainingResult.weights).map(([key, value]) => (
                        <Table.Tr key={key}>
                          <Table.Td>{key}</Table.Td>
                          <Table.Td>{value.toFixed(4)}</Table.Td>
                        </Table.Tr>
                      ))}
                      <Table.Tr>
                        <Table.Td fw={600}>Bias</Table.Td>
                        <Table.Td>{trainingResult.bias.toFixed(4)}</Table.Td>
                      </Table.Tr>
                    </Table.Tbody>
                  </Table>
                </Stack>
              </Paper>
            )}
          </Stack>
        </Paper>
      </div>

      {/* Confirmation: Delete event */}
      <Modal
        opened={deleteConfirmOpened}
        onClose={closeDeleteConfirm}
        title="Confirmar eliminacion"
        centered
        size="sm"
      >
        <Stack gap="md">
          <Text size="sm">
            ¿Estas seguro de que queres eliminar este evento? Esta accion no se puede deshacer.
            Las etiquetas y features asociadas tambien seran eliminadas.
          </Text>
          <Group justify="flex-end" gap="sm">
            <Button variant="default" onClick={closeDeleteConfirm}>
              Cancelar
            </Button>
            <Button color="red" onClick={handleConfirmDelete}>
              Eliminar
            </Button>
          </Group>
        </Stack>
      </Modal>

      {/* Confirmation: Train model */}
      <Modal
        opened={trainConfirmOpened}
        onClose={closeTrainConfirm}
        title="Confirmar entrenamiento"
        centered
        size="sm"
      >
        <Stack gap="md">
          <Text size="sm">
            Se creara un backup del modelo actual antes de entrenar.
            El proceso puede tardar unos segundos.
          </Text>
          <Group gap="lg">
            <div>
              <Text size="xs" c="dimmed">Eventos disponibles</Text>
              <Text fw={600}>{events.length}</Text>
            </div>
          </Group>
          <Group justify="flex-end" gap="sm">
            <Button variant="default" onClick={closeTrainConfirm}>
              Cancelar
            </Button>
            <Button color="blue" onClick={handleConfirmTrain} leftSection={<IconPlayerPlay size={16} />}>
              Entrenar
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}
