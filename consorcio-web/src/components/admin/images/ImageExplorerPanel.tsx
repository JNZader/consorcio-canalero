import {
  ActionIcon,
  Alert,
  Badge,
  Button,
  Card,
  Divider,
  Group,
  Loader,
  Paper,
  SegmentedControl,
  Select,
  SimpleGrid,
  Stack,
  Text,
  Title,
  Tooltip,
  UnstyledButton,
} from '@mantine/core';
import '@mantine/dates/styles.css';
import {
  IconAlertTriangle,
  IconArrowLeft,
  IconArrowRight,
  IconCalendar,
  IconCheck,
  IconGitCompare,
  IconPhoto,
  IconSatellite,
  IconX,
} from '../../ui/icons';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { useMediaQuery } from '@mantine/hooks';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { MAP_CENTER, MAP_DEFAULT_ZOOM } from '../../../constants';
import { useConfigStore } from '../../../stores/configStore';
import { useSelectedImage, type SelectedImage } from '../../../hooks/useSelectedImage';
import { useImageComparison } from '../../../hooks/useImageComparison';
import { API_URL } from '../../../lib/api';
import { logger } from '../../../lib/logger';

// Types
interface Visualization {
  id: string;
  description: string;
}

interface ImageResult {
  tile_url: string;
  target_date: string;
  dates_available: string[];
  images_count: number;
  visualization: string;
  visualization_description: string;
  sensor: string;
  collection: string;
  flood_info?: {
    id: string;
    name: string;
    date: string;
    description: string;
    severity: string;
  };
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
  sensor: string;
  year: number;
  month: number;
  total: number;
}

// API base URL
const API_BASE = `${API_URL}/api/v2/geo/gee/images`;

// Estilo para la capa zona (borde rojo sin relleno)
const ZONA_STYLE = {
  color: '#FF0000',
  weight: 3,
  fillOpacity: 0,
};

const MONTH_NAMES = [
  'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
  'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre',
];

const DAY_NAMES = ['Lu', 'Ma', 'Mi', 'Ju', 'Vi', 'Sa', 'Do'];

// ─── Calendar Grid Component ───────────────────────────────────────────

interface CalendarGridProps {
  year: number;
  month: number; // 0-indexed
  availableDates: Set<string>;
  selectedDay: string | null;
  loadingDates: boolean;
  onSelectDay: (dateStr: string) => void;
  onPrevMonth: () => void;
  onNextMonth: () => void;
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
}: CalendarGridProps) {
  const today = new Date();
  const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;

  // Build calendar grid
  const firstDay = new Date(year, month, 1);
  // getDay() returns 0=Sun, we want 0=Mon
  let startDow = firstDay.getDay() - 1;
  if (startDow < 0) startDow = 6;

  const daysInMonth = new Date(year, month + 1, 0).getDate();

  const cells: Array<{ day: number; dateStr: string } | null> = [];

  // Empty cells before first day
  for (let i = 0; i < startDow; i++) {
    cells.push(null);
  }

  // Day cells
  for (let d = 1; d <= daysInMonth; d++) {
    const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
    cells.push({ day: d, dateStr });
  }

  // Check if can go forward (not beyond current month)
  const canGoNext = year < today.getFullYear() || (year === today.getFullYear() && month < today.getMonth());

  return (
    <Paper p="md" withBorder radius="md">
      {/* Month/Year header */}
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

      {/* Day names header */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 2, marginBottom: 4 }}>
        {DAY_NAMES.map((name) => (
          <Text key={name} ta="center" size="xs" fw={600} c="dimmed">
            {name}
          </Text>
        ))}
      </div>

      {/* Calendar cells */}
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
          const isToday = cell.dateStr === todayStr;

          return (
            <UnstyledButton
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
                  : isToday
                    ? '1px solid var(--mantine-color-gray-4)'
                    : '1px solid transparent',
                background: isSelected
                  ? 'var(--mantine-color-blue-0)'
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
                c={isSelected ? 'blue.7' : isAvailable ? 'dark' : 'dimmed'}
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
            </UnstyledButton>
          );
        })}
      </div>

      {/* Legend */}
      <Group gap="lg" mt="sm">
        <Group gap={4}>
          <div
            style={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              background: 'var(--mantine-color-green-6)',
            }}
          />
          <Text size="xs" c="dimmed">
            Con imagenes ({availableDates.size})
          </Text>
        </Group>
        <Group gap={4}>
          <div
            style={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              background: 'var(--mantine-color-blue-6)',
            }}
          />
          <Text size="xs" c="dimmed">
            Seleccionado
          </Text>
        </Group>
      </Group>
    </Paper>
  );
}

