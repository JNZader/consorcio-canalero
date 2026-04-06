/**
 * MapaMapLibre — 2D interactive map using MapLibre GL JS.
 *
 * Replaces MapaLeaflet.tsx with an imperative MapLibre map following the
 * EXACT same pattern as TerrainViewer3D.tsx: raw new maplibregl.Map({})
 * mounted in a useEffect, all data wired reactively via subsequent useEffects.
 *
 * Drop-in replacement: same external interface (no props — standalone component).
 * MapaInteractivo.tsx only needs a 1-line lazy import change to activate this.
 */

import {
  Badge,
  Box,
  Button,
  Center,
  Checkbox,
  CloseButton,
  ColorSwatch,
  Divider,
  Group,
  Loader,
  Menu,
  Modal,
  Paper,
  SegmentedControl,
  Select,
  Skeleton,
  Stack,
  Text,
  Textarea,
  TextInput,
  Title,
  Tooltip,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { notifications } from '@mantine/notifications';
import type { Feature, FeatureCollection, GeoJsonProperties, Geometry } from 'geojson';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { Protocol } from 'pmtiles';
import { memo, useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';

// Register PMTiles protocol once at module level
const _pmtilesProtocol = new Protocol();
maplibregl.addProtocol('pmtiles', _pmtilesProtocol.tile.bind(_pmtilesProtocol));
import { useApprovedZones } from '../hooks/useApprovedZones';
import { useBasins } from '../hooks/useBasins';
import { useCaminosColoreados, type ConsorcioInfo } from '../hooks/useCaminosColoreados';
import { useCatastroMap } from '../hooks/useCatastroMap';
import { GEE_LAYER_COLORS, useGEELayers } from '../hooks/useGEELayers';
import { buildTileUrl, GEO_LAYER_LABELS, useGeoLayers } from '../hooks/useGeoLayers';
import { useImageComparisonListener } from '../hooks/useImageComparison';
import { useInfrastructure } from '../hooks/useInfrastructure';
import { getMartinTileUrl, MARTIN_SOURCES, useZonaRiskColors } from '../hooks/useMartinLayers';
import { usePublicLayers } from '../hooks/usePublicLayers';
import { useSelectedImageListener } from '../hooks/useSelectedImage';
import { getSoilColor, useSoilMap } from '../hooks/useSoilMap';
import { useSuggestedZones } from '../hooks/useSuggestedZones';
import { useWaterways } from '../hooks/useWaterways';
import { API_URL, getAuthToken } from '../lib/api';
import { formatDate } from '../lib/formatters';
import { useCanAccess } from '../stores/authStore';
import { useConfigStore } from '../stores/configStore';
import { useMapLayerSyncStore } from '../stores/mapLayerSyncStore';
import { MAP_CENTER, MAP_DEFAULT_ZOOM } from '../constants';
import styles from '../styles/components/map.module.css';
import DrawControl, { type DrawControlHandle, type DrawnPolygon } from './map/DrawControl';
import LineDrawControl, { type DrawnLineFeatureCollection } from './map/LineDrawControl';
import { LAYER_LEGEND_CONFIG } from '../config/rasterLegend';
import { RasterLegend } from './RasterLegend';
import { IconGitCompare, IconLayers, IconPhoto, IconDownload, IconMap } from './ui/icons';

/* -------------------------------------------------------------------------- */
/*  Constants                                                                  */
/* -------------------------------------------------------------------------- */

// MapLibre note: center is [lng, lat] — opposite from Leaflet [lat, lng]
function leafletCenterToMapLibre(center: [number, number]): [number, number] {
  return [center[1], center[0]];
}

const DEFAULT_ZOOM = MAP_DEFAULT_ZOOM;

// IGN static overlay bounds
// Leaflet: [[-32.665914, -62.750969], [-32.44785, -62.345994]] = [[lat,lng],[lat,lng]]
// MapLibre image source needs 4 corners: NW, NE, SE, SW as [[lng,lat], ...]
const IGN_MAPLIBRE_COORDS: [[number, number], [number, number], [number, number], [number, number]] = [
  [-62.750969, -32.44785],   // NW: [lng, lat]
  [-62.345994, -32.44785],   // NE
  [-62.345994, -32.665914],  // SE
  [-62.750969, -32.665914],  // SW
];
const IGN_IMAGE_URL = '/overlays/ign/altimetria_ign_consorcio.webp';

// GEE layer names for the 2D map
const GEE_LAYER_NAMES = ['zona'] as const;

// Source/layer IDs
const WATERWAYS_SOURCE_ID = 'map2d-waterways';
const SOIL_SOURCE_ID = 'map2d-soil';
const CATASTRO_SOURCE_ID = 'map2d-catastro';
const ROADS_SOURCE_ID = 'map2d-roads';
const BASINS_SOURCE_ID = 'map2d-basins';
const APPROVED_ZONES_SOURCE_ID = 'map2d-approved-zones';
const SUGGESTED_ZONES_SOURCE_ID = 'map2d-suggested-zones';
const ZONA_SOURCE_ID = 'map2d-zona';
const INFRASTRUCTURE_SOURCE_ID = 'map2d-infrastructure';
const PUBLIC_LAYERS_SOURCE_PREFIX = 'map2d-public-';
const IGN_SOURCE_ID = 'map2d-ign-overlay';
const SATELLITE_IMAGE_SOURCE_ID = 'map2d-selected-image';
const COMPARISON_LEFT_SOURCE_ID = 'map2d-comparison-left';
const COMPARISON_RIGHT_SOURCE_ID = 'map2d-comparison-right';
const DEM_RASTER_SOURCE_ID = 'map2d-dem-raster';
const MARTIN_PUNTOS_SOURCE_ID = 'map2d-martin-puntos';
const MARTIN_CANALES_SOURCE_ID = 'map2d-martin-canales';

type ViewMode = 'base' | 'single' | 'comparison';

/* -------------------------------------------------------------------------- */
/*  Helpers                                                                    */
/* -------------------------------------------------------------------------- */

function asFeatureCollection(features: Feature[]): FeatureCollection {
  return { type: 'FeatureCollection', features };
}

function decorateFeature(
  feature: Feature<Geometry, GeoJsonProperties>,
  properties: GeoJsonProperties,
): Feature<Geometry, GeoJsonProperties> {
  return {
    ...feature,
    properties: { ...(feature.properties ?? {}), ...properties },
  };
}

/**
 * Upsert a GeoJSON source: setData if source exists, else addSource + addLayer.
 * Follows the exact same pattern as TerrainViewer3D.tsx.
 */
function ensureGeoJsonSource(
  map: maplibregl.Map,
  sourceId: string,
  data: FeatureCollection,
): void {
  const existing = map.getSource(sourceId) as maplibregl.GeoJSONSource | undefined;
  if (existing) {
    existing.setData(data);
  } else {
    map.addSource(sourceId, { type: 'geojson', data });
  }
}

function setLayerVisibility(map: maplibregl.Map, layerId: string, visible: boolean): void {
  if (map.getLayer(layerId)) {
    map.setLayoutProperty(layerId, 'visibility', visible ? 'visible' : 'none');
  }
}

function formatExportFilename(title: string, extension: 'png' | 'pdf') {
  const safeTitle =
    (title.trim() || 'mapa_consorcio')
      .toLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-z0-9]+/g, '_')
      .replace(/^_+|_+$/g, '') || 'mapa_consorcio';
  return `${safeTitle}_${new Date().toISOString().slice(0, 10)}.${extension}`;
}


/* -------------------------------------------------------------------------- */
/*  Sub-components (reused from original MapaLeaflet UI — no Leaflet deps)    */
/* -------------------------------------------------------------------------- */

function LegendItemIndicator({ item }: { item: { color: string; type: string } }) {
  if (item.type === 'border') {
    return (
      <Box className={styles.legendItemBorder} style={{ border: `2px solid ${item.color}` }} />
    );
  }
  if (item.type === 'line') {
    return <Box className={styles.legendItemLine} style={{ backgroundColor: item.color }} />;
  }
  return <ColorSwatch color={item.color} size={16} withShadow={false} />;
}

interface LeyendaProps {
  consorcios?: ConsorcioInfo[];
  customItems?: { color: string; label: string; type: string }[];
  floating?: boolean;
}

const Leyenda = memo(function Leyenda({
  consorcios = [],
  customItems = [],
  floating = true,
}: LeyendaProps) {
  const [showConsorcios, setShowConsorcios] = useState(false);

  const legendItems =
    customItems.length > 0
      ? customItems
      : [
            { color: '#FF0000', label: 'Zona Consorcio', type: 'border' },
          ];

  return (
    <Paper
      shadow="md"
      p="sm"
      radius="md"
      className={floating ? styles.legendPanel : undefined}
      style={
        floating
          ? { maxHeight: '80vh', overflowY: 'auto' }
          : {
              maxHeight: '80vh',
              overflowY: 'auto',
              background: 'light-dark(rgba(255,255,255,0.94), rgba(36,36,36,0.94))',
              backdropFilter: 'blur(6px)',
            }
      }
    >
      <Text fw={600} size="sm" mb="xs">
        Leyenda
      </Text>
      <Stack gap={4}>
        {legendItems.map((item) => (
          <Group key={item.label} gap="xs">
            <LegendItemIndicator item={item} />
            <Text size="xs">{item.label}</Text>
          </Group>
        ))}
        {consorcios.length > 0 && (
          <>
            <Divider my={4} />
            <Group
              gap="xs"
              style={{ cursor: 'pointer' }}
              onClick={() => setShowConsorcios(!showConsorcios)}
            >
              <Text fw={600} size="xs" c="dimmed">
                Red Vial ({consorcios.length} consorcios)
              </Text>
              <Text size="xs" c="dimmed">
                {showConsorcios ? '▼' : '►'}
              </Text>
            </Group>
            {showConsorcios && (
              <Stack gap={2} pl="xs">
                {consorcios.map((c) => (
                  <Group key={c.codigo} gap="xs" wrap="nowrap">
                    <Box
                      style={{
                        width: 16,
                        height: 3,
                        backgroundColor: c.color,
                        borderRadius: 1,
                      }}
                    />
                    <Text
                      size="xs"
                      truncate
                      style={{ maxWidth: 150 }}
                      title={`${c.nombre} - ${c.longitud_km} km`}
                    >
                      {c.codigo} ({c.longitud_km.toFixed(0)} km)
                    </Text>
                  </Group>
                ))}
              </Stack>
            )}
          </>
        )}
      </Stack>
    </Paper>
  );
});

