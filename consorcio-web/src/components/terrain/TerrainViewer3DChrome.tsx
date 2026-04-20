import {
  Box,
  Button,
  Group,
  Loader,
  Paper,
  Slider,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import type { GeoLayerInfo } from '../../hooks/useGeoLayers';

import { TerrainLayerTogglesPanel } from './TerrainLayerTogglesPanel';
import { TerrainLegendsPanel } from './TerrainLegendsPanel';

interface SelectedImageOption {
  value: string;
  label: string;
}

interface SelectedImageSummary {
  sensor: string;
  target_date: string;
}

interface TerrainViewer3DChromeProps {
  exaggeration: number;
  onExaggerationChange: (value: number) => void;
  minExaggeration: number;
  maxExaggeration: number;
  height: number | string;
  mapContainerRef: React.RefObject<HTMLDivElement | null>;
  showLayerPanel: boolean;
  onToggleLayerPanel: () => void;
  rasterLayers: GeoLayerInfo[];
  selectedImageOption: SelectedImageOption | null;
  activeRasterType?: string;
  activeRasterLayerId?: string;
  onActiveRasterLayerChange: (value: string | null) => void;
  overlayOpacity: number;
  onOverlayOpacityChange: (value: number) => void;
  hiddenClasses: Record<string, number[]>;
  onClassToggle: (layerType: string, classIndex: number, visible: boolean) => void;
  hiddenRanges: Record<string, number[]>;
  onRangeToggle: (layerType: string, rangeIndex: number, visible: boolean) => void;
  vectorLayerVisibility: Record<string, boolean>;
  onVectorLayerToggle: (layerId: string, visible: boolean) => void;
  hasApprovedZones: boolean;
  ready: boolean;
  selectedImage: SelectedImageSummary | null;
}

export function TerrainViewer3DChrome({
  exaggeration,
  onExaggerationChange,
  minExaggeration,
  maxExaggeration,
  height,
  mapContainerRef,
  showLayerPanel,
  onToggleLayerPanel,
  rasterLayers,
  selectedImageOption,
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
  hasApprovedZones,
  ready,
  selectedImage,
}: TerrainViewer3DChromeProps) {
  return (
    <>
      <Group justify="space-between" align="flex-end">
        <Title order={5}>Vista 3D del Terreno</Title>
        <Group gap="xs" align="center">
          <Text size="xs" c="dimmed">
            Exageracion vertical:
          </Text>
          <Box w={160}>
            <Slider
              value={exaggeration}
              onChange={onExaggerationChange}
              min={minExaggeration}
              max={maxExaggeration}
              step={1}
              size="xs"
              label={(val) => `${val}x`}
              marks={[
                { value: 1, label: '1x' },
                { value: 50, label: '50x' },
                { value: 100, label: '100x' },
              ]}
            />
          </Box>
        </Group>
      </Group>

      <Paper
        radius="md"
        withBorder
        style={{
          height: typeof height === 'number' ? `${height}px` : height,
          position: 'relative',
          overflow: 'hidden',
        }}
      >
        <div ref={mapContainerRef} style={{ width: '100%', height: '100%' }} />

        <Paper
          shadow="md"
          p="xs"
          radius="md"
          style={{
            position: 'absolute',
            top: 12,
            right: 12,
            zIndex: 16,
            background: 'light-dark(rgba(255,255,255,0.94), rgba(36,36,36,0.94))',
            backdropFilter: 'blur(6px)',
          }}
        >
          <Button size="xs" variant="light" onClick={onToggleLayerPanel}>
            {showLayerPanel ? 'Ocultar capas y overlays 3D' : 'Ver capas y overlays 3D'}
          </Button>
        </Paper>

        {showLayerPanel && (
          <>
            {/*
              Phase 8 Fix 5/6 — legends moved OUT of the toggles panel into a
              sibling. Rendered side-by-side so layer toggles (right) and
              legends (left-of-toggles) no longer compete for vertical space.
            */}
            <TerrainLegendsPanel
              activeRasterType={activeRasterType}
              hiddenClasses={hiddenClasses}
              onClassToggle={onClassToggle}
              hiddenRanges={hiddenRanges}
              onRangeToggle={onRangeToggle}
              vectorLayerVisibility={vectorLayerVisibility}
            />
            <TerrainLayerTogglesPanel
              rasterLayers={rasterLayers}
              selectedImageOption={selectedImageOption}
              activeRasterLayerId={activeRasterLayerId}
              onActiveRasterLayerChange={onActiveRasterLayerChange}
              overlayOpacity={overlayOpacity}
              onOverlayOpacityChange={onOverlayOpacityChange}
              vectorLayerVisibility={vectorLayerVisibility}
              onVectorLayerToggle={onVectorLayerToggle}
              onClose={onToggleLayerPanel}
              hasApprovedZones={hasApprovedZones}
            />
          </>
        )}

        {!ready && (
          <Box
            style={{
              position: 'absolute',
              inset: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: 'rgba(0,0,0,0.5)',
              zIndex: 20,
            }}
          >
            <Stack align="center" gap="md">
              <Loader size="lg" color="white" />
              <Text c="white">Cargando terreno 3D...</Text>
            </Stack>
          </Box>
        )}

        <Box
          style={{
            position: 'absolute',
            bottom: 12,
            right: 12,
            background: 'rgba(0,0,0,0.7)',
            borderRadius: 8,
            padding: '8px 12px',
            zIndex: 10,
          }}
        >
          <Text size="xs" c="white" fw={600} mb={4}>
            Terreno 3D
          </Text>
          <Text size="xs" c="gray.4">
            Exageracion: {exaggeration}x
          </Text>
          {selectedImage && (
            <Text size="xs" c="gray.4">
              Imagen seleccionada: {selectedImage.sensor} {selectedImage.target_date}
            </Text>
          )}
          <Text size="xs" c="gray.4">
            Ctrl+arrastre para rotar
          </Text>
        </Box>
      </Paper>
    </>
  );
}
