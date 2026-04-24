import { Box, Checkbox, Group, Paper, Stack, Text } from '@mantine/core';
import { memo } from 'react';
import { LAYER_LEGEND_CONFIG } from '../config/rasterLegend';
import styles from '../styles/components/map.module.css';

interface RasterLegendProps {
  /** Currently visible raster layer types */
  readonly layers: Array<{ tipo: string }>;
  /** Hidden class indices per layer type (e.g. { terrain_class: [1, 3] }) */
  readonly hiddenClasses?: Record<string, number[]>;
  /** Callback when a categorical class is toggled */
  readonly onClassToggle?: (layerType: string, classIndex: number, visible: boolean) => void;
  /** Hidden range indices per layer type (e.g. { flood_risk: [0, 2] }) */
  readonly hiddenRanges?: Record<string, number[]>;
  /** Callback when a continuous range is toggled */
  readonly onRangeToggle?: (layerType: string, rangeIndex: number, visible: boolean) => void;
  /** Render as floating map panel (default) or inline content */
  readonly floating?: boolean;
}

/**
 * Compact legend for raster tile overlays.
 * Renders a horizontal gradient bar with min/max labels for continuous layers,
 * and interactive checkboxes for categorical layers.
 */
export const RasterLegend = memo(function RasterLegend({
  layers,
  hiddenClasses = {},
  onClassToggle,
  hiddenRanges = {},
  onRangeToggle,
  floating = true,
}: RasterLegendProps) {
  const legendEntries = layers
    .map((l) => ({ tipo: l.tipo, config: LAYER_LEGEND_CONFIG[l.tipo] }))
    .filter((entry) => entry.config != null);

  if (legendEntries.length === 0) return null;

  return (
    <Paper
      shadow="md"
      p="xs"
      radius="md"
      className={floating ? styles.rasterLegendPanel : undefined}
      style={
        floating
          ? undefined
          : {
              background: 'light-dark(rgba(255,255,255,0.92), rgba(36,36,36,0.92))',
            }
      }
    >
      <Stack gap={6}>
        {legendEntries.map(({ tipo, config }) => {
          if (config.categorical && config.categories) {
            const hidden = new Set(hiddenClasses[tipo] ?? []);

            return (
              <Box key={tipo}>
                <Text size="xs" fw={600} mb={4}>
                  {config.label}
                </Text>
                <Stack gap={2}>
                  {config.categories.map((cat, idx) => {
                    const isVisible = !hidden.has(idx);
                    return (
                      <Group
                        key={cat.label}
                        gap={6}
                        wrap="nowrap"
                        style={{ cursor: onClassToggle ? 'pointer' : 'default' }}
                        onClick={() => onClassToggle?.(tipo, idx, !isVisible)}
                      >
                        <Checkbox
                          size="xs"
                          checked={isVisible}
                          onClick={(event) => event.stopPropagation()}
                          onChange={() => onClassToggle?.(tipo, idx, !isVisible)}
                          styles={{
                            input: { cursor: 'pointer' },
                            root: { display: 'flex', alignItems: 'center' },
                          }}
                          aria-label={`${isVisible ? 'Ocultar' : 'Mostrar'} ${cat.label} en ${config.label}`}
                        />
                        <Box
                          style={{
                            background: isVisible ? cat.color : '#ccc',
                            width: 14,
                            height: 14,
                            borderRadius: 'var(--mantine-radius-xs)',
                            flexShrink: 0,
                            opacity: isVisible ? 1 : 0.4,
                            transition: 'background 150ms ease, opacity 150ms ease',
                          }}
                        />
                        <Text
                          size="xs"
                          c={isVisible ? 'dimmed' : undefined}
                          style={{
                            opacity: isVisible ? 1 : 0.4,
                            transition: 'opacity 150ms ease',
                          }}
                        >
                          {cat.label}
                        </Text>
                      </Group>
                    );
                  })}
                </Stack>
              </Box>
            );
          }

          // Continuous layer with toggleable ranges
          if (config.ranges && config.ranges.length > 0) {
            const hiddenSet = new Set(hiddenRanges[tipo] ?? []);

            return (
              <Box key={tipo}>
                <Text size="xs" fw={600} mb={4}>
                  {config.label}
                </Text>
                <Stack gap={2}>
                  {config.ranges.map((range, idx) => {
                    const isVisible = !hiddenSet.has(idx);
                    return (
                      <Group
                        key={range.label}
                        gap={6}
                        wrap="nowrap"
                        style={{ cursor: onRangeToggle ? 'pointer' : 'default' }}
                        onClick={() => onRangeToggle?.(tipo, idx, !isVisible)}
                      >
                        <Checkbox
                          size="xs"
                          checked={isVisible}
                          onClick={(event) => event.stopPropagation()}
                          onChange={() => onRangeToggle?.(tipo, idx, !isVisible)}
                          styles={{
                            input: { cursor: 'pointer' },
                            root: { display: 'flex', alignItems: 'center' },
                          }}
                          aria-label={`${isVisible ? 'Ocultar' : 'Mostrar'} ${range.label} en ${config.label}`}
                        />
                        <Box
                          style={{
                            background: isVisible ? range.color : '#ccc',
                            width: 14,
                            height: 14,
                            borderRadius: 'var(--mantine-radius-xs)',
                            flexShrink: 0,
                            opacity: isVisible ? 1 : 0.4,
                            transition: 'background 150ms ease, opacity 150ms ease',
                          }}
                        />
                        <Text
                          size="xs"
                          c={isVisible ? 'dimmed' : undefined}
                          style={{
                            opacity: isVisible ? 1 : 0.4,
                            transition: 'opacity 150ms ease',
                          }}
                        >
                          {range.label}
                        </Text>
                      </Group>
                    );
                  })}
                </Stack>
              </Box>
            );
          }

          // Continuous layer without ranges — gradient bar
          const gradient = `linear-gradient(to right, ${config.colorStops.join(', ')})`;
          const minLabel = `${config.min}${config.unit ? ` ${config.unit}` : ''}`;
          const maxLabel = `${config.max}${config.unit ? ` ${config.unit}` : ''}`;

          return (
            <Box key={tipo}>
              <Text size="xs" fw={600} mb={2}>
                {config.label}
              </Text>
              <Box
                style={{
                  background: gradient,
                  width: 200,
                  height: 14,
                  borderRadius: 'var(--mantine-radius-xs)',
                }}
              />
              <Group justify="space-between" style={{ width: 200 }}>
                <Text size="xs" c="dimmed">
                  {minLabel}
                </Text>
                <Text size="xs" c="dimmed">
                  {maxLabel}
                </Text>
              </Group>
            </Box>
          );
        })}
      </Stack>
    </Paper>
  );
});
