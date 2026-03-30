import { Box, Group, Paper, Stack, Text } from '@mantine/core';
import { memo } from 'react';
import { LAYER_LEGEND_CONFIG } from '../config/rasterLegend';
import styles from '../styles/components/map.module.css';

interface RasterLegendProps {
  /** Currently visible raster layer types */
  readonly layers: Array<{ tipo: string }>;
}

/**
 * Compact legend for raster tile overlays.
 * Renders a horizontal gradient bar with min/max labels for each
 * visible raster layer that has a legend configuration.
 */
export const RasterLegend = memo(function RasterLegend({ layers }: RasterLegendProps) {
  const legendEntries = layers
    .map((l) => ({ tipo: l.tipo, config: LAYER_LEGEND_CONFIG[l.tipo] }))
    .filter((entry) => entry.config != null);

  if (legendEntries.length === 0) return null;

  return (
    <Paper shadow="md" p="xs" radius="md" className={styles.rasterLegendPanel}>
      <Stack gap={6}>
        {legendEntries.map(({ tipo, config }) => {
          if (config.categorical && config.categories) {
            return (
              <Box key={tipo}>
                <Text size="xs" fw={600} mb={4}>
                  {config.label}
                </Text>
                <Stack gap={2}>
                  {config.categories.map((cat) => (
                    <Group key={cat.label} gap={6} wrap="nowrap">
                      <Box
                        style={{
                          background: cat.color,
                          width: 14,
                          height: 14,
                          borderRadius: 'var(--mantine-radius-xs)',
                          flexShrink: 0,
                        }}
                      />
                      <Text size="xs" c="dimmed">
                        {cat.label}
                      </Text>
                    </Group>
                  ))}
                </Stack>
              </Box>
            );
          }

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
