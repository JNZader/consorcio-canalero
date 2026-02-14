import {
  ActionIcon,
  Badge,
  Box,
  Button,
  Center,
  CloseButton,
  ColorSwatch,
  Divider,
  Group,
  Modal,
  Paper,
  SegmentedControl,
  Select,
  Skeleton,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
  Tooltip,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { notifications } from '@mantine/notifications';
import type { Feature, FeatureCollection } from 'geojson';
import type { LeafletMouseEvent, Path } from 'leaflet';
import { memo, useCallback, useEffect, useId, useRef, useState } from 'react';
import { GeoJSON, FeatureGroup, LayersControl, MapContainer, TileLayer, Marker, CircleMarker, Popup, useMapEvents, useMap } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';
import { useGEELayers, GEE_LAYER_STYLES } from '../hooks/useGEELayers';
import { useCaminosColoreados, type ConsorcioInfo } from '../hooks/useCaminosColoreados';
import { useInfrastructure } from '../hooks/useInfrastructure';
import { MapReadyHandler } from '../hooks/useMapReady';
import { useSelectedImageListener, type SelectedImage } from '../hooks/useSelectedImage';
import { useImageComparisonListener } from '../hooks/useImageComparison';
import { ComparisonLayers, ComparisonSliderUI } from './MapImageComparison';
import { IconGitCompare, IconLayers, IconPhoto, IconDownload, IconMap } from './ui/icons';

import { MAP_CENTER, MAP_DEFAULT_ZOOM } from '../constants';
import { useConfigStore } from '../stores/configStore';
import { API_URL, getAuthToken } from '../lib/api';
import styles from '../styles/components/map.module.css';

// Layer names for cuencas (constant to prevent infinite re-renders)
// Caminos are loaded separately via useCaminosColoreados
const CUENCAS_LAYER_NAMES = ['zona', 'candil', 'ml', 'noroeste', 'norte'] as const;

/**
 * Renders the appropriate legend item indicator based on type.
 * Avoids nested ternary operators (SonarQube S3358).
 */
function LegendItemIndicator({ item }: { item: { color: string; type: string } }) {
  if (item.type === 'border') {
    return <Box className={styles.legendItemBorder} style={{ border: `2px solid ${item.color}` }} />;
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
}

const Leyenda = memo(function Leyenda({ consorcios = [], cuencasConfig = [] }: LeyendaProps) {
  const [showConsorcios, setShowConsorcios] = useState(false);

  // Fallback legend items if config not loaded yet
  const legendItems = cuencasConfig.length > 0
    ? [
        { color: '#FF0000', label: 'Zona Consorcio', type: 'border' },
        ...cuencasConfig.map(c => ({ color: c.color, label: `Cuenca ${c.nombre}`, type: 'fill' }))
      ]
    : [
        { color: '#FF0000', label: 'Zona Consorcio', type: 'border' },
        { color: '#2196F3', label: 'Cuenca Candil', type: 'fill' },
        { color: '#4CAF50', label: 'Cuenca ML', type: 'fill' },
        { color: '#FF9800', label: 'Cuenca Noroeste', type: 'fill' },
        { color: '#9C27B0', label: 'Cuenca Norte', type: 'fill' },
      ];

  return (
    <Paper shadow="md" p="sm" radius="md" className={styles.legendPanel} style={{ maxHeight: '80vh', overflowY: 'auto' }}>
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
            <Group gap="xs" style={{ cursor: 'pointer' }} onClick={() => setShowConsorcios(!showConsorcios)}>
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
                    <Text size="xs" truncate style={{ maxWidth: 150 }} title={`${c.nombre} - ${c.longitud_km} km`}>
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

// Panel showing currently active satellite image
interface SatelliteImagePanelProps {
  readonly image: SelectedImage;
  readonly onClear: () => void;
}

const SatelliteImagePanel = memo(function SatelliteImagePanel({ image, onClear }: SatelliteImagePanelProps) {
  return (
    <Paper
      shadow="md"
      p="sm"
      radius="md"
      style={{
        position: 'absolute',
        top: 10,
        left: 60,
        zIndex: 1000,
        maxWidth: 280,
      }}
    >
      <Group justify="space-between" gap="xs" wrap="nowrap">
        <Group gap="xs" wrap="nowrap">
          <IconPhoto size={16} color="var(--mantine-color-blue-6)" />
          <div>
            <Text size="xs" fw={600} c="blue.7">
              {image.sensor} - {image.target_date}
            </Text>
            <Text size="xs" c="dimmed">
              {image.visualization_description}
            </Text>
          </div>
        </Group>
        <CloseButton size="sm" onClick={onClear} aria-label="Quitar imagen satelital" />
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
      style={{
        position: 'absolute',
        bottom: 30,
        right: 10,
        zIndex: 1000,
      }}
    >
      <Stack gap={4}>
        <Text size="xs" fw={600} c="dimmed">
          Vista satelital
        </Text>
        <SegmentedControl
          size="xs"
          value={viewMode}
          onChange={(value) => onViewModeChange(value as ViewMode)}
          data={options}
        />
      </Stack>
    </Paper>
  );
});

// Componente para capturar clics y añadir puntos
function AddPointEvents({ onMapClick, enabled }: { onMapClick: (lat: number, lng: number) => void, enabled: boolean }) {
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

export default function MapaLeaflet() {
  // Get system configuration from store
  const config = useConfigStore((state) => state.config);

  // Use dynamic center and zoom with fallbacks
  const center = config?.map.center
    ? ([config.map.center.lat, config.map.center.lng] as [number, number])
    : MAP_CENTER;
  const zoom = config?.map.zoom ?? MAP_DEFAULT_ZOOM;

  // Unique ID for this map instance - forces clean remount on navigation
  const mapInstanceId = useId();

  // Estados para marcacion manual
  const [markingMode, setMarkingMode] = useState(false);
  const [newPoint, setNewPoint] = useState<{ lat: number, lng: number } | null>(null);
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

  // Use centralized hook for loading GEE layers (sin caminos - se cargan aparte)
  const { layers: capas, loading: loadingCapas } = useGEELayers({
    layerNames: CUENCAS_LAYER_NAMES,
  });

  // Caminos coloreados por consorcio caminero
  const { caminos, consorcios, loading: loadingCaminos } = useCaminosColoreados();

  // Infraestructura y puntos de cruce (alcantarillas potenciales)
  const { assets, intersections, loading: loadingInfra, createAsset } = useInfrastructure();

  const handleExportAsset = async (assetId: string, assetName: string) => {
    try {
      const token = await getAuthToken();
      const response = await fetch(`${API_URL}/api/v1/infrastructure/assets/${assetId}/export-pdf`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (!response.ok) throw new Error('Error al generar PDF');
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `Ficha_Tecnica_${assetName.replace(/\s+/g, '_')}.pdf`;
      a.click();
    } catch (err) {
      notifications.show({ title: 'Error', message: 'No se pudo generar la ficha tecnica', color: 'red' });
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
        tipo: values.tipo as any,
      });
      notifications.show({
        title: 'Punto registrado',
        message: `${values.nombre} ha sido guardado exitosamente`,
        color: 'green',
      });
      setNewPoint(null);
      setMarkingMode(false);
      form.reset();
    } catch (err) {
      notifications.show({
        title: 'Error',
        message: 'No se pudo guardar el punto',
        color: 'red',
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const loading = loadingCapas || loadingCaminos || loadingInfra;
  const [selectedFeature, setSelectedFeature] = useState<GeoJSON.Feature | null>(null);

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
    // If comparison becomes available and we're on base, switch to comparison
    if (isComparisonAvailable && viewMode === 'base') {
      setViewMode('comparison');
    }
    // If single image becomes available and we're on base (and no comparison), switch to single
    else if (selectedImage && viewMode === 'base' && !isComparisonAvailable) {
      setViewMode('single');
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
  const handleClearImage = useCallback(() => {
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
    <Box ref={mapWrapperRef} pos="relative" w="100%" className={styles.mapWrapper}>
      <MapContainer
        key={mapInstanceId}
        center={center}
        zoom={zoom}
        preferCanvas={true}
        style={{ width: '100%', height: '100%', cursor: markingMode ? 'crosshair' : 'grab' }}
        scrollWheelZoom={true}
      >
        <MapViewUpdater center={center} zoom={zoom} />
        <AddPointEvents onMapClick={handleMapClick} enabled={markingMode} />
        {/* Forzar recalculo del tamano del mapa en primera carga */}
        <MapReadyHandler />
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

          {/* Satellite image from Image Explorer (only when in single image mode) */}
          {showSingleImage && selectedImage && (
            <LayersControl.Overlay checked name={`${selectedImage.sensor} (${selectedImage.target_date})`}>
              <TileLayer
                url={selectedImage.tile_url}
                attribution="&copy; Google Earth Engine"
                opacity={0.85}
                maxZoom={18}
              />
            </LayersControl.Overlay>
          )}

          {/* Capas overlay - stable keys to avoid unnecessary remounts */}
          {capas.zona && (
            <LayersControl.Overlay checked name="Zona Consorcio">
              <GeoJSON key="zona" data={capas.zona} style={GEE_LAYER_STYLES.zona} />
            </LayersControl.Overlay>
          )}

          {capas.candil && (
            <LayersControl.Overlay name="Cuenca Candil">
              <GeoJSON key="candil" data={capas.candil} style={GEE_LAYER_STYLES.candil} onEachFeature={onEachFeature} />
            </LayersControl.Overlay>
          )}

          {capas.ml && (
            <LayersControl.Overlay name="Cuenca ML">
              <GeoJSON key="ml" data={capas.ml} style={GEE_LAYER_STYLES.ml} onEachFeature={onEachFeature} />
            </LayersControl.Overlay>
          )}

          {capas.noroeste && (
            <LayersControl.Overlay name="Cuenca Noroeste">
              <GeoJSON
                key="noroeste"
                data={capas.noroeste}
                style={GEE_LAYER_STYLES.noroeste}
                onEachFeature={onEachFeature}
              />
            </LayersControl.Overlay>
          )}

          {capas.norte && (
            <LayersControl.Overlay name="Cuenca Norte">
              <GeoJSON key="norte" data={capas.norte} style={GEE_LAYER_STYLES.norte} onEachFeature={onEachFeature} />
            </LayersControl.Overlay>
          )}

          {/* Caminos coloreados por consorcio caminero */}
          {caminos && (
            <LayersControl.Overlay checked name="Red Vial (por Consorcio)">
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
                pointToLayer={(feature, latlng) => (
                  L.circleMarker(latlng, {
                    radius: 5,
                    fillColor: "#ffffff",
                    color: "#000000",
                    weight: 1,
                    opacity: 1,
                    fillOpacity: 0.8
                  })
                )}
              />
            </LayersControl.Overlay>
          )}

          {/* Activos de Infraestructura Registrados - grouped in a single overlay */}
          <LayersControl.Overlay checked name="Activos de Infraestructura">
            <FeatureGroup>
              {assets.map(asset => {
                const assetColor =
                  asset.tipo === 'puente' ? '#f03e3e' :
                  asset.tipo === 'alcantarilla' ? '#1971c2' :
                  asset.tipo === 'canal' ? '#2f9e44' : '#fd7e14';

                return (
                  <CircleMarker
                    key={asset.id}
                    center={[asset.latitud, asset.longitud]}
                    radius={markingMode ? 4 : 10}
                    pathOptions={{
                      fillColor: assetColor,
                      color: '#ffffff',
                      weight: 2,
                      fillOpacity: 0.9
                    }}
                  >
                    <Tooltip direction="top" offset={[0, -10]}>
                      <Text size="xs" fw={700}>{asset.nombre}</Text>
                    </Tooltip>
                    <Popup>
                      <Stack gap={4}>
                        <Text fw={700} size="sm">{asset.nombre}</Text>
                        <Badge size="xs" variant="outline" color={assetColor}>{asset.tipo.toUpperCase()}</Badge>
                        <Divider my={4} />
                        <Text size="xs">Estado: <b>{asset.estado_actual.toUpperCase()}</b></Text>
                        <Text size="xs" c="dimmed">Cuenca: {asset.cuenca}</Text>
                        <Text size="xs" c="dimmed">Ult. Insp: {asset.ultima_inspeccion ? formatDate(asset.ultima_inspeccion) : 'Nunca'}</Text>
                        <Group gap={4} mt="xs">
                          <Button size="compact-xs" variant="light" color="violet">Bitacora</Button>
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
        </LayersControl>

        {/* Comparison layers - rendered outside LayersControl for proper z-index */}
        {showComparison && imageComparison && (
          <ComparisonLayers comparison={imageComparison} sliderPosition={sliderPosition} />
        )}
      </MapContainer>

      {/* Comparison slider UI - rendered outside MapContainer for proper mouse events */}
      {showComparison && imageComparison && (
        <ComparisonSliderUI
          comparison={imageComparison}
          sliderPosition={sliderPosition}
          onSliderChange={setSliderPosition}
          onClear={handleClearComparison}
          containerRef={mapWrapperRef}
        />
      )}

      {/* View mode panel - allows switching between base, single image, and comparison */}
      <ViewModePanel
        viewMode={viewMode}
        onViewModeChange={setViewMode}
        hasSingleImage={!!selectedImage}
        hasComparison={isComparisonAvailable}
        singleImageInfo={selectedImage ? { sensor: selectedImage.sensor, date: selectedImage.target_date } : null}
        comparisonInfo={
          imageComparison?.left && imageComparison?.right
            ? { leftDate: imageComparison.left.target_date, rightDate: imageComparison.right.target_date }
            : null
        }
      />

      {/* Boton Modo Marcacion */}
      <Paper
        shadow="md"
        p="xs"
        radius="md"
        style={{ position: 'absolute', top: 10, right: 60, zIndex: 1000 }}
      >
        <Tooltip label={markingMode ? "Cancelar marcacion" : "Marcar punto de interes"}>
          <Button
            size="xs"
            color={markingMode ? "red" : "blue"}
            variant={markingMode ? "filled" : "light"}
            onClick={() => {
              setMarkingMode(!markingMode);
              setNewPoint(null);
            }}
            leftSection={<IconMap size={16} />}
          >
            {markingMode ? "Modo Activo (Haz clic)" : "Marcar Punto"}
          </Button>
        </Tooltip>
      </Paper>

      {/* Modal Registro de Activo */}
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
              data={config?.cuencas.map(c => ({ value: c.id, label: c.nombre })) || []}
              {...form.getInputProps('cuenca')}
            />
            <Button type="submit" loading={isSubmitting} fullWidth mt="md">
              Guardar en Bitacora
            </Button>
          </Stack>
        </form>
      </Modal>

      <Leyenda consorcios={consorcios} cuencasConfig={config?.cuencas} />
      <InfoPanel feature={selectedFeature} onClose={handleCloseInfoPanel} />
    </Box>
  );
}