interface InfoPanelProps {
  readonly feature: Feature | null;
  readonly onClose: () => void;
}

const InfoPanel = memo(function InfoPanel({ feature, onClose }: InfoPanelProps) {
  if (!feature) return null;
  const properties = feature.properties ?? {};
  return (
    <Paper shadow="md" p="md" radius="md" className={styles.infoPanel}>
      <Group justify="space-between" mb="xs">
        <Title order={5}>Informacion</Title>
        <CloseButton onClick={onClose} size="sm" aria-label="Cerrar panel de informacion" />
      </Group>
      <Divider mb="xs" />
      <Stack gap={4}>
        {Object.entries(properties)
          .filter(([key]) => !key.startsWith('__'))
          .map(([key, value]) => (
            <Group key={key} gap="xs" wrap="nowrap">
              <Badge size="xs" variant="light" color="gray">
                {key}
              </Badge>
              <Text size="xs" truncate>
                {String(value)}
              </Text>
            </Group>
          ))}
      </Stack>
    </Paper>
  );
});

interface ViewModePanelProps {
  readonly viewMode: ViewMode;
  readonly onViewModeChange: (mode: ViewMode) => void;
  readonly hasSingleImage: boolean;
  readonly hasComparison: boolean;
  readonly singleImageInfo?: { sensor: string; date: string } | null;
  readonly comparisonInfo?: { leftDate: string; rightDate: string } | null;
}

const ViewModePanel = memo(function ViewModePanel({
  viewMode,
  onViewModeChange,
  hasSingleImage,
  hasComparison,
  singleImageInfo,
  comparisonInfo,
}: ViewModePanelProps) {
  if (!hasSingleImage && !hasComparison) return null;

  const options = [
    {
      value: 'base',
      label: (
        <Tooltip label="Solo mapa base" position="bottom" withArrow>
          <Center style={{ gap: 6 }}>
            <IconLayers size={14} />
            <Text size="xs">Base</Text>
          </Center>
        </Tooltip>
      ),
    },
  ];

  if (hasSingleImage) {
    options.push({
      value: 'single',
      label: (
        <Tooltip
          label={singleImageInfo ? `${singleImageInfo.sensor} - ${singleImageInfo.date}` : 'Imagen satelital'}
          position="bottom"
          withArrow
        >
          <Center style={{ gap: 6 }}>
            <IconPhoto size={14} />
            <Text size="xs">Imagen</Text>
          </Center>
        </Tooltip>
      ),
    });
  }

  if (hasComparison) {
    options.push({
      value: 'comparison',
      label: (
        <Tooltip
          label={comparisonInfo ? `Comparar: ${comparisonInfo.leftDate} vs ${comparisonInfo.rightDate}` : 'Comparacion'}
          position="bottom"
          withArrow
        >
          <Center style={{ gap: 6 }}>
            <IconGitCompare size={14} />
            <Text size="xs">Comparar</Text>
          </Center>
        </Tooltip>
      ),
    });
  }

  return (
    <Paper
      shadow="md"
      p="xs"
      radius="md"
      style={{ background: 'light-dark(rgba(255,255,255,0.94), rgba(36,36,36,0.94))', backdropFilter: 'blur(6px)' }}
    >
      <Stack gap={4}>
        <Text size="xs" fw={600} c="dimmed">
          Vista satelital
        </Text>
        <SegmentedControl
          size="xs"
          fullWidth
          value={viewMode}
          onChange={(value) => onViewModeChange(value as ViewMode)}
          data={options}
        />
      </Stack>
    </Paper>
  );
});

/* -------------------------------------------------------------------------- */
/*  SuggestedZonesPanel (minimal — same as MapaLeaflet)                       */
/* -------------------------------------------------------------------------- */

interface SuggestedZonesPanelProps {
  readonly zones: Array<{
    id: string;
    defaultName: string;
    family?: string | null;
    basinCount: number;
    superficieHa: number;
  }>;
  readonly zoneNames: Record<string, string>;
  readonly onZoneNameChange: (zoneId: string, value: string) => void;
  readonly selectedBasinName: string | null;
  readonly selectedBasinZoneId: string | null;
  readonly destinationZoneId: string | null;
  readonly onDestinationZoneChange: (value: string | null) => void;
  readonly onApplyBasinMove: () => void;
  readonly hasApprovedZones: boolean;
  readonly approvedAt: string | null;
  readonly approvedVersion: number | null;
  readonly approvedZonesHistory: Array<{
    id: string;
    nombre: string;
    version: number;
    approvedAt: string;
    notes?: string | null;
    approvedByName?: string | null;
  }>;
  readonly approvalName: string;
  readonly approvalNotes: string;
  readonly onApprovalNameChange: (value: string) => void;
  readonly onApprovalNotesChange: (value: string) => void;
  readonly onClose: () => void;
  readonly onApproveZones: () => void;
  readonly onClearApprovedZones: () => void;
  readonly onRestoreVersion: (id: string) => void;
  readonly onExportApprovedZonesGeoJSON: () => void;
  readonly onExportApprovedZonesPdf: () => void;
}

const SuggestedZonesPanel = memo(function SuggestedZonesPanel({
  zones,
  zoneNames,
  onZoneNameChange,
  selectedBasinName,
  selectedBasinZoneId,
  destinationZoneId,
  onDestinationZoneChange,
  onApplyBasinMove,
  hasApprovedZones,
  approvedAt,
  approvedVersion,
  approvedZonesHistory,
  approvalName,
  approvalNotes,
  onApprovalNameChange,
  onApprovalNotesChange,
  onClose,
  onApproveZones,
  onClearApprovedZones,
  onRestoreVersion,
  onExportApprovedZonesGeoJSON,
  onExportApprovedZonesPdf,
}: SuggestedZonesPanelProps) {
  if (zones.length === 0) return null;

  const zoneOptions = zones.map((zone) => ({
    value: zone.id,
    label: zoneNames[zone.id] ?? zone.defaultName,
  }));

  return (
    <Paper
      shadow="md"
      p="sm"
      radius="md"
      style={{
        position: 'absolute',
        top: 64,
        left: 12,
        zIndex: 16,
        width: 340,
        maxHeight: 'calc(100% - 80px)',
        overflowY: 'auto',
        background: 'light-dark(rgba(255,255,255,0.96), rgba(36,36,36,0.96))',
        backdropFilter: 'blur(6px)',
      }}
    >
      <Stack gap="xs">
        <Box>
          <Group justify="space-between" align="flex-start" wrap="nowrap">
            <Box style={{ flex: 1 }}>
              <Text size="sm" fw={600}>
                {hasApprovedZones ? 'Zonificación aprobada' : 'Zonas sugeridas'}
              </Text>
            </Box>
            <CloseButton size="sm" onClick={onClose} aria-label="Cerrar panel de zonificación" />
          </Group>
        </Box>

        <Divider />

        {!hasApprovedZones && (
          <>
            <Box>
              <Text size="xs" fw={600} mb={4}>
                Reasignar subcuenca
              </Text>
              <Stack gap={6}>
                <Text size="xs">
                  Subcuenca seleccionada: <b>{selectedBasinName || 'Ninguna'}</b>
                </Text>
                <Text size="xs" c="dimmed">
                  Zona actual:{' '}
                  {selectedBasinZoneId
                    ? (zoneNames[selectedBasinZoneId] ?? selectedBasinZoneId)
                    : '-'}
                </Text>
                <Select
                  size="xs"
                  placeholder="Elegir zona destino"
                  data={zoneOptions}
                  value={destinationZoneId}
                  onChange={onDestinationZoneChange}
                  nothingFoundMessage="Sin zonas"
                />
                <Button
                  size="xs"
                  variant="light"
                  disabled={
                    !selectedBasinName ||
                    !destinationZoneId ||
                    destinationZoneId === selectedBasinZoneId
                  }
                  onClick={onApplyBasinMove}
                >
                  Mover subcuenca a esta zona
                </Button>
              </Stack>
            </Box>
            <Divider />
          </>
        )}

        <Box>
          <Group justify="space-between" align="center" mb={4}>
            <Text size="xs" fw={600}>
              Estado
            </Text>
            {hasApprovedZones ? (
              <Badge size="xs" color="green" variant="light">Aprobada</Badge>
            ) : (
              <Badge size="xs" color="yellow" variant="light">Draft</Badge>
            )}
          </Group>
          <Text size="xs" c="dimmed" mb={6}>
            {hasApprovedZones && approvedAt
              ? `Versión actual: v${approvedVersion ?? '-'} • Última aprobación: ${new Date(approvedAt).toLocaleString()}`
              : 'Todavía no hay una zonificación aprobada persistida.'}
          </Text>
          <Stack gap={6} mb={8}>
            <TextInput
              size="xs"
              label="Nombre de versión"
              placeholder="Ej. Zonificación operativa marzo 2026"
              value={approvalName}
              onChange={(event) => onApprovalNameChange(event.currentTarget.value)}
            />
            <Textarea
              size="xs"
              label="Comentario"
              placeholder="Resumen corto del cambio aprobado"
              minRows={2}
              autosize
              value={approvalNotes}
              onChange={(event) => onApprovalNotesChange(event.currentTarget.value)}
            />
          </Stack>
          <Group grow>
            <Button size="xs" color="green" onClick={onApproveZones}>
              Aprobar esta zonificación
            </Button>
            {hasApprovedZones && (
              <Button size="xs" variant="light" color="gray" onClick={onClearApprovedZones}>
                Limpiar aprobada
              </Button>
            )}
          </Group>
          {hasApprovedZones && (
            <Group grow mt={8}>
              <Button size="xs" variant="light" leftSection={<IconDownload size={14} />} onClick={onExportApprovedZonesGeoJSON}>
                GeoJSON
              </Button>
              <Button size="xs" variant="light" leftSection={<IconDownload size={14} />} onClick={onExportApprovedZonesPdf}>
                PDF
              </Button>
            </Group>
          )}
        </Box>

        {!hasApprovedZones && (
          <>
            <Divider />
            <Stack gap={6}>
              {zones.map((zone) => (
                <Paper key={zone.id} withBorder p="xs" radius="sm">
                  <Stack gap={4}>
                    <TextInput
                      size="xs"
                      label={zone.defaultName}
                      value={zoneNames[zone.id] ?? zone.defaultName}
                      onChange={(event) => onZoneNameChange(zone.id, event.currentTarget.value)}
                    />
                    <Text size="xs" c="dimmed">
                      Familia: {zone.family || '-'} • Subcuencas: {zone.basinCount} • Sup:{' '}
                      {zone.superficieHa.toFixed(1)} ha
                    </Text>
                  </Stack>
                </Paper>
              ))}
            </Stack>
          </>
        )}

        {approvedZonesHistory.length > 0 && (
          <>
            <Divider />
            <Box>
              <Text size="xs" fw={600} mb={6}>
                Historial de versiones
              </Text>
              <Stack gap={6}>
                {approvedZonesHistory.map((item) => (
                  <Paper key={item.id} withBorder p="xs" radius="sm">
                    <Group justify="space-between" align="flex-start" wrap="nowrap">
                      <Stack gap={2} style={{ flex: 1 }}>
                        <Text size="xs" fw={600}>
                          v{item.version} — {item.nombre}
                        </Text>
                        <Text size="xs" c="dimmed">
                          {new Date(item.approvedAt).toLocaleString()}
                        </Text>
                        {item.approvedByName && (
                          <Text size="xs" c="dimmed">Aprobó: {item.approvedByName}</Text>
                        )}
                        {item.notes && (
                          <Text size="xs" c="dimmed">{item.notes}</Text>
                        )}
                      </Stack>
                      {approvedVersion !== item.version && (
                        <Button size="xs" variant="light" onClick={() => onRestoreVersion(item.id)}>
                          Restaurar
                        </Button>
                      )}
                    </Group>
                  </Paper>
                ))}
              </Stack>
            </Box>
          </>
        )}
      </Stack>
    </Paper>
  );
});

