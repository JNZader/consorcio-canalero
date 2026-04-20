/**
 * TerrainLayerTogglesPanel.tsx
 *
 * Phase 8 Fix 5 — one half of the split 3D chrome.
 *
 * Before: a single `TerrainLayerPanel` mixed layer toggles + raster select +
 * opacity slider + soil legend + raster legend all in one block. Users
 * reported the legends were cramped and legends + toggles competed for
 * vertical space.
 *
 * Now: this component owns ONLY the input controls — overlay select,
 * opacity slider, and per-layer checkboxes. Legends live in a sibling
 * `TerrainLegendsPanel` rendered side-by-side in `TerrainViewer3DChrome`.
 */

import { Box, Checkbox, CloseButton, Group, Paper, Select, Slider, Stack, Text } from '@mantine/core';

import { GEO_LAYER_LABELS, type GeoLayerInfo } from '../../hooks/useGeoLayers';
import { PRIORITY_3D_VECTOR_LAYERS } from './terrainLayerConfig';

interface TerrainLayerTogglesPanelProps {
  readonly rasterLayers: GeoLayerInfo[];
  readonly selectedImageOption?: {
    value: string;
    label: string;
  } | null;
  readonly activeRasterLayerId?: string;
  readonly onActiveRasterLayerChange: (layerId: string | null) => void;
  readonly overlayOpacity: number;
  readonly onOverlayOpacityChange: (value: number) => void;
  readonly vectorLayerVisibility: Record<string, boolean>;
  readonly onVectorLayerToggle: (layerId: string, visible: boolean) => void;
  readonly onClose: () => void;
  readonly hasApprovedZones: boolean;
}

export function TerrainLayerTogglesPanel({
  rasterLayers,
  selectedImageOption = null,
  activeRasterLayerId,
  onActiveRasterLayerChange,
  overlayOpacity,
  onOverlayOpacityChange,
  vectorLayerVisibility,
  onVectorLayerToggle,
  onClose,
  hasApprovedZones,
}: TerrainLayerTogglesPanelProps) {
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
      data-testid="terrain-3d-toggles-panel"
      style={{
        position: 'absolute',
        top: 56,
        right: 12,
        zIndex: 15,
        width: 280,
        maxHeight: 'calc(100vh - 96px)',
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
          {/* We intentionally drop `null` from the Select's onChange — the
              chrome accepts null but the UX here is "pick a layer", not
              "clear to null". */}
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
      </Stack>
    </Paper>
  );
}
