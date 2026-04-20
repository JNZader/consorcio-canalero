import { Box, Checkbox, CloseButton, Group, Paper, Select, Slider, Stack, Text } from '@mantine/core';
import { RasterLegend } from '../RasterLegend';
import { GEO_LAYER_LABELS, type GeoLayerInfo } from '../../hooks/useGeoLayers';
import {
  SOIL_CAPABILITY_COLORS,
  SOIL_CAPABILITY_LABELS,
  SOIL_CAPABILITY_ORDER,
} from '../../hooks/useSoilMap';
import { PRIORITY_3D_VECTOR_LAYERS } from './terrainLayerConfig';

interface TerrainLayerPanelProps {
  readonly rasterLayers: GeoLayerInfo[];
  readonly selectedImageOption?: {
    value: string;
    label: string;
  } | null;
  readonly activeRasterType?: string;
  readonly activeRasterLayerId?: string;
  readonly onActiveRasterLayerChange: (layerId: string) => void;
  readonly overlayOpacity: number;
  readonly onOverlayOpacityChange: (value: number) => void;
  readonly hiddenClasses: Record<string, number[]>;
  readonly onClassToggle: (layerType: string, classIndex: number, visible: boolean) => void;
  readonly hiddenRanges: Record<string, number[]>;
  readonly onRangeToggle: (layerType: string, rangeIndex: number, visible: boolean) => void;
  readonly vectorLayerVisibility: Record<string, boolean>;
  readonly onVectorLayerToggle: (layerId: string, visible: boolean) => void;
  readonly onClose: () => void;
  readonly hasApprovedZones: boolean;
}

export function TerrainLayerPanel({
  rasterLayers,
  selectedImageOption = null,
  activeRasterType,
  activeRasterLayerId,
  onActiveRasterLayerChange,
  overlayOpacity,
  onOverlayOpacityChange,
  hiddenClasses,
  onClassToggle,
  hiddenRanges,
  onRangeToggle,
  vectorLayerVisibility,
  onVectorLayerToggle,
  onClose,
  hasApprovedZones,
}: TerrainLayerPanelProps) {
  const rasterOptions = rasterLayers.map((layer) => ({
    value: layer.id,
    label: GEO_LAYER_LABELS[layer.tipo] || layer.nombre,
  }));
  const allRasterOptions = selectedImageOption
    ? [selectedImageOption, ...rasterOptions]
    : rasterOptions;

  return (
    <Paper
      shadow="md"
      p="sm"
      radius="md"
      style={{
        position: 'absolute',
        top: 56,
        right: 12,
        zIndex: 15,
        width: 280,
        maxHeight: 'calc(100% - 24px)',
        overflowY: 'auto',
        background: 'light-dark(rgba(255,255,255,0.96), rgba(36,36,36,0.96))',
        backdropFilter: 'blur(6px)',
      }}
    >
      <Stack gap="sm">
        <Box>
          <Group justify="space-between" align="flex-start" wrap="nowrap">
            <Box style={{ flex: 1 }}>
              <Text size="sm" fw={600} mb={4}>
                Capas 3D
              </Text>
              <Text size="xs" c="dimmed">
                {hasApprovedZones
                  ? 'Las cuencas tienen prioridad visual. Podés combinarlas con subcuencas y overlays raster sobre el relieve.'
                  : 'La vista 2D y la vista 3D se mantienen por separado. Esta vista muestra overlays drapeados sobre el DEM.'}
              </Text>
            </Box>
            <CloseButton size="sm" onClick={onClose} aria-label="Cerrar panel 3D" />
          </Group>
        </Box>

        <Box>
          <Text size="xs" fw={600} mb={4}>
            Overlay raster activo
          </Text>
          <Select
            size="xs"
            data={allRasterOptions}
            value={activeRasterLayerId ?? null}
            onChange={(value) => {
              if (value) onActiveRasterLayerChange(value);
            }}
            placeholder="Seleccionar overlay"
            nothingFoundMessage="Sin capas raster"
          />
        </Box>

        <Box>
          <Text size="xs" fw={600} mb={4}>
            Opacidad del overlay
          </Text>
          <Slider
            size="xs"
            min={0}
            max={100}
            step={5}
            value={Math.round(overlayOpacity * 100)}
            onChange={(value) => onOverlayOpacityChange(value / 100)}
            label={(value) => `${value}%`}
            marks={[
              { value: 0, label: '0%' },
              { value: 50, label: '50%' },
              { value: 100, label: '100%' },
            ]}
          />
        </Box>

        {activeRasterType && (
          <RasterLegend
            layers={[{ tipo: activeRasterType }]}
            hiddenClasses={hiddenClasses}
            onClassToggle={onClassToggle}
            hiddenRanges={hiddenRanges}
            onRangeToggle={onRangeToggle}
            floating={false}
          />
        )}

        <Box>
          <Text size="xs" fw={600} mb={4}>
            Capas vectoriales 3D
          </Text>
          <Stack gap={4}>
            {PRIORITY_3D_VECTOR_LAYERS.map((layer) => (
              <Checkbox
                key={layer.id}
                size="xs"
                checked={vectorLayerVisibility[layer.id] ?? false}
                disabled={layer.status !== 'supported'}
                onChange={(event) => onVectorLayerToggle(layer.id, event.currentTarget.checked)}
                label={
                  layer.status === 'supported'
                    ? layer.label
                    : `${layer.label} (${layer.status === 'planned' ? 'pendiente' : layer.status})`
                }
              />
            ))}
          </Stack>
        </Box>

        {vectorLayerVisibility.soil && <SoilLegend />}
      </Stack>
    </Paper>
  );
}

/**
 * Legend for the "Suelos IDECOR 1:50.000" vector layer rendered in 3D.
 *
 * Colors come from `SOIL_CAPABILITY_COLORS` in `useSoilMap.ts` — the same
 * map feeds the MapLibre paint in `terrainVectorLayerEffects.ts`, so the
 * legend can never drift from the rendered polygons.
 *
 * Labels are the Spanish IDECOR soil-capability class descriptors (I–VIII).
 */
function SoilLegend() {
  return (
    <Box data-testid="terrain-3d-soil-legend">
      <Text size="xs" fw={600} mb={4}>
        Suelos — Clases de capacidad (IDECOR)
      </Text>
      <Stack gap={2}>
        {SOIL_CAPABILITY_ORDER.map((cap) => {
          const color = SOIL_CAPABILITY_COLORS[cap];
          const label = SOIL_CAPABILITY_LABELS[cap];
          return (
            <Group
              key={cap}
              gap={6}
              wrap="nowrap"
              data-testid={`terrain-3d-soil-legend-chip-${cap}`}
            >
              <Box
                data-soil-swatch="true"
                style={{
                  background: color,
                  width: 14,
                  height: 14,
                  borderRadius: 'var(--mantine-radius-xs)',
                  flexShrink: 0,
                }}
              />
              <Text size="xs" c="dimmed">
                {cap} — {label}
              </Text>
            </Group>
          );
        })}
      </Stack>
    </Box>
  );
}