/* -------------------------------------------------------------------------- */
/*  Main component                                                             */
/* -------------------------------------------------------------------------- */

export default function MapaMapLibre() {
  // ── Config & auth ─────────────────────────────────────────────────────────
  const config = useConfigStore((state) => state.config);
  const isOperator = useCanAccess(['admin', 'operador']);
  const canManageZoning = useCanAccess(['admin', 'operador']);
  const _mapInstanceId = useId();

  const center = useMemo<[number, number]>(
    () =>
      config?.map.center
        ? leafletCenterToMapLibre([config.map.center.lat, config.map.center.lng])
        : leafletCenterToMapLibre(MAP_CENTER),
    [config?.map.center?.lat, config?.map.center?.lng],
  );
  const zoom = useMemo(() => config?.map.zoom ?? DEFAULT_ZOOM, [config?.map.zoom]);

  // ── Map refs ──────────────────────────────────────────────────────────────
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [mapReady, setMapReady] = useState(false);

  // Comparison slider
  const sliderContainerRef = useRef<HTMLDivElement>(null);
  const [sliderPosition, setSliderPosition] = useState(50);
  const isDraggingSlider = useRef(false);

  // Draw control refs
  const drawControlRef = useRef<DrawControlHandle | null>(null);

  // ── UI state ──────────────────────────────────────────────────────────────
  const [selectedFeature, setSelectedFeature] = useState<Feature | null>(null);
  const [baseLayer, setBaseLayer] = useState<'osm' | 'satellite'>('osm');
  const [viewMode, setViewMode] = useState<ViewMode>('base');
  const [showLegend, setShowLegend] = useState(true);
  const [showSuggestedZonesPanel, setShowSuggestedZonesPanel] = useState(false);
  const [showIGNOverlay, setShowIGNOverlay] = useState(false);
  const [showDemOverlay, setShowDemOverlay] = useState(false);
  const [activeDemLayerId, setActiveDemLayerId] = useState<string | null>(null);
  const [markingMode, setMarkingMode] = useState(false);
  const [newPoint, setNewPoint] = useState<{ lat: number; lng: number } | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [captureMode, setCaptureMode] = useState(false);
  const [exportPngModalOpen, setExportPngModalOpen] = useState(false);
  const [exportIncludeLegend, setExportIncludeLegend] = useState(true);
  const [exportIncludeMetadata, setExportIncludeMetadata] = useState(true);
  const [exportTitle, setExportTitle] = useState('Mapa del Consorcio');
  const [approvalName, setApprovalName] = useState('Zonificación Consorcio aprobada');
  const [approvalNotes, setApprovalNotes] = useState('');
  const [suggestedZoneNames, setSuggestedZoneNames] = useState<Record<string, string>>({});
  const [draftBasinAssignments, setDraftBasinAssignments] = useState<Record<string, string>>({});
  const [selectedDraftBasinId, setSelectedDraftBasinId] = useState<string | null>(null);
  const [draftDestinationZoneId, setDraftDestinationZoneId] = useState<string | null>(null);
  const [drawnPolygon, setDrawnPolygon] = useState<DrawnPolygon | null>(null);
  const [drawnLine, setDrawnLine] = useState<DrawnLineFeatureCollection | null>(null);
  const [hiddenClasses, setHiddenClasses] = useState<Record<string, number[]>>({});
  const [hiddenRanges, setHiddenRanges] = useState<Record<string, number[]>>({});
  const [visibleRasterLayers, setVisibleRasterLayers] = useState<Array<{ tipo: string }>>([]);

  const form = useForm({
    initialValues: { nombre: '', tipo: 'alcantarilla', descripcion: '', cuenca: '' },
    validate: { nombre: (value) => (value.length < 3 ? 'Nombre demasiado corto' : null) },
  });

  // ── Layer sync store ──────────────────────────────────────────────────────
  const sharedVisibleVectors = useMapLayerSyncStore((state) => state.map2d.visibleVectors);
  const setSharedVectorVisibility = useMapLayerSyncStore((state) => state.setVectorVisibility);
  const setSharedActiveRasterType = useMapLayerSyncStore((state) => state.setActiveRasterType);
  const is2DViewInitialized = useMapLayerSyncStore((state) => state.initializedViews.map2d);
  const hydrateSharedViewState = useMapLayerSyncStore((state) => state.hydrateViewState);

  // Local visibility state (mirrors sharedVisibleVectors, drives setLayoutProperty)
  const [vectorVisibility, setVectorVisibility] = useState<Record<string, boolean>>(
    () => sharedVisibleVectors,
  );

  // Sync from shared store → local
  useEffect(() => {
    setVectorVisibility(sharedVisibleVectors);
  }, [sharedVisibleVectors]);

  const toggleLayer = useCallback(
    (layerId: string, visible: boolean) => {
      setVectorVisibility((prev) => ({ ...prev, [layerId]: visible }));
      setSharedVectorVisibility('map2d', layerId, visible);
    },
    [setSharedVectorVisibility],
  );

  // ── Data hooks ────────────────────────────────────────────────────────────
  const { layers: capas } = useGEELayers({ layerNames: [...GEE_LAYER_NAMES] });
  const { caminos, consorcios } = useCaminosColoreados();
  const { assets, intersections, createAsset } = useInfrastructure();
  const { layers: publicLayers } = usePublicLayers();
  const { soilMap } = useSoilMap();
  const { catastroMap } = useCatastroMap();
  const { basins } = useBasins();
  const { suggestedZones } = useSuggestedZones();
  const { waterways } = useWaterways();
  const { layers: allGeoLayers } = useGeoLayers();
  const { data: zonaRiskColors = {} } = useZonaRiskColors();
  const {
    approvedZones,
    approvedAt,
    approvedVersion,
    hasApprovedZones,
    approvedZonesHistory,
    saveApprovedZones,
    clearApprovedZones,
    restoreApprovedZonesVersion,
  } = useApprovedZones();

  const selectedImage = useSelectedImageListener();
  const comparison = useImageComparisonListener();

  // ── Derived data (same decoration pattern as TerrainViewer3D) ────────────

  const zonaCollection = capas.zona ?? null;


  const roadsCollection = caminos;

  const waterwaysCollection = useMemo((): FeatureCollection | null => {
    const features = waterways.flatMap((layer) =>
      layer.data.features.map((f) =>
        decorateFeature(f, { __color: layer.style.color ?? '#1565C0', __label: layer.nombre }),
      ),
    );
    return features.length > 0 ? asFeatureCollection(features) : null;
  }, [waterways]);

  const soilCollection = useMemo((): FeatureCollection | null => {
    if (!soilMap) return null;
    return asFeatureCollection(
      soilMap.features.map((f) =>
        decorateFeature(f, { __color: getSoilColor((f.properties as { cap?: string | null } | null)?.cap) }),
      ),
    );
  }, [soilMap]);

  const infrastructureCollection = useMemo((): FeatureCollection | null => {
    const features = assets.map((asset) => {
      const color =
        asset.tipo === 'puente' ? '#f03e3e'
          : asset.tipo === 'alcantarilla' ? '#1971c2'
            : asset.tipo === 'canal' ? '#2f9e44'
              : '#fd7e14';
      return {
        type: 'Feature' as const,
        geometry: { type: 'Point' as const, coordinates: [asset.longitud, asset.latitud] },
        properties: { ...asset, __color: color },
      };
    });
    return features.length > 0 ? asFeatureCollection(features) : null;
  }, [assets]);

  const approvedZonesCollection = approvedZones;

  const suggestedZonesDisplay = useMemo((): FeatureCollection | null => {
    if (!basins) return null;
    return {
      type: 'FeatureCollection',
      features: basins.features
        .filter((f) => f.properties?.draft_zone_id)
        .map((f) => {
          const zoneId = String(f.properties?.draft_zone_id ?? '');
          const effectiveZoneId = draftBasinAssignments[String(f.properties?.id ?? '')] ?? zoneId;
          const colors: Record<string, string> = {
            Norte: '#9C27B0',
            'Monte Leña': '#4CAF50',
            Candil: '#2196F3',
          };
          const zoneName = suggestedZoneNames[effectiveZoneId] ?? String(f.properties?.nombre ?? effectiveZoneId);
          const color = colors[zoneName] ?? '#1971c2';
          return decorateFeature(f, { __color: color, __zone_id: effectiveZoneId });
        }),
    };
  }, [basins, draftBasinAssignments, suggestedZoneNames]);

  // DEM tile URL
  const demTileUrl = useMemo(() => {
    if (!activeDemLayerId) return null;
    const layer = allGeoLayers.find((l) => l.id === activeDemLayerId);
    if (!layer) return null;
    return buildTileUrl(layer.id, {
      hideClasses: (hiddenClasses[layer.tipo] ?? []).length > 0 ? hiddenClasses[layer.tipo] : undefined,
      hideRanges: (hiddenRanges[layer.tipo] ?? []).length > 0 ? hiddenRanges[layer.tipo] : undefined,
    });
  }, [activeDemLayerId, allGeoLayers, hiddenClasses, hiddenRanges]);

  const COMPOSITE_TYPES = useMemo(() => new Set(['flood_risk', 'drainage_need']), []);
  const demLayers = useMemo(() => allGeoLayers.filter((l) => !COMPOSITE_TYPES.has(l.tipo)), [allGeoLayers, COMPOSITE_TYPES]);

  // Suggested zone summaries (for panel)
  const initialDraftAssignments = useMemo(() => {
    const mapping: Record<string, string> = {};
    for (const feature of suggestedZones?.features ?? []) {
      const zoneId = String(feature.properties?.draft_zone_id || '');
      const memberIds = Array.isArray(feature.properties?.member_basin_ids)
        ? (feature.properties?.member_basin_ids as unknown[])
        : [];
      for (const basinId of memberIds) {
        if (typeof basinId === 'string' && zoneId) mapping[basinId] = zoneId;
      }
    }
    return mapping;
  }, [suggestedZones]);

  const zoneDefinitionById = useMemo(() => {
    const mapping: Record<string, { defaultName: string; family: string | null; color: string }> = {};
    for (const feature of suggestedZones?.features ?? []) {
      const zoneId = String(feature.properties?.draft_zone_id || '');
      if (!zoneId) continue;
      mapping[zoneId] = {
        defaultName: String(feature.properties?.nombre || 'Zona sugerida'),
        family: (feature.properties?.family as string | undefined) ?? null,
        color: (feature.properties?.__color as string | undefined) || '#1971c2',
      };
    }
    return mapping;
  }, [suggestedZones]);

  const basinFeatureById = useMemo(() => {
    const mapping: Record<string, Feature> = {};
    for (const feature of basins?.features ?? []) {
      const basinId = feature.properties?.id;
      if (typeof basinId === 'string') mapping[basinId] = feature as Feature;
    }
    return mapping;
  }, [basins]);

  const effectiveBasinAssignments = useMemo(
    () => ({ ...initialDraftAssignments, ...draftBasinAssignments }),
    [draftBasinAssignments, initialDraftAssignments],
  );

  const suggestedZoneSummaries = useMemo(() => {
    return Object.entries(zoneDefinitionById).map(([zoneId, zoneDef]) => {
      let basinCount = 0;
      let superficieHa = 0;
      for (const [basinId, assignedZoneId] of Object.entries(effectiveBasinAssignments)) {
        if (assignedZoneId !== zoneId) continue;
        basinCount += 1;
        superficieHa += Number(basinFeatureById[basinId]?.properties?.superficie_ha || 0);
      }
      return { id: zoneId, defaultName: zoneDef.defaultName, family: zoneDef.family, basinCount, superficieHa };
    });
  }, [basinFeatureById, effectiveBasinAssignments, zoneDefinitionById]);

  const selectedDraftBasinName = useMemo(() => {
    if (!selectedDraftBasinId) return null;
    const feature = basinFeatureById[selectedDraftBasinId];
    return feature?.properties?.nombre ? String(feature.properties.nombre) : selectedDraftBasinId;
  }, [basinFeatureById, selectedDraftBasinId]);

  const selectedDraftBasinZoneId = useMemo(
    () => (selectedDraftBasinId ? (effectiveBasinAssignments[selectedDraftBasinId] ?? null) : null),
    [selectedDraftBasinId, effectiveBasinAssignments],
  );

  const activeLegendItems = useMemo(() => {
    if (!hasApprovedZones || !approvedZones) return [];
    return approvedZones.features.map((feature) => ({
      color: (feature.properties?.__color as string | undefined) || '#1971c2',
      label: String(feature.properties?.nombre || 'Zona aprobada'),
      type: 'fill',
    }));
  }, [approvedZones, hasApprovedZones]);

  // Auto-activate comparison when comparison state changes
  useEffect(() => {
    if (comparison?.enabled && comparison.left && comparison.right) {
      setViewMode('comparison');
    }
  }, [comparison]);

  // Auto-activate single image view when image loads
  useEffect(() => {
    if (selectedImage && viewMode === 'base') {
      setViewMode('single');
    }
  }, [selectedImage]);

  /* ---------------------------------------------------------------------- */
  /*  Map initialization — Task 2.1                                          */
  /* ---------------------------------------------------------------------- */
  useEffect(() => {
    if (!containerRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: {
        version: 8,
        sources: {
          'osm-base': {
            type: 'raster',
            tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
            tileSize: 256,
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
            maxzoom: 19,
          },
          'satellite-base': {
            type: 'raster',
            tiles: [
              'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            ],
            tileSize: 256,
            attribution: '&copy; Esri',
          },
        },
        layers: [
          {
            id: 'osm-tiles',
            type: 'raster',
            source: 'osm-base',
            layout: { visibility: 'visible' },
            paint: { 'raster-opacity': 1 },
          },
          {
            id: 'satellite-tiles',
            type: 'raster',
            source: 'satellite-base',
            layout: { visibility: 'none' },
            paint: { 'raster-opacity': 1 },
          },
        ],
      },
      center: center,
      zoom: zoom,
    });

    map.addControl(new maplibregl.NavigationControl(), 'top-right');
    map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-left');

    map.on('load', () => {
      setMapReady(true);
    });

    map.on('error', (event) => {
      const msg =
        typeof event.error === 'string'
          ? event.error
          : event.error instanceof Error
            ? event.error.message
            : '';
      const isTileError =
        'tile' in event ||
        /AJAXError/i.test(msg) ||
        /earthengine\.googleapis\.com/i.test(msg);
      if (!isTileError) {
        console.error('MapaMapLibre error:', event.error);
      }
    });

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
      setMapReady(false);
    };
    // center and zoom intentionally excluded — we don't remount on config change
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ---------------------------------------------------------------------- */
  /*  Base layer switching — Task 2.2                                        */
  /* ---------------------------------------------------------------------- */
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    setLayerVisibility(map, 'osm-tiles', baseLayer === 'osm');
    setLayerVisibility(map, 'satellite-tiles', baseLayer === 'satellite');
  }, [baseLayer, mapReady]);

  /* ---------------------------------------------------------------------- */
  /*  GeoJSON vector layers — Tasks 2.3, 2.4, 2.5                           */
  /* ---------------------------------------------------------------------- */
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;

    // ── Waterways (PMTiles — multi-source, one layer per file) ────────────
    const waterwayFiles = [
      { id: `${WATERWAYS_SOURCE_ID}-rio-tercero`,        url: 'pmtiles:///waterways/rio_tercero.pmtiles',        layer: 'rio_tercero',        color: '#1565C0' },
      { id: `${WATERWAYS_SOURCE_ID}-arroyo-algodon`,     url: 'pmtiles:///waterways/arroyo_algodon.pmtiles',     layer: 'arroyo_algodon',     color: '#1976D2' },
      { id: `${WATERWAYS_SOURCE_ID}-canal-desviador`,    url: 'pmtiles:///waterways/canal_desviador.pmtiles',    layer: 'canal_desviador',    color: '#0288D1' },
      { id: `${WATERWAYS_SOURCE_ID}-canal-litin`,        url: 'pmtiles:///waterways/canal_litin_tortugas.pmtiles', layer: 'canal_litin_tortugas', color: '#039BE5' },
      { id: `${WATERWAYS_SOURCE_ID}-canales-existentes`, url: 'pmtiles:///waterways/canales_existentes.pmtiles', layer: 'canales_existentes', color: '#2196F3' },
      { id: `${WATERWAYS_SOURCE_ID}-arroyo-mojarras`,    url: 'pmtiles:///waterways/arroyo_las_mojarras.pmtiles', layer: 'arroyo_las_mojarras', color: '#42A5F5' },
    ];
    for (const wf of waterwayFiles) {
      if (!map.getSource(wf.id)) {
        map.addSource(wf.id, { type: 'vector', url: wf.url });
      }
      const lineLayerId = `${wf.id}-line`;
      if (!map.getLayer(lineLayerId)) {
        map.addLayer({
          id: lineLayerId,
          type: 'line',
          source: wf.id,
          'source-layer': wf.layer,
          paint: {
            'line-color': wf.color,
            'line-width': 3,
            'line-opacity': 0.9,
          },
        });
      }
      setLayerVisibility(map, lineLayerId, !!vectorVisibility.waterways);
    }
  }, [mapReady, vectorVisibility.waterways]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;

    // ── Soil (PMTiles) ─────────────────────────────────────────────────────
    if (!map.getSource(SOIL_SOURCE_ID)) {
      map.addSource(SOIL_SOURCE_ID, {
        type: 'vector',
        url: 'pmtiles:///data/suelos_cu.pmtiles',
      });
    }
    if (!map.getLayer(`${SOIL_SOURCE_ID}-fill`)) {
      map.addLayer({
        id: `${SOIL_SOURCE_ID}-fill`,
        type: 'fill',
        source: SOIL_SOURCE_ID,
        'source-layer': 'suelos_cu',
        paint: {
          'fill-color': [
            'match', ['get', 'cap'],
            'I', '#1b5e20', 'II', '#2e7d32', 'III', '#689f38', 'IV', '#c0ca33',
            'V', '#f9a825', 'VI', '#fb8c00', 'VII', '#ef6c00', 'VIII', '#c62828',
            '#8d6e63',
          ],
          'fill-opacity': 0.45,
        },
      });
    }
    if (!map.getLayer(`${SOIL_SOURCE_ID}-line`)) {
      map.addLayer({
        id: `${SOIL_SOURCE_ID}-line`,
        type: 'line',
        source: SOIL_SOURCE_ID,
        'source-layer': 'suelos_cu',
        paint: { 'line-color': '#6d4c41', 'line-width': 0.8, 'line-opacity': 0.55 },
      });
    }
    setLayerVisibility(map, `${SOIL_SOURCE_ID}-fill`, !!vectorVisibility.soil);
    setLayerVisibility(map, `${SOIL_SOURCE_ID}-line`, !!vectorVisibility.soil);
  }, [mapReady, vectorVisibility.soil]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;

    // ── Catastro (PMTiles) ─────────────────────────────────────────────────
    if (!map.getSource(CATASTRO_SOURCE_ID)) {
      map.addSource(CATASTRO_SOURCE_ID, {
        type: 'vector',
        url: 'pmtiles:///data/catastro_rural_cu.pmtiles',
      });
    }
    // Transparent fill first so parcelas are clickable, then line on top
    if (!map.getLayer(`${CATASTRO_SOURCE_ID}-fill`)) {
      map.addLayer({
        id: `${CATASTRO_SOURCE_ID}-fill`,
        type: 'fill',
        source: CATASTRO_SOURCE_ID,
        'source-layer': 'catastro_rural_cu',
        paint: { 'fill-color': '#ffffff', 'fill-opacity': 0.01 },
      });
    }
    if (!map.getLayer(`${CATASTRO_SOURCE_ID}-line`)) {
      map.addLayer({
        id: `${CATASTRO_SOURCE_ID}-line`,
        type: 'line',
        source: CATASTRO_SOURCE_ID,
        'source-layer': 'catastro_rural_cu',
        paint: { 'line-color': '#f8f9fa', 'line-width': 0.7, 'line-opacity': 0.7 },
      });
    }
    setLayerVisibility(map, `${CATASTRO_SOURCE_ID}-fill`, !!vectorVisibility.catastro);
    setLayerVisibility(map, `${CATASTRO_SOURCE_ID}-line`, !!vectorVisibility.catastro);
  }, [mapReady, vectorVisibility.catastro]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;

    // ── Caminos (roads) ────────────────────────────────────────────────────
    ensureGeoJsonSource(map, ROADS_SOURCE_ID, roadsCollection ?? asFeatureCollection([]));
    if (!map.getLayer(`${ROADS_SOURCE_ID}-line`)) {
      map.addLayer({
        id: `${ROADS_SOURCE_ID}-line`,
        type: 'line',
        source: ROADS_SOURCE_ID,
        paint: {
          'line-color': ['coalesce', ['get', 'color'], '#FFEB3B'],
          'line-width': 2,
          'line-opacity': 0.9,
        },
      });
    }
    setLayerVisibility(map, `${ROADS_SOURCE_ID}-line`, !!vectorVisibility.roads && !!roadsCollection);
  }, [mapReady, roadsCollection, vectorVisibility.roads]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;

    // ── Basins (zonas operativas / subcuencas PostGIS) ─────────────────────
    ensureGeoJsonSource(map, BASINS_SOURCE_ID, basins ?? asFeatureCollection([]));
    if (!map.getLayer(`${BASINS_SOURCE_ID}-fill`)) {
      map.addLayer({
        id: `${BASINS_SOURCE_ID}-fill`,
        type: 'fill',
        source: BASINS_SOURCE_ID,
        paint: { 'fill-color': '#00897B', 'fill-opacity': 0.08 },
      });
    }
    if (!map.getLayer(`${BASINS_SOURCE_ID}-line`)) {
      map.addLayer({
        id: `${BASINS_SOURCE_ID}-line`,
        type: 'line',
        source: BASINS_SOURCE_ID,
        paint: { 'line-color': '#00897B', 'line-width': 1.5, 'line-opacity': 0.95 },
      });
    }
    setLayerVisibility(map, `${BASINS_SOURCE_ID}-fill`, !!vectorVisibility.basins && !!basins);
    setLayerVisibility(map, `${BASINS_SOURCE_ID}-line`, !!vectorVisibility.basins && !!basins);
  }, [mapReady, basins, vectorVisibility.basins]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;

    // ── Zona consorcio (manual histórica de GEE) ───────────────────────────
    ensureGeoJsonSource(map, ZONA_SOURCE_ID, zonaCollection ?? asFeatureCollection([]));
    if (!map.getLayer(`${ZONA_SOURCE_ID}-line`)) {
      map.addLayer({
        id: `${ZONA_SOURCE_ID}-line`,
        type: 'line',
        source: ZONA_SOURCE_ID,
        paint: { 'line-color': '#FF0000', 'line-width': 3, 'line-opacity': 0.95 },
      });
    }
    // Zona consorcio is always visible — not user-toggleable
    setLayerVisibility(map, `${ZONA_SOURCE_ID}-line`, !!zonaCollection);
  }, [mapReady, zonaCollection]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;

    // ── Approved zones ─────────────────────────────────────────────────────
    ensureGeoJsonSource(map, APPROVED_ZONES_SOURCE_ID, approvedZonesCollection ?? asFeatureCollection([]));
    if (!map.getLayer(`${APPROVED_ZONES_SOURCE_ID}-fill`)) {
      map.addLayer({
        id: `${APPROVED_ZONES_SOURCE_ID}-fill`,
        type: 'fill',
        source: APPROVED_ZONES_SOURCE_ID,
        paint: {
          'fill-color': ['coalesce', ['get', '__color'], '#1971c2'],
          'fill-opacity': 0.18,
        },
      });
    }
    if (!map.getLayer(`${APPROVED_ZONES_SOURCE_ID}-line`)) {
      map.addLayer({
        id: `${APPROVED_ZONES_SOURCE_ID}-line`,
        type: 'line',
        source: APPROVED_ZONES_SOURCE_ID,
        paint: {
          'line-color': ['coalesce', ['get', '__color'], '#1971c2'],
          'line-width': 3,
          'line-opacity': 0.95,
        },
      });
    }
    setLayerVisibility(map, `${APPROVED_ZONES_SOURCE_ID}-fill`, !!vectorVisibility.approved_zones && !!approvedZonesCollection);
    setLayerVisibility(map, `${APPROVED_ZONES_SOURCE_ID}-line`, !!vectorVisibility.approved_zones && !!approvedZonesCollection);
  }, [mapReady, approvedZonesCollection, vectorVisibility.approved_zones]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;

    // ── Suggested zones (draft) ────────────────────────────────────────────
    ensureGeoJsonSource(map, SUGGESTED_ZONES_SOURCE_ID, suggestedZonesDisplay ?? asFeatureCollection([]));
    if (!map.getLayer(`${SUGGESTED_ZONES_SOURCE_ID}-fill`)) {
      map.addLayer({
        id: `${SUGGESTED_ZONES_SOURCE_ID}-fill`,
        type: 'fill',
        source: SUGGESTED_ZONES_SOURCE_ID,
        paint: {
          'fill-color': ['coalesce', ['get', '__color'], '#1971c2'],
          'fill-opacity': 0.15,
        },
      });
    }
    if (!map.getLayer(`${SUGGESTED_ZONES_SOURCE_ID}-line`)) {
      map.addLayer({
        id: `${SUGGESTED_ZONES_SOURCE_ID}-line`,
        type: 'line',
        source: SUGGESTED_ZONES_SOURCE_ID,
        paint: {
          'line-color': ['coalesce', ['get', '__color'], '#1971c2'],
          'line-width': 2,
          'line-opacity': 0.9,
          'line-dasharray': [4, 4],
        },
      });
    }
    // Suggested zones visible when the panel is open and there are no approved zones
    const showSuggested = showSuggestedZonesPanel && !hasApprovedZones && !!suggestedZonesDisplay;
    setLayerVisibility(map, `${SUGGESTED_ZONES_SOURCE_ID}-fill`, showSuggested);
    setLayerVisibility(map, `${SUGGESTED_ZONES_SOURCE_ID}-line`, showSuggested);
  }, [mapReady, suggestedZonesDisplay, showSuggestedZonesPanel, hasApprovedZones]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;

    // ── Infrastructure points ──────────────────────────────────────────────
    ensureGeoJsonSource(map, INFRASTRUCTURE_SOURCE_ID, infrastructureCollection ?? asFeatureCollection([]));
    if (!map.getLayer(`${INFRASTRUCTURE_SOURCE_ID}-circle`)) {
      map.addLayer({
        id: `${INFRASTRUCTURE_SOURCE_ID}-circle`,
        type: 'circle',
        source: INFRASTRUCTURE_SOURCE_ID,
        paint: {
          'circle-color': ['coalesce', ['get', '__color'], '#fd7e14'],
          'circle-radius': 6,
          'circle-opacity': 0.95,
          'circle-stroke-color': '#ffffff',
          'circle-stroke-width': 1.5,
        },
      });
    }
    setLayerVisibility(map, `${INFRASTRUCTURE_SOURCE_ID}-circle`, !!vectorVisibility.infrastructure && !!infrastructureCollection);
  }, [mapReady, infrastructureCollection, vectorVisibility.infrastructure]);

  /* ---------------------------------------------------------------------- */
  /*  Public layers (dynamic — varies per layer tipo) — Task 2.5            */
  /* ---------------------------------------------------------------------- */
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;

    for (const layer of publicLayers) {
      if (!layer.geojson_data) continue;
      const sourceId = `${PUBLIC_LAYERS_SOURCE_PREFIX}${layer.id}`;
      const layerPrefix = `${sourceId}`;

      ensureGeoJsonSource(map, sourceId, layer.geojson_data);

      // Add geometry-type-appropriate layer
      const tipo = layer.tipo?.toLowerCase() ?? '';
      const isVisible = !!vectorVisibility.public_layers;

      if (tipo.includes('point') || tipo.includes('punto')) {
        if (!map.getLayer(`${layerPrefix}-circle`)) {
          map.addLayer({
            id: `${layerPrefix}-circle`,
            type: 'circle',
            source: sourceId,
            paint: {
              'circle-color': (layer.estilo?.color as string | undefined) ?? '#6b7280',
              'circle-radius': 5,
              'circle-opacity': 0.9,
              'circle-stroke-color': '#fff',
              'circle-stroke-width': 1,
            },
          });
        }
        setLayerVisibility(map, `${layerPrefix}-circle`, isVisible);
      } else if (tipo.includes('line') || tipo.includes('linea') || tipo.includes('canal')) {
        if (!map.getLayer(`${layerPrefix}-line`)) {
          map.addLayer({
            id: `${layerPrefix}-line`,
            type: 'line',
            source: sourceId,
            paint: {
              'line-color': (layer.estilo?.color as string | undefined) ?? '#6b7280',
              'line-width': 2,
              'line-opacity': 0.85,
            },
          });
        }
        setLayerVisibility(map, `${layerPrefix}-line`, isVisible);
      } else {
        // Polygon (default)
        if (!map.getLayer(`${layerPrefix}-fill`)) {
          map.addLayer({
            id: `${layerPrefix}-fill`,
            type: 'fill',
            source: sourceId,
            paint: {
              'fill-color': (layer.estilo?.color as string | undefined) ?? '#6b7280',
              'fill-opacity': 0.15,
            },
          });
        }
        if (!map.getLayer(`${layerPrefix}-line`)) {
          map.addLayer({
            id: `${layerPrefix}-line`,
            type: 'line',
            source: sourceId,
            paint: {
              'line-color': (layer.estilo?.color as string | undefined) ?? '#6b7280',
              'line-width': 1.5,
              'line-opacity': 0.85,
            },
          });
        }
        setLayerVisibility(map, `${layerPrefix}-fill`, isVisible);
        setLayerVisibility(map, `${layerPrefix}-line`, isVisible);
      }
    }
  }, [mapReady, publicLayers, vectorVisibility.public_layers]);

  /* ---------------------------------------------------------------------- */
  /*  DEM raster tile layer — Task 2.6                                       */
  /* ---------------------------------------------------------------------- */
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;

    if (!demTileUrl || !showDemOverlay) {
      setLayerVisibility(map, `${DEM_RASTER_SOURCE_ID}-layer`, false);
      return;
    }

    const existing = map.getSource(DEM_RASTER_SOURCE_ID) as maplibregl.RasterTileSource | undefined;
    if (existing) {
      // Update tile URL without unmounting — avoids full source removal/re-add
      (existing as maplibregl.RasterTileSource & { setTiles?: (tiles: string[]) => void }).setTiles?.([demTileUrl]);
    } else {
      map.addSource(DEM_RASTER_SOURCE_ID, {
        type: 'raster',
        tiles: [demTileUrl],
        tileSize: 256,
      });
    }

    if (!map.getLayer(`${DEM_RASTER_SOURCE_ID}-layer`)) {
      map.addLayer({
        id: `${DEM_RASTER_SOURCE_ID}-layer`,
        type: 'raster',
        source: DEM_RASTER_SOURCE_ID,
        paint: { 'raster-opacity': 0.75 },
      });
    } else {
      setLayerVisibility(map, `${DEM_RASTER_SOURCE_ID}-layer`, true);
    }
  }, [mapReady, demTileUrl, showDemOverlay]);

  /* ---------------------------------------------------------------------- */
  /*  IGN static image overlay — Task 2.9                                    */
  /* ---------------------------------------------------------------------- */
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;

    if (!map.getSource(IGN_SOURCE_ID)) {
      map.addSource(IGN_SOURCE_ID, {
        type: 'image',
        url: IGN_IMAGE_URL,
        coordinates: IGN_MAPLIBRE_COORDS,
      });
    }

    if (!map.getLayer(`${IGN_SOURCE_ID}-layer`)) {
      map.addLayer({
        id: `${IGN_SOURCE_ID}-layer`,
        type: 'raster',
        source: IGN_SOURCE_ID,
        paint: { 'raster-opacity': 0.65 },
      });
    }

    setLayerVisibility(map, `${IGN_SOURCE_ID}-layer`, showIGNOverlay);
  }, [mapReady, showIGNOverlay]);

  /* ---------------------------------------------------------------------- */
  /*  Satellite image overlay + comparison — Tasks 2.8, 2.11                */
  /* ---------------------------------------------------------------------- */
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;

    const showSingle = viewMode === 'single' && !!selectedImage;
    const showComparison = viewMode === 'comparison' && !!comparison?.left && !!comparison?.right;

    // ── Single selected image ──────────────────────────────────────────────
    // GEE tile_url is an XYZ tile template — use type:'raster', not type:'image'
    if (showSingle && selectedImage) {
      const existing = map.getSource(SATELLITE_IMAGE_SOURCE_ID);
      if (existing) {
        map.removeLayer(`${SATELLITE_IMAGE_SOURCE_ID}-layer`);
        map.removeSource(SATELLITE_IMAGE_SOURCE_ID);
      }
      map.addSource(SATELLITE_IMAGE_SOURCE_ID, {
        type: 'raster',
        tiles: [selectedImage.tile_url],
        tileSize: 256,
      });
      if (!map.getLayer(`${SATELLITE_IMAGE_SOURCE_ID}-layer`)) {
        map.addLayer({
          id: `${SATELLITE_IMAGE_SOURCE_ID}-layer`,
          type: 'raster',
          source: SATELLITE_IMAGE_SOURCE_ID,
          paint: { 'raster-opacity': 0.85 },
        });
      }
    } else {
      if (map.getLayer(`${SATELLITE_IMAGE_SOURCE_ID}-layer`)) {
        map.removeLayer(`${SATELLITE_IMAGE_SOURCE_ID}-layer`);
      }
      if (map.getSource(SATELLITE_IMAGE_SOURCE_ID)) {
        map.removeSource(SATELLITE_IMAGE_SOURCE_ID);
      }
    }

    // ── Comparison images ──────────────────────────────────────────────────
    if (showComparison && comparison?.left && comparison?.right) {
      if (map.getLayer(`${COMPARISON_LEFT_SOURCE_ID}-layer`)) map.removeLayer(`${COMPARISON_LEFT_SOURCE_ID}-layer`);
      if (map.getSource(COMPARISON_LEFT_SOURCE_ID)) map.removeSource(COMPARISON_LEFT_SOURCE_ID);
      map.addSource(COMPARISON_LEFT_SOURCE_ID, {
        type: 'raster',
        tiles: [comparison.left.tile_url],
        tileSize: 256,
      });
      map.addLayer({
        id: `${COMPARISON_LEFT_SOURCE_ID}-layer`,
        type: 'raster',
        source: COMPARISON_LEFT_SOURCE_ID,
        paint: { 'raster-opacity': 0.85 },
      });

      if (map.getLayer(`${COMPARISON_RIGHT_SOURCE_ID}-layer`)) map.removeLayer(`${COMPARISON_RIGHT_SOURCE_ID}-layer`);
      if (map.getSource(COMPARISON_RIGHT_SOURCE_ID)) map.removeSource(COMPARISON_RIGHT_SOURCE_ID);
      map.addSource(COMPARISON_RIGHT_SOURCE_ID, {
        type: 'raster',
        tiles: [comparison.right.tile_url],
        tileSize: 256,
      });
      map.addLayer({
        id: `${COMPARISON_RIGHT_SOURCE_ID}-layer`,
        type: 'raster',
        source: COMPARISON_RIGHT_SOURCE_ID,
        paint: { 'raster-opacity': 0.85 },
      });
    } else {
      if (map.getLayer(`${COMPARISON_LEFT_SOURCE_ID}-layer`)) map.removeLayer(`${COMPARISON_LEFT_SOURCE_ID}-layer`);
      if (map.getSource(COMPARISON_LEFT_SOURCE_ID)) map.removeSource(COMPARISON_LEFT_SOURCE_ID);
      if (map.getLayer(`${COMPARISON_RIGHT_SOURCE_ID}-layer`)) map.removeLayer(`${COMPARISON_RIGHT_SOURCE_ID}-layer`);
      if (map.getSource(COMPARISON_RIGHT_SOURCE_ID)) map.removeSource(COMPARISON_RIGHT_SOURCE_ID);
    }
  }, [mapReady, viewMode, selectedImage, comparison]);

  /* ---------------------------------------------------------------------- */
  /*  Martin MVT native vector sources — Task 2.7                           */
  /* ---------------------------------------------------------------------- */
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;

    const puntosStyle = MARTIN_SOURCES.puntos_conflicto.style;
    const canalesStyle = MARTIN_SOURCES.canal_suggestions.style;

    // Puntos de conflicto
    if (!map.getSource(MARTIN_PUNTOS_SOURCE_ID)) {
      map.addSource(MARTIN_PUNTOS_SOURCE_ID, {
        type: 'vector',
        tiles: [getMartinTileUrl('puntos_conflicto')],
        minzoom: 0,
        maxzoom: 22,
      });
    }
    if (!map.getLayer(`${MARTIN_PUNTOS_SOURCE_ID}-circle`)) {
      map.addLayer({
        id: `${MARTIN_PUNTOS_SOURCE_ID}-circle`,
        type: 'circle',
        source: MARTIN_PUNTOS_SOURCE_ID,
        'source-layer': 'puntos_conflicto',
        paint: {
          'circle-color': puntosStyle.fillColor,
          'circle-opacity': puntosStyle.fillOpacity,
          'circle-radius': puntosStyle.radius ?? 5,
          'circle-stroke-color': puntosStyle.color,
          'circle-stroke-width': puntosStyle.weight,
        },
      });
    }
    setLayerVisibility(map, `${MARTIN_PUNTOS_SOURCE_ID}-circle`, !!vectorVisibility.puntos_conflicto);

    // Canal suggestions
    if (!map.getSource(MARTIN_CANALES_SOURCE_ID)) {
      map.addSource(MARTIN_CANALES_SOURCE_ID, {
        type: 'vector',
        tiles: [getMartinTileUrl('canal_suggestions')],
        minzoom: 0,
        maxzoom: 22,
      });
    }
    if (!map.getLayer(`${MARTIN_CANALES_SOURCE_ID}-line`)) {
      map.addLayer({
        id: `${MARTIN_CANALES_SOURCE_ID}-line`,
        type: 'line',
        source: MARTIN_CANALES_SOURCE_ID,
        'source-layer': 'canal_suggestions',
        paint: {
          'line-color': canalesStyle.fillColor,
          'line-opacity': canalesStyle.opacity,
          'line-width': canalesStyle.weight,
        },
      });
    }
    setLayerVisibility(map, `${MARTIN_CANALES_SOURCE_ID}-line`, !!vectorVisibility.canal_suggestions);
  }, [mapReady, vectorVisibility.puntos_conflicto, vectorVisibility.canal_suggestions]);

  /* ---------------------------------------------------------------------- */
  /*  Feature click → InfoPanel                                              */
  /* ---------------------------------------------------------------------- */
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;

    const clickableLayers = [
      `${WATERWAYS_SOURCE_ID}-rio-tercero-line`,
      `${WATERWAYS_SOURCE_ID}-arroyo-algodon-line`,
      `${WATERWAYS_SOURCE_ID}-canal-desviador-line`,
      `${WATERWAYS_SOURCE_ID}-canal-litin-line`,
      `${WATERWAYS_SOURCE_ID}-canales-existentes-line`,
      `${WATERWAYS_SOURCE_ID}-arroyo-mojarras-line`,
      `${SOIL_SOURCE_ID}-fill`,
      `${CATASTRO_SOURCE_ID}-fill`,
      `${ROADS_SOURCE_ID}-line`,
      `${BASINS_SOURCE_ID}-fill`,
      `${APPROVED_ZONES_SOURCE_ID}-fill`,
      `${SUGGESTED_ZONES_SOURCE_ID}-fill`,
      `${INFRASTRUCTURE_SOURCE_ID}-circle`,
      `${MARTIN_PUNTOS_SOURCE_ID}-circle`,
    ];

    const handleClick = (e: maplibregl.MapMouseEvent) => {
      if (markingMode) {
        setNewPoint({ lat: e.lngLat.lat, lng: e.lngLat.lng });
        return;
      }

      const features = map.queryRenderedFeatures(e.point, {
        layers: clickableLayers.filter((id) => map.getLayer(id)),
      });

      if (features.length > 0 && features[0]) {
        setSelectedFeature(features[0] as unknown as Feature);
      } else {
        setSelectedFeature(null);
      }
    };

    map.on('click', handleClick);
    return () => {
      map.off('click', handleClick);
    };
  }, [mapReady, markingMode]);

  // Basin click for zoning panel
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !showSuggestedZonesPanel) return;

    const handleBasinClick = (e: maplibregl.MapMouseEvent) => {
      const features = map.queryRenderedFeatures(e.point, {
        layers: [`${BASINS_SOURCE_ID}-fill`, `${SUGGESTED_ZONES_SOURCE_ID}-fill`].filter((id) => map.getLayer(id)),
      });
      if (features.length > 0 && features[0]) {
        const basinId = features[0].properties?.id;
        if (typeof basinId === 'string') {
          setSelectedDraftBasinId(basinId);
        }
      }
    };

    map.on('click', handleBasinClick);
    return () => {
      map.off('click', handleBasinClick);
    };
  }, [mapReady, showSuggestedZonesPanel]);

  /* ---------------------------------------------------------------------- */
  /*  Comparison slider — Task 2.11 (CSS clip-path on right image layer)    */
  /* ---------------------------------------------------------------------- */
  const handleSliderMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    isDraggingSlider.current = true;

    const onMouseMove = (moveEvent: MouseEvent) => {
      if (!isDraggingSlider.current || !sliderContainerRef.current) return;
      const rect = sliderContainerRef.current.getBoundingClientRect();
      const pct = Math.max(0, Math.min(100, ((moveEvent.clientX - rect.left) / rect.width) * 100));
      setSliderPosition(pct);
    };

    const onMouseUp = () => {
      isDraggingSlider.current = false;
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    };

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
  }, []);

  /* ---------------------------------------------------------------------- */
  /*  Draw controls — Task 2.10                                              */
  /* ---------------------------------------------------------------------- */
  // Draw controls are mounted as React components that receive the map instance
  // after it's ready. The actual integration happens via the DrawControl component
  // which uses map.addControl() imperatively (see DrawControl.tsx).

  /* ---------------------------------------------------------------------- */
  /*  PNG export — Task 2.12                                                 */
  /* ---------------------------------------------------------------------- */
  const handleExportPng = useCallback(() => {
    const map = mapRef.current;
    if (!map) return;
    const canvas = map.getCanvas();
    const dataUrl = canvas.toDataURL('image/png');
    const link = document.createElement('a');
    link.href = dataUrl;
    link.download = formatExportFilename(exportTitle, 'png');
    link.click();
    setExportPngModalOpen(false);
    notifications.show({
      title: 'Exportación completada',
      message: 'PNG descargado correctamente',
      color: 'green',
    });
  }, [exportTitle]);

  /* ---------------------------------------------------------------------- */
  /*  PDF export — Task 2.13                                                 */
  /* ---------------------------------------------------------------------- */
  const handleExportApprovedZonesPdf = useCallback(async () => {
    if (!approvedZones) return;
    const map = mapRef.current;

    try {
      const token = await getAuthToken();
      const mapSnapshot = map ? map.getCanvas().toDataURL('image/png') : null;

      const response = await fetch(
        `${API_URL}/api/v2/geo/basins/approved-zones/current/export-map-pdf`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({
            features: approvedZones.features,
            map_snapshot: mapSnapshot,
          }),
        },
      );

      if (!response.ok) throw new Error('Error al generar PDF');

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = formatExportFilename('zonificacion_aprobada', 'pdf');
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (_err) {
      notifications.show({
        title: 'Error',
        message: 'No se pudo generar el PDF',
        color: 'red',
      });
    }
  }, [approvedZones]);

  const handleExportApprovedZonesGeoJSON = useCallback(() => {
    if (!approvedZones) return;
    const blob = new Blob([JSON.stringify(approvedZones, null, 2)], { type: 'application/json' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = formatExportFilename('zonificacion_aprobada', 'png').replace('.png', '.geojson');
    a.click();
    window.URL.revokeObjectURL(url);
  }, [approvedZones]);

  /* ---------------------------------------------------------------------- */
  /*  Infrastructure asset creation                                          */
  /* ---------------------------------------------------------------------- */
  const handleSaveAsset = async (values: typeof form.values) => {
    if (!newPoint) return;
    setIsSubmitting(true);
    try {
      await createAsset({
        ...values,
        latitud: newPoint.lat,
        longitud: newPoint.lng,
        estado_actual: 'bueno',
        tipo: values.tipo as 'alcantarilla' | 'puente' | 'canal' | 'otro',
      });
      notifications.show({
        title: 'Punto registrado',
        message: `${values.nombre} guardado exitosamente`,
        color: 'green',
      });
      setNewPoint(null);
      setMarkingMode(false);
      form.reset();
    } catch (_err) {
      notifications.show({ title: 'Error', message: 'No se pudo guardar el punto', color: 'red' });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleApproveZones = useCallback(async () => {
    if (!suggestedZonesDisplay) return;
    try {
      await saveApprovedZones(suggestedZonesDisplay, {
        assignments: effectiveBasinAssignments,
        zoneNames: suggestedZoneNames,
        nombre: approvalName || 'Zonificación Consorcio aprobada',
        notes: approvalNotes || null,
      });
      notifications.show({ title: 'Zonificación aprobada', message: 'Guardada exitosamente', color: 'green' });
    } catch (_err) {
      notifications.show({ title: 'Error', message: 'No se pudo aprobar la zonificación', color: 'red' });
    }
  }, [suggestedZonesDisplay, effectiveBasinAssignments, suggestedZoneNames, approvalName, approvalNotes, saveApprovedZones]);

  const handleClearApprovedZones = useCallback(async () => {
    try {
      await clearApprovedZones();
      notifications.show({ title: 'Zonificación limpiada', message: 'La aprobada fue eliminada', color: 'green' });
    } catch (_err) {
      notifications.show({ title: 'Error', message: 'No se pudo limpiar', color: 'red' });
    }
  }, [clearApprovedZones]);

  const handleApplyBasinMove = useCallback(() => {
    if (!selectedDraftBasinId || !draftDestinationZoneId) return;
    setDraftBasinAssignments((prev) => ({ ...prev, [selectedDraftBasinId]: draftDestinationZoneId }));
    setSelectedDraftBasinId(null);
    setDraftDestinationZoneId(null);
  }, [selectedDraftBasinId, draftDestinationZoneId]);

  /* ---------------------------------------------------------------------- */
  /*  Render                                                                 */
  /* ---------------------------------------------------------------------- */

  const hasSingleImage = !!selectedImage;
  const hasComparison = !!(comparison?.left && comparison.right);

  return (
    <Box className={styles.mapWrapper} style={{ position: 'relative', height: '100%' }}>
      {/* Map container */}
      <div ref={sliderContainerRef} style={{ width: '100%', height: '100%', position: 'relative' }}>
        <div ref={containerRef} style={{ width: '100%', height: '100%' }} />

        {/* Comparison slider divider line */}
        {viewMode === 'comparison' && (
          <div
            style={{
              position: 'absolute',
              top: 0,
              left: `${sliderPosition}%`,
              width: 3,
              height: '100%',
              background: 'rgba(255,255,255,0.9)',
              cursor: 'col-resize',
              zIndex: 15,
              transform: 'translateX(-50%)',
            }}
            onMouseDown={handleSliderMouseDown}
          >
            <div
              style={{
                position: 'absolute',
                top: '50%',
                left: '50%',
                transform: 'translate(-50%, -50%)',
                width: 28,
                height: 28,
                borderRadius: '50%',
                background: 'white',
                border: '2px solid rgba(0,0,0,0.3)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 2px 6px rgba(0,0,0,0.3)',
              }}
            >
              <IconGitCompare size={14} color="gray" />
            </div>
          </div>
        )}

        {/* Loading overlay */}
        {!mapReady && (
          <Box
            style={{
              position: 'absolute',
              inset: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: 'rgba(0,0,0,0.4)',
              zIndex: 20,
            }}
          >
            <Stack align="center" gap="md">
              <Loader size="lg" color="white" />
              <Text c="white">Cargando mapa...</Text>
            </Stack>
          </Box>
        )}
      </div>

      {/* Draw controls (attached to map after load) */}
      {mapReady && mapRef.current && isOperator && (
        <>
          <DrawControl
            ref={drawControlRef}
            map={mapRef.current}
            onPolygonCreated={setDrawnPolygon}
            onPolygonDeleted={() => setDrawnPolygon(null)}
            showControls={isOperator}
          />
          <LineDrawControl
            map={mapRef.current}
            value={drawnLine}
            onChange={setDrawnLine}
          />
        </>
      )}

      {/* ── Top-left floating controls ──────────────────────────────────── */}
      <Box
        style={{
          position: 'absolute',
          top: 12,
          left: 12,
          zIndex: 16,
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
        }}
      >
        {/* Base layer toggle */}
        <Paper
          shadow="md"
          p="xs"
          radius="md"
          style={{ background: 'light-dark(rgba(255,255,255,0.94), rgba(36,36,36,0.94))', backdropFilter: 'blur(6px)' }}
        >
          <Stack gap={4}>
            <Text size="xs" fw={600} c="dimmed">Capa base</Text>
            <SegmentedControl
              size="xs"
              value={baseLayer}
              onChange={(v) => setBaseLayer(v as 'osm' | 'satellite')}
              data={[
                { value: 'osm', label: 'OSM' },
                { value: 'satellite', label: 'Satélite' },
              ]}
            />
          </Stack>
        </Paper>

        {/* View mode panel (single/comparison satellite) */}
        <ViewModePanel
          viewMode={viewMode}
          onViewModeChange={setViewMode}
          hasSingleImage={hasSingleImage}
          hasComparison={hasComparison}
          singleImageInfo={selectedImage ? { sensor: selectedImage.sensor, date: selectedImage.target_date } : null}
          comparisonInfo={
            comparison?.left && comparison.right
              ? { leftDate: comparison.left.target_date, rightDate: comparison.right.target_date }
              : null
          }
        />

        {/* Layer toggles */}
        <Paper
          shadow="md"
          p="xs"
          radius="md"
          style={{
            background: 'light-dark(rgba(255,255,255,0.94), rgba(36,36,36,0.94))',
            backdropFilter: 'blur(6px)',
            maxHeight: '60vh',
            overflowY: 'auto',
          }}
        >
          <Text size="xs" fw={600} c="dimmed" mb={6}>Capas</Text>
          <Stack gap={4}>
            {[
              { id: 'basins', label: 'Subcuencas', show: !!basins && basins.features.length > 0 },
              { id: 'approved_zones', label: 'Cuencas', show: !!approvedZonesCollection },
              { id: 'waterways', label: 'Hidrografía', show: true },
              { id: 'roads', label: 'Red vial', show: !!roadsCollection && roadsCollection.features.length > 0 },
              { id: 'soil', label: 'Suelos IDECOR', show: true },
              { id: 'catastro', label: 'Catastro rural', show: true },
              { id: 'infrastructure', label: 'Infraestructura', show: !!infrastructureCollection },
              { id: 'public_layers', label: 'Capas públicas', show: publicLayers.length > 0 },
              { id: 'puntos_conflicto', label: 'Puntos conflicto', show: !!(intersections?.features?.length) },
              { id: 'canal_suggestions', label: 'Sugerencias canal', show: true },
            ].filter(({ show }) => show)
             .map(({ id, label }) => (
              <Checkbox
                key={id}
                size="xs"
                label={label}
                checked={!!vectorVisibility[id]}
                onChange={(e) => toggleLayer(id, e.currentTarget.checked)}
              />
            ))}
            <Divider my={4} />
            <Checkbox
              size="xs"
              label="IGN Altimetría"
              checked={showIGNOverlay}
              onChange={(e) => setShowIGNOverlay(e.currentTarget.checked)}
            />
            {demLayers.length > 0 && (
              <>
                <Checkbox
                  size="xs"
                  label="Capa DEM"
                  checked={showDemOverlay}
                  onChange={(e) => setShowDemOverlay(e.currentTarget.checked)}
                />
                {showDemOverlay && (
                  <Select
                    size="xs"
                    placeholder="Tipo de capa"
                    value={activeDemLayerId}
                    onChange={setActiveDemLayerId}
                    data={demLayers.map((l) => ({
                      value: l.id,
                      label: GEO_LAYER_LABELS[l.tipo] ?? l.nombre,
                    }))}
                  />
                )}
              </>
            )}
          </Stack>
        </Paper>
      </Box>

      {/* ── Top-right controls ──────────────────────────────────────────── */}
      <Box
        style={{
          position: 'absolute',
          top: 12,
          right: 48, // leave room for nav control
          zIndex: 16,
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
          alignItems: 'flex-end',
        }}
      >
        <Paper
          shadow="md"
          p="xs"
          radius="md"
          style={{ background: 'light-dark(rgba(255,255,255,0.94), rgba(36,36,36,0.94))', backdropFilter: 'blur(6px)' }}
        >
          <Group gap="xs">
            <Menu shadow="md" width={200}>
              <Menu.Target>
                <Button size="xs" variant="light" leftSection={<IconDownload size={14} />}>
                  Exportar
                </Button>
              </Menu.Target>
              <Menu.Dropdown>
                <Menu.Item
                  leftSection={<IconPhoto size={14} />}
                  onClick={() => setExportPngModalOpen(true)}
                >
                  Exportar PNG
                </Menu.Item>
                {hasApprovedZones && (
                  <Menu.Item
                    leftSection={<IconMap size={14} />}
                    onClick={handleExportApprovedZonesPdf}
                  >
                    Exportar PDF zonificación
                  </Menu.Item>
                )}
              </Menu.Dropdown>
            </Menu>

            {isOperator && (
              <Button
                size="xs"
                variant={markingMode ? 'filled' : 'light'}
                color={markingMode ? 'red' : undefined}
                onClick={() => {
                  setMarkingMode(!markingMode);
                  setNewPoint(null);
                }}
              >
                {markingMode ? 'Cancelar marcado' : 'Marcar punto'}
              </Button>
            )}

            {canManageZoning && (
              <Button
                size="xs"
                variant="light"
                leftSection={<IconLayers size={14} />}
                onClick={() => setShowSuggestedZonesPanel((prev) => !prev)}
              >
                {showSuggestedZonesPanel
                  ? 'Ocultar zonificación'
                  : hasApprovedZones
                    ? 'Ver zonificación'
                    : 'Zonas sugeridas'}
              </Button>
            )}
          </Group>
        </Paper>

        {showLegend && (
          <Leyenda
            consorcios={consorcios}
            customItems={activeLegendItems}
            floating={false}
          />
        )}

        {/* Raster legend */}
        {visibleRasterLayers.length > 0 && (
          <RasterLegend
            layers={visibleRasterLayers}
            hiddenClasses={hiddenClasses}
            hiddenRanges={hiddenRanges}
            onClassToggle={(layerType, classIndex, visible) =>
              setHiddenClasses((prev) => {
                const curr = prev[layerType] ?? [];
                const next = visible ? curr.filter((i) => i !== classIndex) : [...curr, classIndex];
                return { ...prev, [layerType]: next };
              })
            }
            onRangeToggle={(layerType, rangeIndex, visible) =>
              setHiddenRanges((prev) => {
                const curr = prev[layerType] ?? [];
                const next = visible ? curr.filter((i) => i !== rangeIndex) : [...curr, rangeIndex];
                return { ...prev, [layerType]: next };
              })
            }
          />
        )}
      </Box>

      {/* ── Suggested zones panel ──────────────────────────────────────── */}
      {showSuggestedZonesPanel && suggestedZoneSummaries.length > 0 && canManageZoning && (
        <SuggestedZonesPanel
          zones={suggestedZoneSummaries}
          zoneNames={suggestedZoneNames}
          onZoneNameChange={(id, value) => setSuggestedZoneNames((prev) => ({ ...prev, [id]: value }))}
          selectedBasinName={selectedDraftBasinName}
          selectedBasinZoneId={selectedDraftBasinZoneId}
          destinationZoneId={draftDestinationZoneId}
          onDestinationZoneChange={setDraftDestinationZoneId}
          onApplyBasinMove={handleApplyBasinMove}
          hasApprovedZones={hasApprovedZones}
          approvedAt={approvedAt}
          approvedVersion={approvedVersion}
          approvedZonesHistory={approvedZonesHistory}
          approvalName={approvalName}
          approvalNotes={approvalNotes}
          onApprovalNameChange={setApprovalName}
          onApprovalNotesChange={setApprovalNotes}
          onClose={() => setShowSuggestedZonesPanel(false)}
          onApproveZones={handleApproveZones}
          onClearApprovedZones={handleClearApprovedZones}
          onRestoreVersion={async (id) => {
            try {
              await restoreApprovedZonesVersion(id);
              notifications.show({ title: 'Versión restaurada', message: 'Zonificación restaurada', color: 'green' });
            } catch (_err) {
              notifications.show({ title: 'Error', message: 'No se pudo restaurar', color: 'red' });
            }
          }}
          onExportApprovedZonesGeoJSON={handleExportApprovedZonesGeoJSON}
          onExportApprovedZonesPdf={handleExportApprovedZonesPdf}
        />
      )}

      {/* ── InfoPanel ─────────────────────────────────────────────────── */}
      {selectedFeature && (
        <InfoPanel
          feature={selectedFeature}
          onClose={() => setSelectedFeature(null)}
        />
      )}

      {/* ── New point modal ────────────────────────────────────────────── */}
      <Modal
        opened={!!newPoint}
        onClose={() => { setNewPoint(null); form.reset(); setMarkingMode(false); }}
        title="Registrar activo de infraestructura"
        size="sm"
      >
        <form onSubmit={form.onSubmit(handleSaveAsset)}>
          <Stack gap="xs">
            <Text size="xs" c="dimmed">
              Coordenadas: {newPoint?.lat.toFixed(5)}, {newPoint?.lng.toFixed(5)}
            </Text>
            <TextInput
              size="xs"
              label="Nombre"
              placeholder="Nombre del activo"
              {...form.getInputProps('nombre')}
            />
            <Select
              size="xs"
              label="Tipo"
              data={[
                { value: 'alcantarilla', label: 'Alcantarilla' },
                { value: 'puente', label: 'Puente' },
                { value: 'canal', label: 'Canal' },
                { value: 'otro', label: 'Otro' },
              ]}
              {...form.getInputProps('tipo')}
            />
            <Textarea
              size="xs"
              label="Descripción"
              placeholder="Descripción opcional"
              minRows={2}
              {...form.getInputProps('descripcion')}
            />
            <Button type="submit" size="xs" loading={isSubmitting}>
              Guardar punto
            </Button>
          </Stack>
        </form>
      </Modal>

      {/* ── Export PNG modal ───────────────────────────────────────────── */}
      <Modal
        opened={exportPngModalOpen}
        onClose={() => setExportPngModalOpen(false)}
        title="Exportar mapa como PNG"
        size="sm"
      >
        <Stack gap="xs">
          <TextInput
            size="xs"
            label="Título del mapa"
            value={exportTitle}
            onChange={(e) => setExportTitle(e.currentTarget.value)}
          />
          <Checkbox
            size="xs"
            label="Incluir leyenda"
            checked={exportIncludeLegend}
            onChange={(e) => setExportIncludeLegend(e.currentTarget.checked)}
          />
          <Checkbox
            size="xs"
            label="Incluir metadatos"
            checked={exportIncludeMetadata}
            onChange={(e) => setExportIncludeMetadata(e.currentTarget.checked)}
          />
          <Button size="xs" onClick={handleExportPng} leftSection={<IconDownload size={14} />}>
            Descargar PNG
          </Button>
        </Stack>
      </Modal>
    </Box>
  );
}
