/**
 * TerrainLegendsPanel.tsx
 *
 * Phase 8 Fix 5/6 — the "legends only" half of the split 3D chrome.
 *
 * Positioned to the LEFT of the toggles panel so both are visible
 * simultaneously without overlapping. Has a bounded `maxHeight` plus
 * internal vertical scroll, so tall legends (DEM raster with many classes,
 * soil with 8 IDECOR capability classes, future BPA gradients) don't spill
 * past the viewport nor get truncated.
 *
 * Returns `null` when nothing is visible — keeps the chrome clean when the
 * user has all layers off.
 */

import { Box, Paper, Stack, Text } from '@mantine/core';

import { RasterLegend } from '../RasterLegend';
import { CollapsibleSection } from '../ui/CollapsibleSection';
import {
  SOIL_CAPABILITY_COLORS,
  SOIL_CAPABILITY_LABELS,
  SOIL_CAPABILITY_ORDER,
} from '../../hooks/useSoilMap';

interface TerrainLegendsPanelProps {
  readonly activeRasterType?: string;
  readonly hiddenClasses: Record<string, number[]>;
  readonly onClassToggle: (layerType: string, classIndex: number, visible: boolean) => void;
  readonly hiddenRanges: Record<string, number[]>;
  readonly onRangeToggle: (layerType: string, rangeIndex: number, visible: boolean) => void;
  readonly vectorLayerVisibility: Record<string, boolean>;
}

export function TerrainLegendsPanel({
  activeRasterType,
  hiddenClasses,
  onClassToggle,
  hiddenRanges,
  onRangeToggle,
  vectorLayerVisibility,
}: TerrainLegendsPanelProps) {
  const hasRasterLegend = !!activeRasterType;
  const hasSoilLegend = !!vectorLayerVisibility.soil;

  if (!hasRasterLegend && !hasSoilLegend) return null;

  return (
    <Paper
      shadow="md"
      p="sm"
      radius="md"
      data-testid="terrain-3d-legends-panel"
      style={{
        position: 'absolute',
        top: 56,
        right: 308, // toggles panel is 280 wide at right:12 → sit 16px left of it
        zIndex: 15,
        width: 260,
        maxHeight: 'calc(100vh - 96px)',
        overflowY: 'auto',
        background: 'light-dark(rgba(255,255,255,0.96), rgba(36,36,36,0.96))',
        backdropFilter: 'blur(6px)',
      }}
    >
      <CollapsibleSection
        title="Leyendas"
        testId="terrain-3d-legends"
        titleSize="sm"
        titleWeight={600}
      >
        <Stack gap="sm">
          {hasRasterLegend && (
            <RasterLegend
              layers={[{ tipo: activeRasterType as string }]}
              hiddenClasses={hiddenClasses}
              onClassToggle={onClassToggle}
              hiddenRanges={hiddenRanges}
              onRangeToggle={onRangeToggle}
              floating={false}
            />
          )}

          {hasSoilLegend && <SoilLegend />}
        </Stack>
      </CollapsibleSection>
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
            <Box
              key={cap}
              data-testid={`terrain-3d-soil-legend-chip-${cap}`}
              style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'nowrap' }}
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
            </Box>
          );
        })}
      </Stack>
    </Box>
  );
}