// ─── Main Component ────────────────────────────────────────────────────

export default function ImageExplorerPanel() {
  const config = useConfigStore((state) => state.config);
  const isMobile = useMediaQuery('(max-width: 768px)');

  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);
  const tileLayerRef = useRef<L.TileLayer | null>(null);
  const zonaLayerRef = useRef<L.GeoJSON | null>(null);

  const [loading, setLoading] = useState(false);
  const [loadingDates, setLoadingDates] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ImageResult | null>(null);

  // Calendar state
  const now = new Date();
  const [calendarYear, setCalendarYear] = useState(now.getFullYear());
  const [calendarMonth, setCalendarMonth] = useState(now.getMonth()); // 0-indexed
  const [availableDates, setAvailableDates] = useState<string[]>([]);
  const [selectedDay, setSelectedDay] = useState<string | null>(null);

  // Filters
  const [maxCloud, setMaxCloud] = useState<string>(
    config?.analysis.default_max_cloud?.toString() || '40'
  );
  const [visualization, setVisualization] = useState<string>('rgb');
  const [sensor, setSensor] = useState<'sentinel2' | 'sentinel1'>('sentinel2');

  // Data
  const [visualizations, setVisualizations] = useState<Visualization[]>([]);
  const [historicFloods, setHistoricFloods] = useState<HistoricFlood[]>([]);

  // Shared image selection
  const { selectedImage, setSelectedImage, clearSelectedImage } = useSelectedImage();

  // Image comparison
  const {
    comparison,
    setLeftImage,
    setRightImage,
    clearComparison,
    isReady: comparisonReady,
  } = useImageComparison();

  // Memoize available dates as Set for O(1) lookup
  const availableDatesSet = useMemo(() => new Set(availableDates), [availableDates]);

  // Initialize map
  useEffect(() => {
    if (!mapRef.current || mapInstanceRef.current) return;

    const center = config?.map.center
      ? ([config.map.center.lat, config.map.center.lng] as [number, number])
      : MAP_CENTER;
    const zoom = config?.map.zoom ?? MAP_DEFAULT_ZOOM;

    const map = L.map(mapRef.current, {
      center,
      zoom,
      zoomControl: true,
    });

    // Base layer - satellite
    L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      {
        attribution: 'Tiles &copy; Esri',
        maxZoom: 18,
      }
    ).addTo(map);

    // Labels layer
    L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',
      {
        maxZoom: 18,
      }
    ).addTo(map);

    mapInstanceRef.current = map;

    return () => {
      map.remove();
      mapInstanceRef.current = null;
    };
  }, [config?.map.center, config?.map.zoom]);

  // Cargar capa zona del consorcio
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;

    fetch(`${API_URL}/api/v2/geo/gee/layers/zona`)
      .then((res) => {
        if (res.ok) return res.json();
        throw new Error('No se pudo cargar la capa zona');
      })
      .then((geojson) => {
        if (zonaLayerRef.current) {
          map.removeLayer(zonaLayerRef.current);
        }
        const layer = L.geoJSON(geojson, { style: ZONA_STYLE }).addTo(map);
        zonaLayerRef.current = layer;
      })
      .catch((err) => logger.warn('Error cargando capa zona:', err));

    return () => {
      if (zonaLayerRef.current && map) {
        map.removeLayer(zonaLayerRef.current);
        zonaLayerRef.current = null;
      }
    };
  }, []);

  // Fetch visualizations and historic floods on mount
  useEffect(() => {
    fetch(`${API_BASE}/visualizations`)
      .then((res) => res.json())
      .then((data: Visualization[]) => setVisualizations(data))
      .catch((err) => logger.error('Error fetching visualizations:', err));

    fetch(`${API_BASE}/historic-floods`)
      .then((res) => res.json())
      .then((data: { floods: HistoricFlood[] }) => setHistoricFloods(data.floods))
      .catch((err) => logger.error('Error fetching historic floods:', err));
  }, []);

  // Fetch available dates when month/year/sensor/maxCloud changes
  useEffect(() => {
    setLoadingDates(true);
    setAvailableDates([]);

    const params = new URLSearchParams({
      year: String(calendarYear),
      month: String(calendarMonth + 1), // API expects 1-indexed
      sensor,
    });

    if (sensor === 'sentinel2') {
      params.append('max_cloud', maxCloud);
    }

    fetch(`${API_BASE}/available-dates?${params}`)
      .then((res) => {
        if (!res.ok) throw new Error('Error fetching available dates');
        return res.json();
      })
      .then((data: AvailableDatesResponse) => {
        setAvailableDates(data.dates);
      })
      .catch((err) => {
        logger.error('Error fetching available dates:', err);
        setAvailableDates([]);
      })
      .finally(() => setLoadingDates(false));
  }, [calendarYear, calendarMonth, sensor, maxCloud]);

  // Update tile layer on map
  const updateTileLayer = useCallback((tileUrl: string) => {
    const map = mapInstanceRef.current;
    if (!map) return;

    if (tileLayerRef.current) {
      map.removeLayer(tileLayerRef.current);
    }

    const layer = L.tileLayer(tileUrl, {
      attribution: 'Imagery &copy; Google Earth Engine',
      maxZoom: 18,
      opacity: 0.9,
    }).addTo(map);

    tileLayerRef.current = layer;
  }, []);

  // Fetch image for a specific date
  const fetchImageForDate = useCallback(
    async (dateStr: string) => {
      setLoading(true);
      setError(null);

      try {
        const endpoint = sensor === 'sentinel2' ? 'sentinel2' : 'sentinel1';
        const params = new URLSearchParams({
          target_date: dateStr,
          days_buffer: '1',
          visualization,
        });

        if (sensor === 'sentinel2') {
          params.append('max_cloud', maxCloud);
        }

        const response = await fetch(`${API_BASE}/${endpoint}?${params}`);

        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.detail || 'Error fetching image');
        }

        const data: ImageResult = await response.json();
        setResult(data);
        updateTileLayer(data.tile_url);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Error desconocido');
      } finally {
        setLoading(false);
      }
    },
    [sensor, visualization, maxCloud, updateTileLayer]
  );

  // Handle day selection in calendar
  const handleSelectDay = useCallback(
    (dateStr: string) => {
      setSelectedDay(dateStr);
      fetchImageForDate(dateStr);
    },
    [fetchImageForDate]
  );

  // Calendar navigation
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

      // Don't go beyond current month
      if (nextYear > today.getFullYear() || (nextYear === today.getFullYear() && nextMonth > today.getMonth())) {
        return prev;
      }

      if (prev === 11) {
        setCalendarYear((y) => y + 1);
      }
      return nextMonth;
    });
    setSelectedDay(null);
  }, [calendarYear]);

  // Load historic flood
  const loadHistoricFlood = useCallback(
    async (floodId: string) => {
      setLoading(true);
      setError(null);

      try {
        const response = await fetch(
          `${API_BASE}/historic-floods/${floodId}?visualization=${visualization}`
        );

        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.detail || 'Error fetching historic flood');
        }

        const data: ImageResult = await response.json();
        setResult(data);
        updateTileLayer(data.tile_url);

        // Navigate calendar to flood date
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
    },
    [visualization, updateTileLayer]
  );

  // Create SelectedImage from current result
  const createImageData = useCallback((): SelectedImage | null => {
    if (!result) return null;

    return {
      tile_url: result.tile_url,
      target_date: result.target_date,
      sensor: result.sensor as 'Sentinel-1' | 'Sentinel-2',
      visualization: result.visualization,
      visualization_description: result.visualization_description,
      collection: result.collection,
      images_count: result.images_count,
      flood_info: result.flood_info
        ? {
            id: result.flood_info.id,
            name: result.flood_info.name,
            description: result.flood_info.description,
            severity: result.flood_info.severity,
          }
        : undefined,
      selected_at: new Date().toISOString(),
    };
  }, [result]);

  // Handle selecting image for use in other views
  const handleSelectImage = useCallback(() => {
    const imageData = createImageData();
    if (imageData) {
      setSelectedImage(imageData);
    }
  }, [createImageData, setSelectedImage]);

  // Handle setting as left comparison image
  const handleSetLeftImage = useCallback(() => {
    const imageData = createImageData();
    if (imageData) {
      setLeftImage(imageData);
    }
  }, [createImageData, setLeftImage]);

  // Handle setting as right comparison image
  const handleSetRightImage = useCallback(() => {
    const imageData = createImageData();
    if (imageData) {
      setRightImage(imageData);
    }
  }, [createImageData, setRightImage]);

  // Re-fetch current image when visualization changes (if a day is selected)
  useEffect(() => {
    if (selectedDay && result) {
      fetchImageForDate(selectedDay);
    }
    // Only react to visualization changes, not selectedDay/result
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visualization]);

  // Check if current result matches selected image
  const isCurrentImageSelected = selectedImage?.tile_url === result?.tile_url;

  // Visualization options based on sensor
  const visOptions =
    sensor === 'sentinel2'
      ? visualizations.map((v) => ({ value: v.id, label: v.description }))
      : [
          { value: 'vv', label: 'Radar SAR (VV)' },
          { value: 'vv_flood', label: 'Deteccion de agua (SAR)' },
        ];

  return (
    <Stack gap="md">
      {/* Top bar: Sensor + Visualization + Cloud */}
      <Paper p="md" withBorder radius="md">
        <Group gap="md" wrap="wrap" justify="space-between">
          <SegmentedControl
            value={sensor}
            onChange={(v) => {
              setSensor(v as 'sentinel2' | 'sentinel1');
              setVisualization(v === 'sentinel2' ? 'rgb' : 'vv');
              setSelectedDay(null);
              setResult(null);
            }}
            data={[
              { value: 'sentinel2', label: 'Sentinel-2 (Optico)' },
              { value: 'sentinel1', label: 'Sentinel-1 (SAR)' },
            ]}
          />

          <Group gap="md" wrap="wrap">
            <Select
              label="Visualizacion"
              value={visualization}
              onChange={(v) => v && setVisualization(v)}
              data={visOptions}
              w={220}
              size="sm"
            />

            {sensor === 'sentinel2' && (
              <Select
                label="Nubes max."
                value={maxCloud}
                onChange={(v) => {
                  if (v) {
                    setMaxCloud(v);
                    setSelectedDay(null);
                    setResult(null);
                  }
                }}
                data={[
                  { value: '20', label: '20%' },
                  { value: '40', label: '40%' },
                  { value: '60', label: '60%' },
                  { value: '80', label: '80%' },
                ]}
                w={100}
                size="sm"
              />
            )}

            <Group gap="xs" mt="auto">
              <IconCalendar size={16} />
              <Text size="xs" c="dimmed">
                {sensor === 'sentinel1' ? 'SAR funciona con nubes' : 'Selecciona un dia del calendario'}
              </Text>
            </Group>
          </Group>
        </Group>
      </Paper>

      {/* Main area: Calendar + Map + Info */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: isMobile ? '1fr' : 'minmax(280px, 340px) 1fr',
          gap: 16,
        }}
      >
        {/* Left: Calendar */}
        <div>
          <CalendarGrid
            year={calendarYear}
            month={calendarMonth}
            availableDates={availableDatesSet}
            selectedDay={selectedDay}
            loadingDates={loadingDates}
            onSelectDay={handleSelectDay}
            onPrevMonth={handlePrevMonth}
            onNextMonth={handleNextMonth}
          />
        </div>

        {/* Right: Map + Info */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Error */}
          {error && (
            <Alert color="red" icon={<IconAlertTriangle />} title="Error">
              {error}
            </Alert>
          )}

          {/* Map */}
          <Card
            padding={0}
            radius="md"
            withBorder
            style={{ minHeight: 450, position: 'relative', flex: '1 1 auto' }}
          >
            <div
              ref={mapRef}
              style={{ width: '100%', height: 450, borderRadius: 'var(--mantine-radius-md)' }}
            />

            {loading && (
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

            {!result && !loading && (
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
                    Selecciona un dia con imagenes
                  </Text>
                  <Text c="dimmed" size="xs">
                    del calendario para previsualizar
                  </Text>
                </Paper>
              </div>
            )}
          </Card>

          {/* Image info + actions */}
          {result && (
            <Paper p="md" withBorder radius="md">
              <Group justify="space-between" wrap="wrap" gap="md">
                {/* Image info */}
                <Group gap="lg" wrap="wrap">
                  {result.flood_info && (
                    <Badge color="blue" variant="light" size="lg">
                      {result.flood_info.name}
                    </Badge>
                  )}
                  <Group gap={4}>
                    <IconSatellite size={16} />
                    <Text size="sm" fw={500}>{result.sensor}</Text>
                  </Group>
                  <Group gap={4}>
                    <IconCalendar size={16} />
                    <Text size="sm" fw={500}>{result.target_date}</Text>
                  </Group>
                  <Text size="sm" c="dimmed">
                    {result.visualization_description}
                  </Text>
                  <Text size="xs" c="dimmed">
                    {result.images_count} imagen{result.images_count !== 1 ? 'es' : ''} | {result.collection}
                  </Text>
                </Group>

                {/* Actions */}
                <Group gap="sm" wrap="wrap">
                  <Button
                    variant={isCurrentImageSelected ? 'light' : 'filled'}
                    color={isCurrentImageSelected ? 'green' : 'blue'}
                    leftSection={
                      isCurrentImageSelected ? <IconCheck size={16} /> : <IconPhoto size={16} />
                    }
                    onClick={handleSelectImage}
                    disabled={isCurrentImageSelected}
                    size="sm"
                  >
                    {isCurrentImageSelected ? 'Seleccionada' : 'Usar esta imagen'}
                  </Button>

                  <Tooltip label="Comparar: imagen izquierda (antes)">
                    <Button
                      variant={comparison?.left?.tile_url === result?.tile_url ? 'light' : 'outline'}
                      color="blue"
                      size="sm"
                      onClick={handleSetLeftImage}
                    >
                      Izquierda
                    </Button>
                  </Tooltip>

                  <Tooltip label="Comparar: imagen derecha (despues)">
                    <Button
                      variant={comparison?.right?.tile_url === result?.tile_url ? 'light' : 'outline'}
                      color="green"
                      size="sm"
                      onClick={handleSetRightImage}
                    >
                      Derecha
                    </Button>
                  </Tooltip>
                </Group>
              </Group>
            </Paper>
          )}
        </div>
      </div>

      {/* Historic floods */}
      {historicFloods.length > 0 && (
        <Paper p="md" withBorder radius="md">
          <Title order={5} mb="sm">
            <Group gap="xs">
              <IconPhoto size={20} />
              Escenas Historicas
            </Group>
          </Title>
          <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }}>
            {historicFloods.map((flood) => (
              <Card
                key={flood.id}
                padding="sm"
                radius="md"
                withBorder
                style={{ cursor: 'pointer' }}
                onClick={() => loadHistoricFlood(flood.id)}
              >
                <Group justify="space-between" mb="xs">
                  <Text fw={500}>{flood.name}</Text>
                  <Badge
                    color={
                      flood.severity === 'alta'
                        ? 'red'
                        : flood.severity === 'media'
                          ? 'orange'
                          : 'yellow'
                    }
                    size="sm"
                  >
                    {flood.severity}
                  </Badge>
                </Group>
                <Text size="sm" c="dimmed">
                  {flood.description}
                </Text>
                <Text size="xs" c="dimmed" mt="xs">
                  {flood.date}
                </Text>
              </Card>
            ))}
          </SimpleGrid>
        </Paper>
      )}

      {/* Currently selected image indicator */}
      {selectedImage && (
        <Paper p="sm" withBorder radius="md" bg="green.0">
          <Group justify="space-between">
            <Group gap="xs">
              <IconCheck size={18} color="var(--mantine-color-green-7)" />
              <Text size="sm" fw={500} c="green.7">
                Imagen activa en otras vistas:
              </Text>
              <Badge variant="light" color="green">
                {selectedImage.sensor} - {selectedImage.target_date}
              </Badge>
              <Text size="sm" c="dimmed">
                ({selectedImage.visualization_description})
              </Text>
            </Group>
            <Button
              variant="subtle"
              color="red"
              size="xs"
              leftSection={<IconX size={14} />}
              onClick={clearSelectedImage}
            >
              Quitar
            </Button>
          </Group>
        </Paper>
      )}

      {/* Comparison mode indicator */}
      {comparison && (
        <Paper p="sm" withBorder radius="md" bg="blue.0">
          <Group justify="space-between">
            <Group gap="md">
              <IconGitCompare size={18} color="var(--mantine-color-blue-7)" />
              <Text size="sm" fw={500} c="blue.7">
                Comparacion activa:
              </Text>
              <Group gap="xs">
                <Badge variant="light" color="blue">
                  {comparison.left?.target_date || 'Sin seleccionar'}
                </Badge>
                <Text size="sm" c="dimmed">
                  vs
                </Text>
                <Badge variant="light" color="green">
                  {comparison.right?.target_date || 'Sin seleccionar'}
                </Badge>
              </Group>
              {comparisonReady && (
                <Text size="xs" c="dimmed">
                  (Ve al Mapa para ver la comparacion)
                </Text>
              )}
            </Group>
            <Button
              variant="subtle"
              color="red"
              size="xs"
              leftSection={<IconX size={14} />}
              onClick={clearComparison}
            >
              Quitar
            </Button>
          </Group>
        </Paper>
      )}

      {/* Visualization legend */}
      <Paper p="sm" withBorder radius="md">
        <Group gap="lg" wrap="wrap">
          <Text size="sm" fw={500}>
            Visualizaciones:
          </Text>
          {sensor === 'sentinel2' ? (
            <Text size="sm" c="dimmed">
              RGB = Color natural | NDWI/MNDWI = Agua en azul | NDVI = Vegetacion en verde |
              Inundacion = Agua detectada
            </Text>
          ) : (
            <Text size="sm" c="dimmed">
              VV = Radar (oscuro=agua) | VV Flood = Deteccion de inundacion en cyan
            </Text>
          )}
        </Group>
      </Paper>
    </Stack>
  );
}
