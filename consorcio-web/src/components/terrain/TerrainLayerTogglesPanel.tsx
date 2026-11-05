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
 *
 * Phase 3 (Batch D) of `pilar-verde-y-canales-3d` — extends the panel with:
 *   - "Pilar Verde" CollapsibleSection: 5 checkboxes (one per PV layer).
 *   - "Canales" CollapsibleSection: 2 master toggles (relevados + propuestos).
 *
 * Per-canal (43) checkboxes are now rendered in 3D v2 — the 3D chrome is
 * 280px wide and scroll is enabled (maxHeight + overflowY: auto), so all
 * rows fit. Power users no longer need to switch to 2D for per-canal control.
 *
 * NOTE: The propuestos etapas filter (Alta → Largo plazo) used to live here
 * as a `<PropuestasEtapasFilter>` subsection. It moved to the legend
 * (`TerrainLegendsPanel`) as interactive checkboxes — single source of truth
 * for both the swatch colors AND the toggle controls.
 */

import { Box, CloseButton, Paper, Select, Slider, Stack, Text } from '@mantine/core';

import { GEO_LAYER_LABELS, type GeoLayerInfo } from '../../hooks/useGeoLayers';
import styles from '../../styles/components/map/classNames';
import { CollapsibleSection } from '../ui/CollapsibleSection';

/**
 * When `true`, the panel renders WITHOUT the absolute-positioning styles
 * (top/right/width/maxHeight) so the parent can place it inline (e.g. in a
 * bottom bar grid below the map). When `false` (default) the panel keeps
 * the legacy floating overlay behavior.
 */
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
  /** Optional — when omitted, no close button is rendered (used in embedded mode). */
  readonly onClose?: () => void;
  readonly hasApprovedZones: boolean;
  /**
   * When `true`, the panel renders inline (no `position: absolute`, no fixed
   * width/maxHeight). The parent is expected to place it inside a layout
   * grid below the map. Defaults to `false` (legacy floating overlay).
   */
  readonly embedded?: boolean;
  /** Whether to render the inline overlay opacity slider (false when LayerControlsPanel fine control handles __dem opacity). */
  readonly showOpacitySlider?: boolean;
}

export function TerrainLayerTogglesPanel({
  rasterLayers,
  selectedImageOption = null,
  activeRasterLayerId,
  onActiveRasterLayerChange,
  overlayOpacity,
  onOverlayOpacityChange,
  onClose,
  hasApprovedZones,
  embedded = false,
  showOpacitySlider = true,
}: TerrainLayerTogglesPanelProps) {
  const rasterOptions = rasterLayers.map((layer) => ({
    value: layer.id,
    // `layer.label` ya trae el sufijo "(escenario)" cuando corresponde. Usar
    // GEO_LAYER_LABELS[tipo] mostraria "Acumulacion de Flujo" tanto para la
    // capa operativa como para la de escenario — indistinguibles.
    label: layer.label ?? GEO_LAYER_LABELS[layer.tipo] ?? layer.nombre,
  }));
  const noneOverlayOption = { value: '__none__', label: 'Sin overlay (solo relieve)' };
  const allRasterOptions = selectedImageOption
    ? [noneOverlayOption, selectedImageOption, ...rasterOptions]
    : [noneOverlayOption, ...rasterOptions];

  return (
    <Paper
      shadow="md"
      p="sm"
      radius="md"
      className={styles.layerTogglesRoot}
      data-testid="terrain-3d-toggles-panel"
      style={
        embedded
          ? {
              background: 'light-dark(rgba(255,255,255,0.96), rgba(36,36,36,0.96))',
              backdropFilter: 'blur(6px)',
            }
          : {
              position: 'absolute',
              top: 56,
              right: 12,
              zIndex: 15,
              width: 280,
              maxHeight: 'calc(100vh - 96px)',
              overflowY: 'auto',
              background: 'light-dark(rgba(255,255,255,0.96), rgba(36,36,36,0.96))',
              backdropFilter: 'blur(6px)',
            }
      }
    >
      <CollapsibleSection
        title="Capas 3D"
        testId="terrain-3d-toggles"
        titleSize="sm"
        titleWeight={600}
        rightAccessory={
          onClose ? (
            <CloseButton
              size="sm"
              onClick={(event) => {
                // Prevent the click from bubbling to the collapse toggle — the
                // close button owns its own behavior (the user closes the
                // chrome entirely, it is NOT a collapse gesture).
                event.stopPropagation();
                onClose();
              }}
              aria-label="Cerrar panel 3D"
            />
          ) : null
        }
      >
        <Stack gap="sm">
          <Box>
            <Text size="xs" c="dimmed">
              {hasApprovedZones
                ? 'Las cuencas tienen prioridad visual. Podés combinarlas con subcuencas y overlays raster sobre el relieve.'
                : 'Las capas vectoriales siguen al mapa 2D. Los overlays raster se drapean sobre el DEM.'}
            </Text>
          </Box>

          <Box>
            <Text size="xs" fw={600} mb={4}>
              Overlay raster activo
            </Text>
            <Select
              size="xs"
              clearable
              data={allRasterOptions}
              value={activeRasterLayerId ?? '__none__'}
              onChange={(value) => {
                onActiveRasterLayerChange(!value || value === '__none__' ? null : value);
              }}
              placeholder="Sin overlay (solo relieve)"
              nothingFoundMessage="Sin capas raster"
            />
          </Box>

          {showOpacitySlider ? (
            <Box pb={20}>
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
          ) : null}
        </Stack>
      </CollapsibleSection>
    </Paper>
  );
}
