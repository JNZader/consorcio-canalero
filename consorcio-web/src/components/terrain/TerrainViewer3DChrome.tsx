import { Box, Button, Group, Loader, Paper, Slider, Stack, Text, Title } from '@mantine/core';
import type { Feature } from 'geojson';
import type { GeoLayerInfo } from '../../hooks/useGeoLayers';
import type { Etapa } from '../../types/canales';
import type { BpaEnrichedFile, BpaHistoryFile } from '../../types/pilarVerde';

import { InfoPanel } from '../map2d/InfoPanel';
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
  /**
   * 5-key record sourced from `mapLayerSyncStore.propuestasEtapasVisibility`.
   * Forwarded untouched into the toggles panel's Canales CollapsibleSection so
   * the conditional `<PropuestasEtapasFilter>` can render its 5 rows. Optional
   * so legacy tests/pages that don't care about Pilar Azul can skip it.
   */
  etapasVisibility?: Readonly<Record<Etapa, boolean>>;
  /** Parent-owned setter for a single etapa (delegates to the store). */
  onSetEtapaVisible?: (etapa: Etapa, visible: boolean) => void;
  /**
   * Phase 4 (Batch E) — visibility flags forwarded to
   * `<TerrainLegendsPanel>` so each of the 7 conditional Pilar Verde +
   * Canales legend blocks can gate its own render. Derived by
   * `TerrainViewer3D` from `mapLayerSyncStore.map3d.visibleVectors`.
   *
   * Optional for backwards compatibility — pre-Batch-E callers that don't
   * care about Pilar Verde / Canales legends can skip them and the panel
   * falls back to the pre-existing raster + soil legends.
   */
  bpaHistoricoVisible?: boolean;
  agroAceptadaVisible?: boolean;
  agroPresentadaVisible?: boolean;
  agroZonasVisible?: boolean;
  porcentajeForestacionVisible?: boolean;
  canalesRelevadosVisible?: boolean;
  canalesPropuestosVisible?: boolean;
  /**
   * Phase 5 (Batch F) — click-driven InfoPanel overlay. Renders
   * absolutely-positioned above the terrain chrome via the shared
   * `.infoPanel` CSS class (position: absolute, z-index: 1000). Empty
   * array ⇒ panel unmounts. Optional so pre-Phase-5 tests can skip it.
   */
  selectedFeatures?: readonly Feature[];
  onCloseInfoPanel?: () => void;
  /** Pilar Verde enriched catastro dataset — forwarded to `<InfoPanel>`. */
  bpaEnriched?: BpaEnrichedFile | null;
  /** Pilar Verde histórico lookup — forwarded to `<InfoPanel>`. */
  bpaHistory?: BpaHistoryFile | null;
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
  etapasVisibility,
  onSetEtapaVisible,
  bpaHistoricoVisible,
  agroAceptadaVisible,
  agroPresentadaVisible,
  agroZonasVisible,
  porcentajeForestacionVisible,
  canalesRelevadosVisible,
  canalesPropuestosVisible,
  selectedFeatures,
  onCloseInfoPanel,
  bpaEnriched,
  bpaHistory,
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
              bpaHistoricoVisible={bpaHistoricoVisible}
              agroAceptadaVisible={agroAceptadaVisible}
              agroPresentadaVisible={agroPresentadaVisible}
              agroZonasVisible={agroZonasVisible}
              porcentajeForestacionVisible={porcentajeForestacionVisible}
              canalesRelevadosVisible={canalesRelevadosVisible}
              canalesPropuestosVisible={canalesPropuestosVisible}
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
              etapasVisibility={etapasVisibility}
              onSetEtapaVisible={onSetEtapaVisible}
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

        {/*
          Phase 5 (Batch F) — click-driven InfoPanel overlay. Rendered INSIDE
          the relative Paper so the shared `.infoPanel` CSS module class
          (position: absolute, top: calc(spacing.md + 108px), right:
          spacing.md, z-index: 1000) is scoped to the 3D canvas. `z-index:
          1000` sits above the toggles button (`zIndex: 16`) and the chrome
          panels (`zIndex: 16`), so the panel always wins on overlap.
        */}
        {selectedFeatures && selectedFeatures.length > 0 && onCloseInfoPanel && (
          <InfoPanel
            features={selectedFeatures}
            onClose={onCloseInfoPanel}
            bpaEnriched={bpaEnriched}
            bpaHistory={bpaHistory}
          />
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
