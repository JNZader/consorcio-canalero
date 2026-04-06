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
import type { Feature } from 'geojson';
import html2canvas from 'html2canvas';
import type { LeafletMouseEvent, Path } from 'leaflet';
import { memo, useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import {
  GeoJSON,
  FeatureGroup,
  ImageOverlay,
  LayersControl,
  MapContainer,
  Pane,
  TileLayer,
  CircleMarker,
  Popup,
  Tooltip as LeafletTooltip,
  useMapEvents,
  useMap,
} from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';
import { useBasins } from '../hooks/useBasins';
import { useApprovedZones } from '../hooks/useApprovedZones';
import { useSuggestedZones } from '../hooks/useSuggestedZones';
import { useGEELayers, GEE_LAYER_STYLES } from '../hooks/useGEELayers';
import { useGeoLayers, GEO_LAYER_LABELS, buildTileUrl } from '../hooks/useGeoLayers';
import { MARTIN_SOURCES, getMartinTileUrl, useZonaRiskColors, getZonaFillColor } from '../hooks/useMartinLayers';
import MartinVectorLayer from './MartinVectorLayer';
import { useCaminosColoreados, type ConsorcioInfo } from '../hooks/useCaminosColoreados';
import { useInfrastructure } from '../hooks/useInfrastructure';
import { usePublicLayers } from '../hooks/usePublicLayers';
import { getSoilColor, useSoilMap } from '../hooks/useSoilMap';
import { useCatastroMap } from '../hooks/useCatastroMap';
import { useWaterways } from '../hooks/useWaterways';
import { MapReadyHandler } from '../hooks/useMapReady';
import { useSelectedImageListener, type SelectedImage } from '../hooks/useSelectedImage';
import { useImageComparisonListener } from '../hooks/useImageComparison';
import { ComparisonLayers, ComparisonSliderUI } from './MapImageComparison';
import { RasterLegend } from './RasterLegend';
import { IconGitCompare, IconLayers, IconPhoto, IconDownload, IconMap } from './ui/icons';
import { LAYER_LEGEND_CONFIG } from '../config/rasterLegend';

import { MAP_CENTER, MAP_DEFAULT_ZOOM } from '../constants';

/**
 * TileLayer wrapper that updates the URL without unmounting.
 * Changing the `key` on a TileLayer inside LayersControl causes Leaflet
 * to lose track of the overlay (disabling all layers). Instead, we use
 * a ref and call setUrl() imperatively when the URL changes.
 */
function DynamicTileLayer(props: React.ComponentProps<typeof TileLayer>) {
  const ref = useRef<L.TileLayer>(null);
  const prevUrl = useRef(props.url);

  useEffect(() => {
    if (ref.current && props.url !== prevUrl.current) {
      ref.current.setUrl(props.url);
      prevUrl.current = props.url;
    }
  }, [props.url]);

  return <TileLayer ref={ref} {...props} />;
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
import { useConfigStore } from '../stores/configStore';
import { useCanAccess } from '../stores/authStore';
import { useMapLayerSyncStore } from '../stores/mapLayerSyncStore';
import { API_URL, getAuthToken } from '../lib/api';
import { formatDate } from '../lib/formatters';
import styles from '../styles/components/map.module.css';

// Solo mantenemos la zona histórica manual desde GEE.
// Las subcuencas operativas deben venir del backend/PostGIS.
const GEE_LAYER_NAMES = ['zona'] as const;
const IGN_HISTORIC_OVERLAY = {
  image: '/overlays/ign/altimetria_ign_consorcio.webp',
  bounds: [
    [-32.665914, -62.750969],
    [-32.44785, -62.345994],
  ] as [[number, number], [number, number]],
};

/**
 * Renders the appropriate legend item indicator based on type.
 * Avoids nested ternary operators (SonarQube S3358).
 */
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

// Componente para controlar la leyenda - con soporte para consorcios camineros
interface LeyendaProps {
  consorcios?: ConsorcioInfo[];
  cuencasConfig?: { id: string; nombre: string; color: string }[];
  customItems?: { color: string; label: string; type: string }[];
  floating?: boolean;
}

const Leyenda = memo(function Leyenda({
  consorcios = [],
  cuencasConfig = [],
  customItems = [],
  floating = true,
}: LeyendaProps) {
  const [showConsorcios, setShowConsorcios] = useState(false);

  // Fallback legend items if config not loaded yet
  const legendItems =
    customItems.length > 0
      ? customItems
      : cuencasConfig.length > 0
      ? [
          { color: '#FF0000', label: 'Zona Consorcio', type: 'border' },
          ...cuencasConfig.map((c) => ({
            color: c.color,
            label: `Cuenca ${c.nombre}`,
            type: 'fill',
          })),
        ]
      : [
          { color: '#FF0000', label: 'Zona Consorcio', type: 'border' },
          { color: '#2196F3', label: 'Cuenca Candil', type: 'fill' },
          { color: '#4CAF50', label: 'Cuenca ML', type: 'fill' },
          { color: '#FF9800', label: 'Cuenca Noroeste', type: 'fill' },
          { color: '#9C27B0', label: 'Cuenca Norte', type: 'fill' },
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
        {/* Items base (cuencas, zona) */}
        {legendItems.map((item) => (
          <Group key={item.label} gap="xs">
            <LegendItemIndicator item={item} />
            <Text size="xs">{item.label}</Text>
          </Group>
        ))}

        {/* Seccion de Consorcios Camineros */}
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

// Panel de informacion - memoizado para evitar re-renders innecesarios
interface InfoPanelProps {
  readonly feature: GeoJSON.Feature | null;
  readonly onClose: () => void;
}

const InfoPanel = memo(function InfoPanel({ feature, onClose }: InfoPanelProps) {
  if (!feature) return null;

  const properties = feature.properties || {};

  return (
    <Paper shadow="md" p="md" radius="md" className={styles.infoPanel}>
      <Group justify="space-between" mb="xs">
        <Title order={5}>Informacion</Title>
        <CloseButton onClick={onClose} size="sm" aria-label="Cerrar panel de informacion" />
      </Group>
      <Divider mb="xs" />
      <Stack gap={4}>
        {Object.entries(properties).map(([key, value]) => (
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
        zIndex: 1000,
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
              <Text size="xs" c="dimmed">
                {hasApprovedZones
                  ? 'La zonificación aprobada ya reemplaza visualmente a las capas draft e históricas. Si necesitás editar de nuevo, podés limpiar la aprobada.'
                  : 'Draft territorial sugerido: Norte absorbe norte+noroeste, Monte Leña absorbe ml y Candil absorbe candil. Las sin asignar del sur/este se absorben en Monte Leña o Candil y después podés corregir manualmente subcuenca por subcuenca.'}
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
              <Text size="xs" c="dimmed" mb={6}>
                Seleccioná una subcuenca en el mapa y elegí la zona destino.
              </Text>
              <Stack gap={6}>
                <Text size="xs">
                  Subcuenca seleccionada: <b>{selectedBasinName || 'Ninguna'}</b>
                </Text>
                <Text size="xs" c="dimmed">
                  Zona actual:{' '}
                  {selectedBasinZoneId
                    ? (zoneNames[selectedBasinZoneId] ??
                      zones.find((zone) => zone.id === selectedBasinZoneId)?.defaultName ??
                      selectedBasinZoneId)
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
              <Badge size="xs" color="green" variant="light">
                Aprobada
              </Badge>
            ) : (
              <Badge size="xs" color="yellow" variant="light">
                Draft
              </Badge>
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
              <Button
                size="xs"
                variant="light"
                leftSection={<IconDownload size={14} />}
                onClick={onExportApprovedZonesGeoJSON}
              >
                GeoJSON
              </Button>
              <Button
                size="xs"
                variant="light"
                leftSection={<IconDownload size={14} />}
                onClick={onExportApprovedZonesPdf}
              >
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
                        {item.approvedByName ? (
                          <Text size="xs" c="dimmed">
                            Aprobó: {item.approvedByName}
                          </Text>
                        ) : null}
                        {item.notes ? (
                          <Text size="xs" c="dimmed">
                            {item.notes}
                          </Text>
                        ) : null}
                      </Stack>
                      {approvedVersion !== item.version && (
                        <Button
                          size="xs"
                          variant="light"
                          onClick={() => onRestoreVersion(item.id)}
                        >
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

interface SuggestedZonesToggleProps {
  readonly opened: boolean;
  readonly onToggle: () => void;
  readonly hasApprovedZones: boolean;
}

const SuggestedZonesToggle = memo(function SuggestedZonesToggle({
  opened,
  onToggle,
  hasApprovedZones,
}: SuggestedZonesToggleProps) {
  return (
    <Paper
      shadow="md"
      p="xs"
      radius="md"
      style={{ background: 'light-dark(rgba(255,255,255,0.94), rgba(36,36,36,0.94))', backdropFilter: 'blur(6px)' }}
    >
      <Button size="xs" variant="light" onClick={onToggle} leftSection={<IconLayers size={14} />}>
        {opened
          ? 'Ocultar zonificación'
          : hasApprovedZones
            ? 'Ver zonificación e historial'
            : 'Ver zonas sugeridas e historial'}
      </Button>
    </Paper>
  );
});

// Panel showing currently active satellite image
interface SatelliteImagePanelProps {
  readonly image: SelectedImage;
  readonly onClear: () => void;
}

const _SatelliteImagePanel = memo(function SatelliteImagePanel({
  image: _image,
  onClear: _onClear,
}: SatelliteImagePanelProps) {
  return (
    <Paper
      shadow="md"
      p="sm"
      radius="md"
      style={{ maxWidth: 320, background: 'light-dark(rgba(255,255,255,0.94), rgba(36,36,36,0.94))', backdropFilter: 'blur(6px)' }}
    >
      <Group justify="space-between" gap="xs" wrap="nowrap">
        <Group gap="xs" wrap="nowrap">
          <IconPhoto size={16} color="var(--mantine-color-blue-6)" />
          <div>
            <Text size="xs" fw={600} c="blue.7">
              {_image.sensor} - {_image.target_date}
            </Text>
            <Text size="xs" c="dimmed">
              {_image.visualization_description}
            </Text>
          </div>
        </Group>
        <CloseButton size="sm" onClick={_onClear} aria-label="Quitar imagen satelital" />
      </Group>
    </Paper>
  );
});

// View mode types
type ViewMode = 'base' | 'single' | 'comparison';

// Panel to control which satellite view is active
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
  // Don't show if there's nothing to toggle
  if (!hasSingleImage && !hasComparison) {
    return null;
  }

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
          label={
            singleImageInfo
              ? `${singleImageInfo.sensor} - ${singleImageInfo.date}`
              : 'Imagen satelital'
          }
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
          label={
            comparisonInfo
              ? `Comparar: ${comparisonInfo.leftDate} vs ${comparisonInfo.rightDate}`
              : 'Comparacion'
          }
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

// Componente para capturar clics y añadir puntos
function AddPointEvents({
  onMapClick,
  enabled,
}: { onMapClick: (lat: number, lng: number) => void; enabled: boolean }) {
  useMapEvents({
    click(e) {
      if (enabled) {
        onMapClick(e.latlng.lat, e.latlng.lng);
      }
    },
  });
  return null;
}

/**
 * Syncs the map view when center/zoom change from config,
 * without remounting the entire MapContainer.
 */
function MapViewUpdater({ center, zoom }: { center: [number, number]; zoom: number }) {
  const map = useMap();

  useEffect(() => {
    map.setView(center, zoom);
  }, [map, center, zoom]);

  return null;
}

/** Raster layer type prefixes used in LayersControl overlay names */
const DEM_OVERLAY_PREFIX = 'DEM: ';

/**
 * Listens to LayersControl overlay add/remove events and reports
 * which raster tile layers are currently visible.
 */
function OverlayTracker({
  allGeoLayers,
  waterwayIdsByName,
  onVisibleChange,
  onRasterFocusChange,
  onVectorVisibilityChange,
}: {
  allGeoLayers: Array<{ id: string; tipo: string; nombre: string }>;
  waterwayIdsByName: Record<string, string>;
  onVisibleChange: (layers: Array<{ tipo: string }>) => void;
  onRasterFocusChange?: (tipo: string | null) => void;
  onVectorVisibilityChange?: (layerId: string, visible: boolean) => void;
}) {
  const visibleRef = useRef(new Set<string>());
  const vectorOverlayMap: Record<string, string> = {
    'Zonificación Consorcio aprobada': 'approved_zones',
    'Zona Consorcio (manual histórica)': 'zona',
    'IGN Altimetría histórica': 'ign_historico',
    'Subcuencas Operativas': 'basins',
    'Zonas sugeridas (draft desde subcuencas)': 'basins',
    'Red Vial (por Consorcio)': 'roads',
    'Suelos IDECOR 1:50.000': 'soil',
    'Catastro rural IDECOR': 'catastro',
    'Activos de Infraestructura': 'infrastructure',
    'Riesgo Hidráulico (zonas)': 'hydraulic_risk',
    'Puntos de Conflicto': 'puntos_conflicto',
    'Sugerencias de Canal': 'canal_suggestions',
  };

  const resolveVectorLayerId = (name: string): string | null => {
    if (vectorOverlayMap[name]) return vectorOverlayMap[name];
    if (name.startsWith('Hidro: ')) {
      const waterwayName = name.replace('Hidro: ', '');
      const waterwayId = waterwayIdsByName[waterwayName];
      return waterwayId ? `waterways_${waterwayId}` : 'waterways';
    }
    if (
      name === 'Cuenca Candil' ||
      name === 'Cuenca ML' ||
      name === 'Cuenca Noroeste' ||
      name === 'Cuenca Norte'
    ) {
      return 'cuencas';
    }
    return null;
  };

  useMapEvents({
    overlayadd(e) {
      const name: string = e.name;
      // Match DEM layers ("DEM: Elevacion (DEM)") and composite layers by label
      const matched = allGeoLayers.find((l) => {
        const demName = `${DEM_OVERLAY_PREFIX}${GEO_LAYER_LABELS[l.tipo] || l.nombre}`;
        const compositeName = GEO_LAYER_LABELS[l.tipo] || l.nombre;
        return name === demName || name === compositeName;
      });
      if (matched) {
        visibleRef.current.add(matched.tipo);
        onVisibleChange(Array.from(visibleRef.current).map((tipo) => ({ tipo })));
        onRasterFocusChange?.(matched.tipo);
      }
      const vectorLayerId = resolveVectorLayerId(name);
      if (vectorLayerId) {
        onVectorVisibilityChange?.(vectorLayerId, true);
      }
    },
    overlayremove(e) {
      const name: string = e.name;
      const matched = allGeoLayers.find((l) => {
        const demName = `${DEM_OVERLAY_PREFIX}${GEO_LAYER_LABELS[l.tipo] || l.nombre}`;
        const compositeName = GEO_LAYER_LABELS[l.tipo] || l.nombre;
        return name === demName || name === compositeName;
      });
      if (matched) {
        visibleRef.current.delete(matched.tipo);
        onVisibleChange(Array.from(visibleRef.current).map((tipo) => ({ tipo })));
        const nextVisible = Array.from(visibleRef.current);
        onRasterFocusChange?.(nextVisible.length > 0 ? nextVisible[nextVisible.length - 1] : null);
      }
      const vectorLayerId = resolveVectorLayerId(name);
      if (vectorLayerId) {
        onVectorVisibilityChange?.(vectorLayerId, false);
      }
    },
  });

  return null;
}

export default function MapaLeaflet() {
  // Get system configuration from store
  const config = useConfigStore((state) => state.config);

  // Memoize center and zoom to prevent MapViewUpdater from resetting the
  // map viewport on every re-render (e.g. during comparison slider drag).
  // Without useMemo, a new array reference is created each render, which
  // triggers the useEffect inside MapViewUpdater and calls map.setView(),
  // snapping the map back to default zoom.
  const center = useMemo<[number, number]>(
    () =>
      config?.map.center
        ? [config.map.center.lat, config.map.center.lng]
        : MAP_CENTER,
    [config?.map.center?.lat, config?.map.center?.lng]
  );
  const zoom = useMemo(
    () => config?.map.zoom ?? MAP_DEFAULT_ZOOM,
    [config?.map.zoom]
  );

  // Unique ID for this map instance - forces clean remount on navigation
  const mapInstanceId = useId();

  // Estados para marcacion manual
  const [markingMode, setMarkingMode] = useState(false);
  const [newPoint, setNewPoint] = useState<{ lat: number; lng: number } | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const form = useForm({
    initialValues: {
      nombre: '',
      tipo: 'alcantarilla',
      descripcion: '',
      cuenca: '',
    },
    validate: {
      nombre: (value) => (value.length < 3 ? 'Nombre demasiado corto' : null),
    },
  });

  // Check if user is admin/operator (controls visibility of draw/mark tools)
  const isOperator = useCanAccess(['admin', 'operador']);
  const canManageZoning = useCanAccess(['admin', 'operador']);

  // Use centralized hook for loading GEE layers (sin caminos - se cargan aparte)
  const { layers: capas, loading: loadingCapas } = useGEELayers({
    layerNames: GEE_LAYER_NAMES,
  });

  // Caminos coloreados por consorcio caminero
  const { caminos, consorcios, loading: loadingCaminos } = useCaminosColoreados();

  // Infraestructura y puntos de cruce (alcantarillas potenciales)
  const { assets, intersections, loading: loadingInfra, createAsset } = useInfrastructure();

  // Public vector layers (admin-published, no auth required)
  const { layers: publicLayers, loading: loadingPublicLayers } = usePublicLayers();

  // Soil map from IDECOR 1:50.000
  const { soilMap, loading: loadingSoilMap } = useSoilMap();
  const [suggestedZoneNames, setSuggestedZoneNames] = useState<Record<string, string>>({});
  const [draftBasinAssignments, setDraftBasinAssignments] = useState<Record<string, string>>({});
  const [selectedDraftBasinId, setSelectedDraftBasinId] = useState<string | null>(null);
  const [draftDestinationZoneId, setDraftDestinationZoneId] = useState<string | null>(null);
  const [showSuggestedZonesPanel, setShowSuggestedZonesPanel] = useState(false);
  const [captureMode, setCaptureMode] = useState(false);
  const [exportingMap, setExportingMap] = useState(false);
  const [exportPngModalOpen, setExportPngModalOpen] = useState(false);
  const [exportIncludeLegend, setExportIncludeLegend] = useState(true);
  const [exportIncludeMetadata, setExportIncludeMetadata] = useState(true);
  const [exportTitle, setExportTitle] = useState('Mapa del Consorcio');
  const [approvalName, setApprovalName] = useState('Zonificación Consorcio aprobada');
  const [approvalNotes, setApprovalNotes] = useState('');
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
  const { catastroMap, loading: loadingCatastroMap } = useCatastroMap();

  // Basin polygons from PostGIS (public, no auth required)
  const { basins, loading: loadingBasins } = useBasins();
  const { suggestedZones, loading: loadingSuggestedZones } = useSuggestedZones();

  // Waterway layers (static GeoJSON, no auth required)
  const { waterways, loading: loadingWaterways } = useWaterways();
  const waterwayIdsByName = useMemo(
    () =>
      Object.fromEntries(
        waterways.map((layer) => [layer.nombre, layer.id]),
      ),
    [waterways],
  );

  // DEM pipeline raster layers for tile overlays (authenticated)
  const { layers: allGeoLayers, loading: loadingDemLayers } = useGeoLayers();

  // Flood risk colors per zona (for Martin zonas_operativas layer)
  const { data: zonaRiskColors = {} } = useZonaRiskColors();

  // Track which raster overlay layers are currently visible (for legend)
  const [visibleRasterLayers, setVisibleRasterLayers] = useState<Array<{ tipo: string }>>([]);

  // Track hidden class indices per categorical layer type (e.g. { terrain_class: [1, 3] })
  const [hiddenClasses, setHiddenClasses] = useState<Record<string, number[]>>({});

  const handleClassToggle = useCallback(
    (layerType: string, classIndex: number, visible: boolean) => {
      setHiddenClasses((prev) => {
        const current = prev[layerType] ?? [];
        const next = visible
          ? current.filter((i) => i !== classIndex)
          : [...current, classIndex];
        return { ...prev, [layerType]: next };
      });
    },
    [],
  );

  // Track hidden range indices per continuous layer type (e.g. { flood_risk: [0, 2] })
  const [hiddenRanges, setHiddenRanges] = useState<Record<string, number[]>>({});
  const sharedActiveRasterType = useMapLayerSyncStore((state) => state.map2d.activeRasterType);
  const sharedVisibleVectors = useMapLayerSyncStore((state) => state.map2d.visibleVectors);
  const is2DViewInitialized = useMapLayerSyncStore((state) => state.initializedViews.map2d);
  const setSharedActiveRasterType = useMapLayerSyncStore((state) => state.setActiveRasterType);
  const setSharedVectorVisibility = useMapLayerSyncStore((state) => state.setVectorVisibility);
  const hydrateSharedViewState = useMapLayerSyncStore((state) => state.hydrateViewState);

  const handleRangeToggle = useCallback(
    (layerType: string, rangeIndex: number, visible: boolean) => {
      setHiddenRanges((prev) => {
        const current = prev[layerType] ?? [];
        const next = visible
          ? current.filter((i) => i !== rangeIndex)
          : [...current, rangeIndex];
        return { ...prev, [layerType]: next };
      });
    },
    [],
  );

  // Separate composite analysis layers from standard DEM layers
  const COMPOSITE_TYPES = useMemo(() => new Set(['flood_risk', 'drainage_need']), []);
  const demLayers = useMemo(
    () => allGeoLayers.filter((l) => !COMPOSITE_TYPES.has(l.tipo)),
    [allGeoLayers, COMPOSITE_TYPES]
  );
  const compositeLayers = useMemo(
    () => allGeoLayers.filter((l) => COMPOSITE_TYPES.has(l.tipo)),
    [allGeoLayers, COMPOSITE_TYPES]
  );

  const handleExportAsset = async (assetId: string, assetName: string) => {
    try {
      const token = await getAuthToken();
      const response = await fetch(
        // TODO: Asset export-pdf not implemented in v2 yet
        `${API_URL}/api/v2/infraestructura/assets/${assetId}/export-pdf`,
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );
      if (!response.ok) throw new Error('Error al generar PDF');
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `Ficha_Tecnica_${assetName.replace(/\s+/g, '_')}.pdf`;
      a.click();
    } catch (_err) {
      notifications.show({
        title: 'Error',
        message: 'No se pudo generar la ficha tecnica',
        color: 'red',
      });
    }
  };

  const handleMapClick = useCallback((lat: number, lng: number) => {
    setNewPoint({ lat, lng });
  }, []);

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
        message: `${values.nombre} ha sido guardado exitosamente`,
        color: 'green',
      });
      setNewPoint(null);
      setMarkingMode(false);
      form.reset();
    } catch (_err) {
      notifications.show({
        title: 'Error',
        message: 'No se pudo guardar el punto',
        color: 'red',
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const loading =
    loadingCapas ||
    loadingCaminos ||
    loadingInfra ||
    loadingPublicLayers ||
    loadingSoilMap ||
    loadingCatastroMap ||
    loadingBasins ||
    loadingSuggestedZones ||
    loadingDemLayers ||
    loadingWaterways;
  const [selectedFeature, setSelectedFeature] = useState<GeoJSON.Feature | null>(null);

  const initialDraftAssignments = useMemo(() => {
    const mapping: Record<string, string> = {};
    for (const feature of suggestedZones?.features ?? []) {
      const zoneId = String(feature.properties?.draft_zone_id || '');
      const memberIds = Array.isArray(feature.properties?.member_basin_ids)
        ? (feature.properties?.member_basin_ids as unknown[])
        : [];
      for (const basinId of memberIds) {
        if (typeof basinId === 'string' && zoneId) {
          mapping[basinId] = zoneId;
        }
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
      if (typeof basinId === 'string') {
        mapping[basinId] = feature as Feature;
      }
    }
    return mapping;
  }, [basins]);

  const effectiveBasinAssignments = useMemo(
    () => ({ ...initialDraftAssignments, ...draftBasinAssignments }),
    [draftBasinAssignments, initialDraftAssignments],
  );

  const suggestedZoneSummaries = useMemo(() => {
    const summaries: Array<{
      id: string;
      defaultName: string;
      family?: string | null;
      basinCount: number;
      superficieHa: number;
    }> = [];

    for (const [zoneId, zoneDef] of Object.entries(zoneDefinitionById)) {
      let basinCount = 0;
      let superficieHa = 0;
      for (const [basinId, assignedZoneId] of Object.entries(effectiveBasinAssignments)) {
        if (assignedZoneId !== zoneId) continue;
        basinCount += 1;
        const feature = basinFeatureById[basinId];
        superficieHa += Number(feature?.properties?.superficie_ha || 0);
      }

      summaries.push({
        id: zoneId,
        defaultName: zoneDef.defaultName,
        family: zoneDef.family,
        basinCount,
        superficieHa,
      });
    }

    return summaries;
  }, [basinFeatureById, effectiveBasinAssignments, zoneDefinitionById]);

  const activeLegendItems = useMemo(() => {
    if (!hasApprovedZones || !approvedZones) {
      return [];
    }

    return approvedZones.features.map((feature) => ({
      color: (feature.properties?.__color as string | undefined) || '#1971c2',
      label: String(feature.properties?.nombre || 'Zona aprobada'),
      type: 'fill',
    }));
  }, [approvedZones, hasApprovedZones]);

  const suggestedZonesDisplay = useMemo(() => {
    if (!basins) return null;
    return {
      type: 'FeatureCollection' as const,
      features: basins.features
        .filter((feature) => typeof feature.properties?.id === 'string')
        .map((feature) => {
          const basinId = String(feature.properties?.id);
          const zoneId = effectiveBasinAssignments[basinId];
          const zoneDef = zoneDefinitionById[zoneId];
          const renamed = zoneId ? suggestedZoneNames[zoneId] : null;
          return {
            ...feature,
            properties: {
              ...(feature.properties ?? {}),
              draft_zone_id: zoneId ?? null,
              nombre: renamed && renamed.trim().length > 0 ? renamed : zoneDef?.defaultName ?? 'Sin zona',
              family: zoneDef?.family ?? null,
              __color: zoneDef?.color ?? '#868e96',
            },
          };
        }),
    };
  }, [basins, effectiveBasinAssignments, suggestedZoneNames, zoneDefinitionById]);

  useEffect(() => {
    if (!suggestedZones) return;
    setSuggestedZoneNames((prev) => {
      const next = { ...prev };
      for (const feature of suggestedZones.features) {
        const zoneId = String(feature.properties?.draft_zone_id || '');
        const defaultName = String(feature.properties?.nombre || 'Zona sugerida');
        if (zoneId && next[zoneId] === undefined) {
          next[zoneId] = defaultName;
        }
      }
      return next;
    });
  }, [suggestedZones]);

  useEffect(() => {
    if (hasApprovedZones && approvedZonesHistory.length > 0) {
      const current = approvedZonesHistory.find((item) => item.version === approvedVersion) ?? approvedZonesHistory[0];
      if (current) {
        setApprovalName(current.nombre || 'Zonificación Consorcio aprobada');
        setApprovalNotes(current.notes || '');
      }
      return;
    }
    setApprovalName('Zonificación Consorcio aprobada');
    setApprovalNotes('');
  }, [approvedVersion, approvedZonesHistory, hasApprovedZones]);

  useEffect(() => {
    if (hasApprovedZones && approvalName.trim()) {
      setExportTitle(approvalName.trim());
    }
  }, [approvalName, hasApprovedZones]);

  useEffect(() => {
    if (is2DViewInitialized) return;
    hydrateSharedViewState('map2d', {
      visibleVectors: {
        roads: true,
        waterways: true,
        approved_zones: false,
        basins: false,
        zona: !hasApprovedZones,
        cuencas: false,
        soil: false,
        catastro: false,
        public_layers: false,
        infrastructure: false,
      },
    });
  }, [hasApprovedZones, hydrateSharedViewState, is2DViewInitialized]);

  useEffect(() => {
    if (hasApprovedZones) {
      setShowSuggestedZonesPanel(false);
    }
  }, [hasApprovedZones]);

  useEffect(() => {
    setDraftBasinAssignments({});
    setSelectedDraftBasinId(null);
    setDraftDestinationZoneId(null);
  }, [suggestedZones]);

  const handleSuggestedZoneNameChange = useCallback((zoneId: string, value: string) => {
    setSuggestedZoneNames((prev) => ({ ...prev, [zoneId]: value }));
  }, []);

  const selectedDraftBasin = useMemo(() => {
    if (!selectedDraftBasinId) return null;
    return basinFeatureById[selectedDraftBasinId] ?? null;
  }, [basinFeatureById, selectedDraftBasinId]);

  const handleApplyDraftBasinMove = useCallback(() => {
    if (!selectedDraftBasinId || !draftDestinationZoneId) return;
    setDraftBasinAssignments((prev) => ({
      ...prev,
      [selectedDraftBasinId]: draftDestinationZoneId,
    }));
  }, [draftDestinationZoneId, selectedDraftBasinId]);

  const handleApproveSuggestedZones = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/api/v2/geo/basins/approved-zones/build`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          assignments: draftBasinAssignments,
          zone_names: suggestedZoneNames,
        }),
      });

      if (!response.ok) {
        throw new Error(`Error aprobando zonas: ${response.status}`);
      }

      const featureCollection = (await response.json()) as GeoJSON.FeatureCollection;
      await saveApprovedZones(featureCollection, {
        assignments: draftBasinAssignments,
        zoneNames: suggestedZoneNames,
        nombre: approvalName.trim() || 'Zonificación Consorcio aprobada',
        notes: approvalNotes.trim() || null,
      });
      notifications.show({
        title: 'Zonificación aprobada',
        message: 'La propuesta quedó guardada en backend y ya puede usarse en 2D/3D.',
        color: 'green',
      });
    } catch (_error) {
      notifications.show({
        title: 'Error',
        message: 'No se pudo aprobar la zonificación propuesta.',
        color: 'red',
      });
    }
  }, [approvalName, approvalNotes, draftBasinAssignments, saveApprovedZones, suggestedZoneNames]);

  const handleClearApprovedZones = useCallback(async () => {
    try {
      await clearApprovedZones();
      notifications.show({
        title: 'Zonificación aprobada limpiada',
        message: 'Se quitó la versión aprobada guardada en backend.',
        color: 'gray',
      });
    } catch {
      notifications.show({
        title: 'Error',
        message: 'No se pudo limpiar la zonificación aprobada.',
        color: 'red',
      });
    }
  }, [clearApprovedZones]);

  const handleRestoreApprovedZoneVersion = useCallback(async (id: string) => {
    try {
      const restored = await restoreApprovedZonesVersion(id);
      notifications.show({
        title: 'Versión restaurada',
        message: `La zonificación aprobada volvió a la versión ${restored.version}.`,
        color: 'green',
      });
    } catch {
      notifications.show({
        title: 'Error',
        message: 'No se pudo restaurar la versión seleccionada.',
        color: 'red',
      });
    }
  }, [restoreApprovedZonesVersion]);

  const handleExportApprovedZonesGeoJSON = useCallback(() => {
    if (!approvedZones) {
      notifications.show({
        title: 'Sin zonificación aprobada',
        message: 'Primero tenés que tener una zonificación aprobada para exportar.',
        color: 'yellow',
      });
      return;
    }

    const blob = new Blob([JSON.stringify(approvedZones, null, 2)], {
      type: 'application/geo+json;charset=utf-8',
    });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    const versionSuffix = approvedVersion ? `_v${approvedVersion}` : '';
    link.href = url;
    link.download = `zonificacion_consorcio_aprobada${versionSuffix}.geojson`;
    link.click();
    window.URL.revokeObjectURL(url);
  }, [approvedVersion, approvedZones]);

  const captureMapCanvas = useCallback(async () => {
    const exportTarget = mapWrapperRef.current as HTMLDivElement | null;
    if (!exportTarget) {
      throw new Error('No se encontró el contenedor del mapa.');
    }

    setCaptureMode(true);
    await new Promise((resolve) => window.requestAnimationFrame(() => resolve(undefined)));
    await new Promise((resolve) => window.requestAnimationFrame(() => resolve(undefined)));

    try {
      return await html2canvas(exportTarget, {
        backgroundColor: '#ffffff',
        useCORS: true,
        scale: 2,
        logging: false,
      });
    } finally {
      setCaptureMode(false);
    }
  }, []);

  const handleExportApprovedZonesPdf = useCallback(async () => {
    if (!approvedZones) {
      notifications.show({
        title: 'Sin zonificación aprobada',
        message: 'Primero tenés que tener una zonificación aprobada para exportar.',
        color: 'yellow',
      });
      return;
    }

    try {
      setExportingMap(true);

      const canvas = await captureMapCanvas();
      const mapImageDataUrl = canvas.toDataURL('image/png');

      const zoneLegend = activeLegendItems.map((item) => ({
        label: item.label,
        color: item.color,
      }));

      const roadLegend = consorcios.map((consorcio) => ({
        label: `${consorcio.codigo} — ${consorcio.nombre}`,
        color: consorcio.color,
        detail: `${consorcio.longitud_km.toFixed(1)} km`,
      }));

      const rasterLegends = visibleRasterLayers
        .map((layer) => {
          const config = LAYER_LEGEND_CONFIG[layer.tipo];
          if (!config) return null;

          if (config.categorical && config.categories) {
            const hiddenSet = new Set(hiddenClasses[layer.tipo] ?? []);
            return {
              label: config.label,
              items: config.categories
                .map((category, index) => ({
                  label: category.label,
                  color: category.color,
                  hidden: hiddenSet.has(index),
                }))
                .filter((item) => !item.hidden)
                .map(({ label, color }) => ({ label, color })),
            };
          }

          if (config.ranges) {
            const hiddenSet = new Set(hiddenRanges[layer.tipo] ?? []);
            return {
              label: config.label,
              items: config.ranges
                .map((range, index) => ({
                  label: range.label,
                  color: range.color,
                  hidden: hiddenSet.has(index),
                }))
                .filter((item) => !item.hidden)
                .map(({ label, color }) => ({ label, color })),
            };
          }

          return {
            label: config.label,
            items: [
              {
                label: `${config.min}${config.unit ? ` ${config.unit}` : ''} – ${config.max}${config.unit ? ` ${config.unit}` : ''}`,
                color: config.colorStops.at(-1) ?? '#888888',
              },
            ],
          };
        })
        .filter((group): group is { label: string; items: Array<{ label: string; color: string }> } => !!group && group.items.length > 0);

      const zoneSummary = approvedZones.features.map((feature) => ({
        name: String(feature.properties?.nombre || 'Zona'),
        subcuencas: Number(feature.properties?.basin_count || 0),
        areaHa: Number(feature.properties?.superficie_ha || 0).toFixed(1),
        color: String(feature.properties?.__color || '#1971c2'),
      }));

      const response = await fetch(`${API_URL}/api/v2/geo/basins/approved-zones/current/export-map-pdf`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          title: '',
          subtitle: '',
          mapImageDataUrl,
          zoneLegend,
          roadLegend,
          rasterLegends,
          zoneSummary,
        }),
      });
      if (!response.ok) throw new Error('Error al generar PDF');
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = formatExportFilename(exportTitle.trim() || approvalName.trim() || 'mapa_consorcio', 'pdf');
      link.click();
      window.URL.revokeObjectURL(url);
    } catch {
      notifications.show({
        title: 'Error',
        message: 'No se pudo generar el PDF de la zonificación aprobada.',
        color: 'red',
      });
    } finally {
      setExportingMap(false);
    }
  }, [
    activeLegendItems,
    approvalName,
    approvalNotes,
    approvedAt,
    approvedVersion,
    approvedZones,
    captureMapCanvas,
    consorcios,
      exportTitle,
      hasApprovedZones,
      hiddenClasses,
      hiddenRanges,
    visibleRasterLayers,
  ]);

  const handleOpenApprovedZonesPdf = useCallback(async () => {
    if (!approvedZones) {
      notifications.show({
        title: 'Sin zonificación aprobada',
        message: 'Primero tenés que tener una zonificación aprobada para exportar.',
        color: 'yellow',
      });
      return;
    }

    try {
      setExportingMap(true);

      const canvas = await captureMapCanvas();
      const mapImageDataUrl = canvas.toDataURL('image/png');

      const zoneLegend = activeLegendItems.map((item) => ({
        label: item.label,
        color: item.color,
      }));

      const roadLegend = consorcios.map((consorcio) => ({
        label: `${consorcio.codigo} — ${consorcio.nombre}`,
        color: consorcio.color,
        detail: `${consorcio.longitud_km.toFixed(1)} km`,
      }));

      const rasterLegends = visibleRasterLayers
        .map((layer) => {
          const config = LAYER_LEGEND_CONFIG[layer.tipo];
          if (!config) return null;

          if (config.categorical && config.categories) {
            const hiddenSet = new Set(hiddenClasses[layer.tipo] ?? []);
            return {
              label: config.label,
              items: config.categories
                .map((category, index) => ({
                  label: category.label,
                  color: category.color,
                  hidden: hiddenSet.has(index),
                }))
                .filter((item) => !item.hidden)
                .map(({ label, color }) => ({ label, color })),
            };
          }

          if (config.ranges) {
            const hiddenSet = new Set(hiddenRanges[layer.tipo] ?? []);
            return {
              label: config.label,
              items: config.ranges
                .map((range, index) => ({
                  label: range.label,
                  color: range.color,
                  hidden: hiddenSet.has(index),
                }))
                .filter((item) => !item.hidden)
                .map(({ label, color }) => ({ label, color })),
            };
          }

          return {
            label: config.label,
            items: [
              {
                label: `${config.min}${config.unit ? ` ${config.unit}` : ''} – ${config.max}${config.unit ? ` ${config.unit}` : ''}`,
                color: config.colorStops.at(-1) ?? '#888888',
              },
            ],
          };
        })
        .filter((group): group is { label: string; items: Array<{ label: string; color: string }> } => !!group && group.items.length > 0);

      const zoneSummary = approvedZones.features.map((feature) => ({
        name: String(feature.properties?.nombre || 'Zona'),
        subcuencas: Number(feature.properties?.basin_count || 0),
        areaHa: Number(feature.properties?.superficie_ha || 0).toFixed(1),
        color: String(feature.properties?.__color || '#1971c2'),
      }));

      const response = await fetch(`${API_URL}/api/v2/geo/basins/approved-zones/current/export-map-pdf`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          title: '',
          subtitle: '',
          mapImageDataUrl,
          zoneLegend,
          roadLegend,
          rasterLegends,
          zoneSummary,
        }),
      });
      if (!response.ok) throw new Error('Error al generar PDF');
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      window.open(url, '_blank', 'noopener,noreferrer');

      setTimeout(() => {
        window.URL.revokeObjectURL(url);
      }, 60_000);
    } catch {
      notifications.show({
        title: 'Error',
        message: 'No se pudo abrir el PDF cartográfico.',
        color: 'red',
      });
    } finally {
      setExportingMap(false);
    }
  }, [
    activeLegendItems,
    approvedZones,
    captureMapCanvas,
    consorcios,
    hiddenClasses,
    hiddenRanges,
    visibleRasterLayers,
  ]);

  const handleExportCleanMapPng = useCallback(async () => {
    setExportingMap(true);
    setExportPngModalOpen(false);

    try {
      const exportTarget = mapWrapperRef.current?.parentElement as HTMLDivElement | null;
      if (!exportTarget) {
        throw new Error('No se pudo preparar la exportación del mapa.');
      }

      setCaptureMode(true);
      await new Promise((resolve) => window.requestAnimationFrame(() => resolve(undefined)));
      await new Promise((resolve) => window.requestAnimationFrame(() => resolve(undefined)));

      const canvas = await html2canvas(exportTarget, {
        backgroundColor: '#ffffff',
        useCORS: true,
        scale: 2,
        logging: false,
      });

      const url = canvas.toDataURL('image/png');
      const link = document.createElement('a');
      link.href = url;
      link.download = formatExportFilename(exportTitle, 'png');
      link.click();

      notifications.show({
        title: 'PNG exportado',
        message: 'Se descargó una imagen limpia del mapa.',
        color: 'green',
      });
    } catch {
      notifications.show({
        title: 'Error',
        message: 'No se pudo exportar el mapa como PNG.',
        color: 'red',
      });
    } finally {
      setCaptureMode(false);
      setExportingMap(false);
    }
  }, [exportTitle]);

  // Get selected satellite image from localStorage (set in ImageExplorer)
  const selectedImage = useSelectedImageListener();

  // Get comparison mode (set in ImageExplorer)
  const imageComparison = useImageComparisonListener();
  const isComparisonAvailable = !!(imageComparison?.left && imageComparison?.right);

  // View mode state - determines what satellite imagery to show
  const [viewMode, setViewMode] = useState<ViewMode>('base');

  // Auto-switch to best available mode when options change
  // biome-ignore lint/correctness/useExhaustiveDependencies: only trigger on availability changes
  useEffect(() => {
    // If single image becomes available and we're on base, switch to single (preferred default)
    if (selectedImage && viewMode === 'base') {
      setViewMode('single');
    }
    // If comparison becomes available and we're on base (and no single image), switch to comparison
    else if (isComparisonAvailable && viewMode === 'base' && !selectedImage) {
      setViewMode('comparison');
    }
    // If current mode is no longer available, switch to best available
    else if (viewMode === 'comparison' && !isComparisonAvailable) {
      setViewMode(selectedImage ? 'single' : 'base');
    } else if (viewMode === 'single' && !selectedImage) {
      setViewMode(isComparisonAvailable ? 'comparison' : 'base');
    }
  }, [isComparisonAvailable, !!selectedImage]);

  // Slider position for comparison (lifted state)
  const [sliderPosition, setSliderPosition] = useState(50);

  // Determine what to show based on view mode
  const showComparison = viewMode === 'comparison' && isComparisonAvailable;
  const showSingleImage = viewMode === 'single' && !!selectedImage;

  // Ref to the map wrapper for slider positioning
  const mapWrapperRef = useRef<HTMLDivElement>(null);

  // Clear selected image
  const _handleClearImage = useCallback(() => {
    localStorage.removeItem('consorcio_selected_image');
    window.dispatchEvent(new CustomEvent('selectedImageChange', { detail: null }));
  }, []);

  // Clear comparison
  const handleClearComparison = useCallback(() => {
    localStorage.removeItem('consorcio_image_comparison');
    window.dispatchEvent(new CustomEvent('imageComparisonChange', { detail: null }));
  }, []);

  // Track which elements have been processed to avoid duplicate listeners
  const processedElementsRef = useRef(new WeakSet<Element>());

  // Memoized event handler for feature interactions
  // Incluye soporte para teclado (WCAG 2.1.1)
  const onEachFeature = useCallback((feature: Feature, layer: Path) => {
    // Obtener el nombre de la feature para el aria-label
    const featureName = feature.properties?.nombre || feature.properties?.name || 'Region del mapa';

    layer.on({
      click: () => {
        setSelectedFeature(feature);
      },
      mouseover: (e: LeafletMouseEvent) => {
        const targetLayer = e.target;
        targetLayer.setStyle({
          weight: 4,
          fillOpacity: 0.3,
        });
      },
      mouseout: (e: LeafletMouseEvent) => {
        const targetLayer = e.target;
        targetLayer.setStyle({
          weight: 2,
          fillOpacity: 0.1,
        });
      },
    });

    // Agregar soporte de teclado al elemento del layer
    const element = layer.getElement?.();
    if (element && !processedElementsRef.current.has(element)) {
      // Mark as processed to avoid duplicate listeners
      processedElementsRef.current.add(element);

      // Hacer focusable
      element.setAttribute('tabindex', '0');
      element.setAttribute('role', 'button');
      element.setAttribute('aria-label', `Ver informacion de ${featureName}`);

      // Named handlers for proper cleanup
      const handleFocus = () => {
        layer.setStyle({
          weight: 4,
          fillOpacity: 0.3,
        });
      };

      const handleBlur = () => {
        layer.setStyle({
          weight: 2,
          fillOpacity: 0.1,
        });
      };

      const handleKeydown = (e: Event) => {
        const keyEvent = e as KeyboardEvent;
        if (keyEvent.key === 'Enter' || keyEvent.key === ' ') {
          e.preventDefault();
          setSelectedFeature(feature);
        }
      };

      // Add event listeners
      element.addEventListener('focus', handleFocus);
      element.addEventListener('blur', handleBlur);
      element.addEventListener('keydown', handleKeydown);

      // Clean up listeners when layer is removed from map
      layer.on('remove', () => {
        element.removeEventListener('focus', handleFocus);
        element.removeEventListener('blur', handleBlur);
        element.removeEventListener('keydown', handleKeydown);
        processedElementsRef.current.delete(element);
      });
    }
  }, []);

  // Memoized close handler
  const handleCloseInfoPanel = useCallback(() => {
    setSelectedFeature(null);
  }, []);

  if (loading) {
    return (
      <Box pos="relative" w="100%" className={styles.mapWrapper}>
        <Skeleton height="100%" radius="md" />
        <Center className={styles.skeletonOverlay}>
          <Stack align="center" gap="md">
            <Skeleton circle height={48} width={48} />
            <Skeleton height={16} width={120} radius="md" />
          </Stack>
        </Center>
      </Box>
    );
  }

  return (
    <Box w="100%">
      <Box
        ref={mapWrapperRef}
        pos="relative"
        w="100%"
        className={`${styles.mapWrapper}${captureMode ? ` ${styles.captureMode}` : ''}`}
      >
      <MapContainer
        key={mapInstanceId}
        center={center}
        zoom={zoom}
        preferCanvas={true}
        style={{ width: '100%', height: '100%', cursor: isOperator && markingMode ? 'crosshair' : 'grab' }}
        scrollWheelZoom={true}
        zoomDelta={0.25}
        zoomSnap={0.25}
        wheelPxPerZoomLevel={360}
      >
        <Pane name="selectedImageBasePane" style={{ zIndex: 250 }} />
        <Pane name="analysisOverlayPane" style={{ zIndex: 420 }} />
        <Pane name="vectorOverlayPane" style={{ zIndex: 450 }} />
        <MapViewUpdater center={center} zoom={zoom} />
        <AddPointEvents onMapClick={handleMapClick} enabled={isOperator && markingMode} />
        {/* Forzar recalculo del tamano del mapa en primera carga */}
        <MapReadyHandler />
        <OverlayTracker
          allGeoLayers={allGeoLayers}
          waterwayIdsByName={waterwayIdsByName}
          onVisibleChange={setVisibleRasterLayers}
          onRasterFocusChange={(tipo) => setSharedActiveRasterType('map2d', tipo)}
          onVectorVisibilityChange={(layerId, visible) =>
            setSharedVectorVisibility('map2d', layerId, visible)
          }
        />
        <LayersControl position="topright">
          {/* Capas base */}
          <LayersControl.BaseLayer name="OpenStreetMap">
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
          </LayersControl.BaseLayer>

          <LayersControl.BaseLayer checked name="Satelite">
            <TileLayer
              attribution="&copy; Esri"
              url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
            />
          </LayersControl.BaseLayer>

          {/* Capas overlay - stable keys to avoid unnecessary remounts */}
          {!hasApprovedZones && capas.zona && (
            <LayersControl.Overlay
              checked={sharedVisibleVectors.zona ?? !hasApprovedZones}
              name="Zona Consorcio (manual histórica)"
            >
              <GeoJSON key="zona" data={capas.zona} style={GEE_LAYER_STYLES.zona} />
            </LayersControl.Overlay>
          )}

          <LayersControl.Overlay
            checked={sharedVisibleVectors.ign_historico ?? false}
            name="IGN Altimetría histórica"
          >
            <ImageOverlay
              url={IGN_HISTORIC_OVERLAY.image}
              bounds={IGN_HISTORIC_OVERLAY.bounds}
              opacity={0.78}
              zIndex={350}
              interactive={false}
            />
          </LayersControl.Overlay>

          {approvedZones && approvedZones.features.length > 0 && (
            <LayersControl.Overlay
              checked={sharedVisibleVectors.approved_zones ?? false}
              name="Zonificación Consorcio aprobada"
            >
              <GeoJSON
                key="approved-zones"
                data={approvedZones}
                style={(feature) => ({
                  color: (feature?.properties?.__color as string) || '#1971c2',
                  weight: 3,
                  fillOpacity: 0.2,
                  fillColor: (feature?.properties?.__color as string) || '#1971c2',
                })}
                onEachFeature={(feature, layer) => {
                  const props = feature.properties || {};
                  layer.bindTooltip(
                    `<b>${props.nombre || 'Zona aprobada'}</b><br/>Subcuencas: ${props.basin_count || 0}<br/>Sup: ${props.superficie_ha ? Number(props.superficie_ha).toFixed(1) + ' ha' : '-'}`,
                    { sticky: true },
                  );
                  layer.on({
                    click: () => setSelectedFeature(feature),
                    mouseover: (e) => {
                      e.target.setStyle({ weight: 4, fillOpacity: 0.28 });
                    },
                    mouseout: (e) => {
                      e.target.setStyle({ weight: 3, fillOpacity: 0.2 });
                    },
                  });
                }}
              />
            </LayersControl.Overlay>
          )}

          {/* Subcuencas operativas from PostGIS */}
          {basins && basins.features.length > 0 && (
            <LayersControl.Overlay
              checked={false}
              name="Subcuencas Operativas"
            >
              <GeoJSON
                key="basins"
                data={basins}
                style={(feature) => {
                  const basinId =
                    typeof feature?.properties?.id === 'string' ? String(feature.properties.id) : null;
                  const zoneId = basinId ? effectiveBasinAssignments[basinId] : null;
                  const zoneDef = zoneId ? zoneDefinitionById[zoneId] : null;
                  const isSelected = basinId !== null && basinId === selectedDraftBasinId;
                  return {
                    color: isSelected ? '#ffd43b' : '#00897B',
                    weight: isSelected ? 3 : 1.5,
                    fillOpacity: 0.12,
                    fillColor: zoneDef?.color || '#00897B',
                  };
                }}
                onEachFeature={(feature, layer) => {
                  const props = feature.properties || {};
                  layer.bindTooltip(
                    `<b>${props.nombre || 'Zona'}</b><br/>Cuenca: ${props.cuenca || '-'}<br/>Sup: ${props.superficie_ha ? Number(props.superficie_ha).toFixed(1) + ' ha' : '-'}<br/>Zona sugerida: ${(() => {
                      const basinId = typeof props.id === 'string' ? props.id : null;
                      const zoneId = basinId ? effectiveBasinAssignments[basinId] : null;
                      return zoneId
                        ? suggestedZoneNames[zoneId] || zoneDefinitionById[zoneId]?.defaultName || zoneId
                        : '-';
                    })()}`,
                    { sticky: true }
                  );
                  layer.on({
                    click: () => {
                      setSelectedFeature(feature);
                      const basinId = typeof feature.properties?.id === 'string' ? feature.properties.id : null;
                      setSelectedDraftBasinId(basinId);
                      if (basinId) {
                        setDraftDestinationZoneId(effectiveBasinAssignments[basinId] ?? null);
                      }
                    },
                    mouseover: (e) => {
                      e.target.setStyle({ weight: 3, fillOpacity: 0.2 });
                    },
                    mouseout: (e) => {
                      e.target.setStyle({ weight: 1.5, fillOpacity: 0.08 });
                    },
                  });
                }}
              />
            </LayersControl.Overlay>
          )}

          {!hasApprovedZones && suggestedZonesDisplay && suggestedZonesDisplay.features.length > 0 && (
            <LayersControl.Overlay checked={false} name="Zonas sugeridas (draft desde subcuencas)">
              <GeoJSON
                key="suggested-zones"
                data={suggestedZonesDisplay}
                style={(feature) => ({
                  color: (feature?.properties?.__color as string) || '#1971c2',
                  weight: 2,
                  fillOpacity: 0.14,
                  fillColor: (feature?.properties?.__color as string) || '#1971c2',
                })}
                onEachFeature={(feature, layer) => {
                  const props = feature.properties || {};
                  layer.bindTooltip(
                    `<b>${props.nombre || 'Zona sugerida'}</b><br/>Familia: ${props.family || '-'}<br/>Subcuencas: ${props.basin_count || 0}<br/>Sup: ${props.superficie_ha ? Number(props.superficie_ha).toFixed(1) + ' ha' : '-'}`,
                    { sticky: true },
                  );
                  layer.on({
                    click: () => setSelectedFeature(feature),
                    mouseover: (e) => {
                      e.target.setStyle({ weight: 3, fillOpacity: 0.22 });
                    },
                    mouseout: (e) => {
                      e.target.setStyle({ weight: 2, fillOpacity: 0.14 });
                    },
                  });
                }}
              />
            </LayersControl.Overlay>
          )}

          {soilMap && soilMap.features.length > 0 && (
            <LayersControl.Overlay checked={sharedVisibleVectors.soil ?? false} name="Suelos IDECOR 1:50.000">
              <GeoJSON
                key="soil-map"
                data={soilMap}
                style={(feature) => ({
                  color: '#6d4c41',
                  weight: 0.8,
                  fillOpacity: 0.35,
                  fillColor: getSoilColor(
                    (feature?.properties as { cap?: string | null } | null)?.cap,
                  ),
                })}
                onEachFeature={(feature, layer) => {
                  const props = (feature.properties ?? {}) as {
                    simbolo?: string | null;
                    cap?: string | null;
                    ip?: number | null;
                  };

                  layer.bindTooltip(
                    `<b>${props.simbolo || 'Unidad de suelo'}</b><br/>Capacidad: ${props.cap || '-'}<br/>IP: ${props.ip ?? '-'}`,
                    { sticky: true },
                  );
                }}
              />
            </LayersControl.Overlay>
          )}

          {catastroMap && catastroMap.features.length > 0 && (
            <LayersControl.Overlay checked={sharedVisibleVectors.catastro ?? false} name="Catastro rural IDECOR">
              <GeoJSON
                key="catastro-rural-map"
                data={catastroMap}
                style={() => ({
                  color: '#ffffff',
                  weight: 0.7,
                  opacity: 0.85,
                  fillOpacity: 0,
                })}
                onEachFeature={(feature, layer) => {
                  const props = (feature.properties ?? {}) as {
                    Nomenclatura?: string | null;
                    desig_oficial?: string | null;
                    departamento?: string | null;
                    pedania?: string | null;
                    Superficie_Tierra_Rural?: number | null;
                    Nro_Cuenta?: string | null;
                  };

                  const superficieHa =
                    typeof props.Superficie_Tierra_Rural === 'number'
                      ? (props.Superficie_Tierra_Rural / 10000).toFixed(1)
                      : null;

                  layer.bindPopup(
                    `<b>${props.Nomenclatura || 'Parcela rural'}</b><br/>Designación: ${props.desig_oficial || '-'}<br/>Pedanía: ${props.pedania || '-'}<br/>Departamento: ${props.departamento || '-'}<br/>Superficie: ${superficieHa ? `${superficieHa} ha` : '-'}<br/>Cuenta: ${props.Nro_Cuenta || '-'}`,
                    {
                      closeButton: true,
                      autoClose: true,
                      closeOnClick: false,
                    },
                  );

                  layer.on({
                    click: () => {
                      layer.openPopup();
                    },
                    mouseover: (e) => {
                      e.target.setStyle({
                        weight: 1.8,
                        opacity: 1,
                        color: '#ffe066',
                      });
                    },
                    mouseout: (e) => {
                      e.target.setStyle({
                        weight: 0.7,
                        opacity: 0.85,
                        color: '#ffffff',
                      });
                    },
                  });
                }}
              />
            </LayersControl.Overlay>
          )}

          {/* DEM pipeline raster layers as XYZ tile overlays */}
          {demLayers.map((layer) => {
            const layerHidden = hiddenClasses[layer.tipo] ?? [];
            const layerHiddenRanges = hiddenRanges[layer.tipo] ?? [];
            const tileUrl = buildTileUrl(layer.id, {
              hideClasses: layerHidden.length > 0 ? layerHidden : undefined,
              hideRanges: layerHiddenRanges.length > 0 ? layerHiddenRanges : undefined,
            });
            return (
              <LayersControl.Overlay
                key={`dem-${layer.id}`}
                checked={sharedActiveRasterType === layer.tipo}
                name={`DEM: ${GEO_LAYER_LABELS[layer.tipo] || layer.nombre}`}
              >
                <DynamicTileLayer
                  url={tileUrl}
                  pane="analysisOverlayPane"
                  opacity={0.7}
                  zIndex={420}
                  maxZoom={18}
                  maxNativeZoom={12}
                  tms={false}
                  crossOrigin="anonymous"
                />
              </LayersControl.Overlay>
            );
          })}

          {/* Composite analysis layers (flood risk, drainage need) */}
          {compositeLayers.map((layer) => {
            const layerHidden = hiddenClasses[layer.tipo] ?? [];
            const layerHiddenRanges = hiddenRanges[layer.tipo] ?? [];
            const tileUrl = buildTileUrl(layer.id, {
              hideClasses: layerHidden.length > 0 ? layerHidden : undefined,
              hideRanges: layerHiddenRanges.length > 0 ? layerHiddenRanges : undefined,
            });
            return (
            <LayersControl.Overlay
              key={`composite-${layer.id}`}
              checked={sharedActiveRasterType === layer.tipo}
              name={GEO_LAYER_LABELS[layer.tipo] || layer.nombre}
            >
              <DynamicTileLayer
                url={tileUrl}
                pane="analysisOverlayPane"
                opacity={0.7}
                zIndex={420}
                maxZoom={18}
                maxNativeZoom={12}
                tms={false}
                crossOrigin="anonymous"
              />
            </LayersControl.Overlay>
            );
          })}

          {/* Martin MVT: zonas_operativas coloreadas por riesgo hidráulico */}
          <LayersControl.Overlay
            checked={sharedVisibleVectors.hydraulic_risk ?? false}
            name="Riesgo Hidráulico (zonas)"
          >
            <MartinVectorLayer
              tileUrl={getMartinTileUrl('zonas_operativas')}
              layerName="zonas_operativas"
              pane="vectorOverlayPane"
              minZoom={8}
              enabled={sharedVisibleVectors.hydraulic_risk ?? false}
              style={{
                fill: true,
                fillColor: '#3b82f6',
                fillOpacity: 0.35,
                color: '#1d4ed8',
                weight: 1.5,
                opacity: 0.8,
              }}
              featureStyle={(props) => {
                const zonaId = props['id'] as string | undefined;
                const fillColor = getZonaFillColor(zonaId, zonaRiskColors);
                return { fillColor, color: fillColor };
              }}
            />
          </LayersControl.Overlay>

          {/* Martin MVT: puntos de conflicto de infraestructura */}
          <LayersControl.Overlay
            checked={sharedVisibleVectors.puntos_conflicto ?? false}
            name={MARTIN_SOURCES.puntos_conflicto.label}
          >
            <MartinVectorLayer
              tileUrl={getMartinTileUrl(MARTIN_SOURCES.puntos_conflicto.table)}
              layerName={MARTIN_SOURCES.puntos_conflicto.table}
              pane="vectorOverlayPane"
              enabled={sharedVisibleVectors.puntos_conflicto ?? false}
              style={MARTIN_SOURCES.puntos_conflicto.style}
            />
          </LayersControl.Overlay>

          {/* Martin MVT: sugerencias de canal generadas por análisis */}
          <LayersControl.Overlay
            checked={sharedVisibleVectors.canal_suggestions ?? false}
            name={MARTIN_SOURCES.canal_suggestions.label}
          >
            <MartinVectorLayer
              tileUrl={getMartinTileUrl(MARTIN_SOURCES.canal_suggestions.table)}
              layerName={MARTIN_SOURCES.canal_suggestions.table}
              pane="vectorOverlayPane"
              enabled={sharedVisibleVectors.canal_suggestions ?? false}
              style={MARTIN_SOURCES.canal_suggestions.style}
            />
          </LayersControl.Overlay>

          {/* Caminos coloreados por consorcio caminero */}
          {caminos && (
            <LayersControl.Overlay checked={sharedVisibleVectors.roads ?? true} name="Red Vial (por Consorcio)">
              <GeoJSON
                key="caminos"
                data={caminos}
                style={(feature) => ({
                  color: feature?.properties?.color || '#888888',
                  weight: 2,
                  opacity: 0.9,
                })}
                onEachFeature={onEachFeature}
              />
            </LayersControl.Overlay>
          )}

          {/* Puntos de cruce potenciales (Caminos / Drenaje) */}
          {intersections && (
            <LayersControl.Overlay name="Intersecciones (Alcantarillas potenciales)">
              <GeoJSON
                data={intersections}
                pointToLayer={(_feature, latlng) =>
                  L.circleMarker(latlng, {
                    radius: 5,
                    fillColor: '#ffffff',
                    color: '#000000',
                    weight: 1,
                    opacity: 1,
                    fillOpacity: 0.8,
                  })
                }
              />
            </LayersControl.Overlay>
          )}

          {/* Public vector layers (admin-published, no auth required) */}
          {publicLayers.map((layer) => (
            <LayersControl.Overlay
              key={layer.id}
              checked={sharedVisibleVectors.public_layers ?? false}
              name={layer.nombre}
            >
              <GeoJSON
                key={`public-${layer.id}`}
                data={layer.geojson_data!}
                style={() => ({
                  color: (layer.estilo?.color as string) || '#3388ff',
                  weight: (layer.estilo?.weight as number) || 2,
                  fillOpacity: (layer.estilo?.fillOpacity as number) || 0.1,
                  fillColor: (layer.estilo?.fillColor as string) || (layer.estilo?.color as string) || '#3388ff',
                })}
                onEachFeature={onEachFeature}
              />
            </LayersControl.Overlay>
          ))}

          {/* Hidrografia — waterway overlay layers (off by default) */}
          {waterways.map((wl) => (
            <LayersControl.Overlay
              key={`ww-${wl.id}`}
              checked={sharedVisibleVectors[`waterways_${wl.id}`] ?? sharedVisibleVectors.waterways ?? true}
              name={`Hidro: ${wl.nombre}`}
            >
              <GeoJSON
                key={`ww-data-${wl.id}`}
                data={wl.data}
                style={() => wl.style}
              />
            </LayersControl.Overlay>
          ))}

          {/* Activos de Infraestructura Registrados - show only when there is data */}
          {assets.length > 0 && (
            <LayersControl.Overlay checked={sharedVisibleVectors.infrastructure ?? false} name="Activos de Infraestructura">
              <FeatureGroup>
                {assets.map((asset) => {
                  const assetColor =
                    asset.tipo === 'puente'
                      ? '#f03e3e'
                      : asset.tipo === 'alcantarilla'
                        ? '#1971c2'
                        : asset.tipo === 'canal'
                          ? '#2f9e44'
                          : '#fd7e14';

                  return (
                    <CircleMarker
                      key={asset.id}
                      center={[asset.latitud, asset.longitud]}
                      radius={markingMode ? 4 : 10}
                      pathOptions={{
                        fillColor: assetColor,
                        color: '#ffffff',
                        weight: 2,
                        fillOpacity: 0.9,
                      }}
                    >
                      <LeafletTooltip direction="top" offset={[0, -10]}>
                        <Text size="xs" fw={700}>
                          {asset.nombre}
                        </Text>
                      </LeafletTooltip>
                      <Popup>
                        <Stack gap={4}>
                          <Text fw={700} size="sm">
                            {asset.nombre}
                          </Text>
                          <Badge size="xs" variant="outline" color={assetColor}>
                            {asset.tipo.toUpperCase()}
                          </Badge>
                          <Divider my={4} />
                          <Text size="xs">
                            Estado: <b>{asset.estado_actual.toUpperCase()}</b>
                          </Text>
                          <Text size="xs" c="dimmed">
                            Cuenca: {asset.cuenca}
                          </Text>
                          <Text size="xs" c="dimmed">
                            Ult. Insp:{' '}
                            {asset.ultima_inspeccion ? formatDate(asset.ultima_inspeccion) : 'Nunca'}
                          </Text>
                          <Group gap={4} mt="xs">
                            <Button size="compact-xs" variant="light" color="violet">
                              Bitacora
                            </Button>
                            <Button
                              size="compact-xs"
                              variant="outline"
                              leftSection={<IconDownload size={12} />}
                              onClick={() => handleExportAsset(asset.id, asset.nombre)}
                            >
                              Ficha PDF
                            </Button>
                          </Group>
                        </Stack>
                      </Popup>
                    </CircleMarker>
                  );
                })}
              </FeatureGroup>
            </LayersControl.Overlay>
          )}
        </LayersControl>

        {/* Selected satellite image should behave as a dynamic base layer under overlays */}
        {showSingleImage && selectedImage && (
          <TileLayer
            key={`selected-image-base-${selectedImage.sensor}-${selectedImage.target_date}-${selectedImage.tile_url}`}
            attribution="&copy; Google Earth Engine"
            url={selectedImage.tile_url}
            pane="selectedImageBasePane"
            opacity={1}
            zIndex={250}
            maxZoom={18}
          />
        )}

        {/* Always-visible outer boundary of the consorcio */}
        {capas.zona && (
          <GeoJSON
            key="consorcio-boundary"
            data={capas.zona}
            interactive={false}
            style={() => ({
              color: '#ffd43b',
              weight: 4,
              opacity: 0.95,
              fillOpacity: 0,
            })}
          />
        )}

        {/* Comparison layers - rendered outside LayersControl for proper z-index */}
        {showComparison && imageComparison && (
          <ComparisonLayers comparison={imageComparison} sliderPosition={sliderPosition} />
        )}
      </MapContainer>

      {/* Comparison slider UI - rendered outside MapContainer for proper mouse events */}
      {!captureMode && showComparison && imageComparison && (
        <ComparisonSliderUI
          comparison={imageComparison}
          sliderPosition={sliderPosition}
          onSliderChange={setSliderPosition}
          onClear={handleClearComparison}
          containerRef={mapWrapperRef}
        />
      )}

      {!captureMode && (
      <Box className={styles.bottomToolbar}>
        <Box className={styles.bottomToolbarRow}>
          {/* View mode panel - allows switching between base, single image, and comparison */}
          <ViewModePanel
            viewMode={viewMode}
            onViewModeChange={setViewMode}
            hasSingleImage={!!selectedImage}
            hasComparison={isComparisonAvailable}
            singleImageInfo={
              selectedImage ? { sensor: selectedImage.sensor, date: selectedImage.target_date } : null
            }
            comparisonInfo={
              imageComparison?.left && imageComparison?.right
                ? {
                    leftDate: imageComparison.left.target_date,
                    rightDate: imageComparison.right.target_date,
                  }
                : null
            }
          />

          {canManageZoning && (
            <SuggestedZonesToggle
              opened={showSuggestedZonesPanel}
              onToggle={() => setShowSuggestedZonesPanel((prev) => !prev)}
              hasApprovedZones={hasApprovedZones}
            />
          )}

          {/* Boton Modo Marcacion — solo visible para admin/operador */}
          {isOperator && (
            <Paper
              shadow="md"
              p="xs"
              radius="md"
              style={{ background: 'light-dark(rgba(255,255,255,0.94), rgba(36,36,36,0.94))', backdropFilter: 'blur(6px)' }}
            >
              <Tooltip label={markingMode ? 'Cancelar marcacion' : 'Marcar punto de interes'}>
                <Button
                  size="xs"
                  color={markingMode ? 'red' : 'blue'}
                  variant={markingMode ? 'filled' : 'light'}
                  onClick={() => {
                    setMarkingMode(!markingMode);
                    setNewPoint(null);
                  }}
                  leftSection={<IconMap size={16} />}
                >
                  {markingMode ? 'Modo Activo (Haz clic)' : 'Marcar Punto'}
                </Button>
              </Tooltip>
            </Paper>
          )}

          <Paper
            shadow="md"
            p="xs"
            radius="md"
            style={{ background: 'light-dark(rgba(255,255,255,0.94), rgba(36,36,36,0.94))', backdropFilter: 'blur(6px)' }}
          >
            <Tooltip label="Oculta controles y mueve leyendas fuera del mapa">
              <Button
                size="xs"
                variant="light"
                onClick={() => setCaptureMode(true)}
                leftSection={<IconPhoto size={16} />}
              >
                Captura
              </Button>
            </Tooltip>
          </Paper>

          <Paper
            shadow="md"
            p="xs"
            radius="md"
            style={{ background: 'light-dark(rgba(255,255,255,0.94), rgba(36,36,36,0.94))', backdropFilter: 'blur(6px)' }}
          >
            <Menu shadow="md" position="top" withinPortal>
              <Menu.Target>
                <Button
                  size="xs"
                  variant="light"
                  leftSection={<IconDownload size={16} />}
                  loading={exportingMap}
                >
                  Exportar
                </Button>
              </Menu.Target>
              <Menu.Dropdown>
                <Menu.Item
                  leftSection={<IconPhoto size={14} />}
                  onClick={() => setExportPngModalOpen(true)}
                >
                  Descargar PNG
                </Menu.Item>
                <Menu.Item
                  leftSection={<IconDownload size={14} />}
                  onClick={() => void handleExportApprovedZonesPdf()}
                  disabled={!approvedZones}
                >
                  Descargar PDF
                </Menu.Item>
                <Menu.Item
                  leftSection={<IconDownload size={14} />}
                  onClick={() => void handleOpenApprovedZonesPdf()}
                  disabled={!approvedZones}
                >
                  Abrir PDF
                </Menu.Item>
              </Menu.Dropdown>
            </Menu>
          </Paper>
        </Box>
      </Box>
      )}

      {canManageZoning && showSuggestedZonesPanel && !captureMode && (
        <SuggestedZonesPanel
          zones={suggestedZoneSummaries}
          zoneNames={suggestedZoneNames}
          onZoneNameChange={handleSuggestedZoneNameChange}
          selectedBasinName={
            selectedDraftBasin && typeof selectedDraftBasin.properties?.nombre === 'string'
              ? selectedDraftBasin.properties.nombre
              : null
          }
          selectedBasinZoneId={
            selectedDraftBasinId ? effectiveBasinAssignments[selectedDraftBasinId] ?? null : null
          }
          destinationZoneId={draftDestinationZoneId}
          onDestinationZoneChange={setDraftDestinationZoneId}
          onApplyBasinMove={handleApplyDraftBasinMove}
          hasApprovedZones={hasApprovedZones}
          approvedAt={approvedAt}
          approvedVersion={approvedVersion}
          approvedZonesHistory={approvedZonesHistory.map((item) => ({
            id: item.id,
            nombre: item.nombre,
            version: item.version,
            approvedAt: item.approvedAt,
            notes: item.notes,
            approvedByName: item.approvedByName,
          }))}
          approvalName={approvalName}
          approvalNotes={approvalNotes}
          onApprovalNameChange={setApprovalName}
          onApprovalNotesChange={setApprovalNotes}
          onClose={() => setShowSuggestedZonesPanel(false)}
          onApproveZones={handleApproveSuggestedZones}
          onClearApprovedZones={handleClearApprovedZones}
          onRestoreVersion={handleRestoreApprovedZoneVersion}
          onExportApprovedZonesGeoJSON={handleExportApprovedZonesGeoJSON}
          onExportApprovedZonesPdf={handleExportApprovedZonesPdf}
        />
      )}

      <Modal
        opened={exportPngModalOpen}
        onClose={() => setExportPngModalOpen(false)}
        title="Exportar mapa PNG"
        centered
      >
        <Stack gap="sm">
          <TextInput
            label="Título"
            placeholder="Mapa del Consorcio"
            value={exportTitle}
            onChange={(event) => setExportTitle(event.currentTarget.value)}
          />
          <Checkbox
            label="Incluir leyendas fuera del mapa"
            checked={exportIncludeLegend}
            onChange={(event) => setExportIncludeLegend(event.currentTarget.checked)}
          />
          <Checkbox
            label="Incluir título y datos de versión"
            checked={exportIncludeMetadata}
            onChange={(event) => setExportIncludeMetadata(event.currentTarget.checked)}
          />
          <Group justify="flex-end">
            <Button variant="light" onClick={() => setExportPngModalOpen(false)}>
              Cancelar
            </Button>
            <Button onClick={handleExportCleanMapPng} loading={exportingMap}>
              Descargar PNG
            </Button>
          </Group>
        </Stack>
      </Modal>

      {/* Modal Registro de Activo — solo para admin/operador */}
      <Modal
        opened={!!newPoint}
        onClose={() => setNewPoint(null)}
        title="Registrar Punto de Interes"
        centered
      >
        <form onSubmit={form.onSubmit(handleSaveAsset)}>
          <Stack gap="sm">
            <Text size="sm" c="dimmed">
              Ubicacion: {newPoint?.lat.toFixed(5)}, {newPoint?.lng.toFixed(5)}
            </Text>
            <TextInput
              label="Nombre"
              placeholder="Ej: Alcantarilla campo Perez"
              required
              {...form.getInputProps('nombre')}
            />
            <Select
              label="Tipo de Activo"
              data={[
                { value: 'alcantarilla', label: 'Alcantarilla' },
                { value: 'puente', label: 'Puente' },
                { value: 'canal', label: 'Canal (Punto)' },
                { value: 'punto_critico', label: 'Punto Critico' },
                { value: 'otro', label: 'Otro' },
              ]}
              {...form.getInputProps('tipo')}
            />
            <TextInput
              label="Descripcion"
              placeholder="Detalles sobre el estado o acceso"
              {...form.getInputProps('descripcion')}
            />
            <Select
              label="Cuenca"
              data={config?.cuencas.map((c) => ({ value: c.id, label: c.nombre })) || []}
              {...form.getInputProps('cuenca')}
            />
            <Button type="submit" loading={isSubmitting} fullWidth mt="md">
              Guardar en Bitacora
            </Button>
          </Stack>
        </form>
      </Modal>

      {!captureMode && (
      <Leyenda
        consorcios={consorcios}
        cuencasConfig={hasApprovedZones ? [] : config?.cuencas}
        customItems={activeLegendItems}
      />
      )}
      {!captureMode && (
      <RasterLegend
        layers={visibleRasterLayers}
        hiddenClasses={hiddenClasses}
        onClassToggle={handleClassToggle}
        hiddenRanges={hiddenRanges}
        onRangeToggle={handleRangeToggle}
      />
      )}
      {!captureMode && <InfoPanel feature={selectedFeature} onClose={handleCloseInfoPanel} />}
    </Box>

      {captureMode && (
        <Stack gap="sm" mt="sm">
          <Group justify="space-between" align="center" data-html2canvas-ignore="true">
            <Text size="sm" c="dimmed">
              Modo captura activo: el mapa quedó listo para exportación limpia.
            </Text>
            <Button size="xs" variant="light" onClick={() => setCaptureMode(false)}>
              Salir de captura
            </Button>
          </Group>
          {exportIncludeMetadata && (
            <Paper
              shadow="sm"
              p="md"
              radius="md"
              style={{ background: 'light-dark(rgba(255,255,255,0.96), rgba(36,36,36,0.96))' }}
            >
              <Stack gap={4}>
                <Title order={4}>{exportTitle.trim() || 'Mapa del Consorcio'}</Title>
                <Text size="sm" c="dimmed">
                  {hasApprovedZones && approvedVersion
                    ? `Versión aprobada v${approvedVersion}${approvedAt ? ` • ${new Date(approvedAt).toLocaleString()}` : ''}`
                    : `Exportado el ${new Date().toLocaleString()}`}
                </Text>
              </Stack>
            </Paper>
          )}
          {exportIncludeLegend && (
            <Group align="flex-start" gap="sm" wrap="wrap">
              <Leyenda
                consorcios={consorcios}
                cuencasConfig={hasApprovedZones ? [] : config?.cuencas}
                customItems={activeLegendItems}
                floating={false}
              />
              <RasterLegend
                layers={visibleRasterLayers}
                hiddenClasses={hiddenClasses}
                onClassToggle={handleClassToggle}
                hiddenRanges={hiddenRanges}
                onRangeToggle={handleRangeToggle}
                floating={false}
              />
            </Group>
          )}
        </Stack>
      )}
    </Box>
  );
}
