import { Group, Paper, SegmentedControl, Stack, Text } from '@mantine/core';
import { type ReactNode, memo } from 'react';

interface MapBaseSelectorPanelProps {
  readonly baseLayer: 'osm' | 'satellite';
  readonly onBaseLayerChange: (value: 'osm' | 'satellite') => void;
  /**
   * Optional slot — typically a `<ViewModePanel>` rendered only when
   * `baseLayer === 'satellite'`. The parent decides when to show it.
   */
  readonly viewModePanel?: ReactNode;
}

export const MapBaseSelectorPanel = memo(function MapBaseSelectorPanel({
  baseLayer,
  onBaseLayerChange,
  viewModePanel,
}: MapBaseSelectorPanelProps) {
  return (
    <Paper
      shadow="xs"
      p="xs"
      radius="md"
      data-testid="map-base-selector-panel"
      style={{
        background: 'light-dark(rgba(255,255,255,0.94), rgba(36,36,36,0.94))',
        backdropFilter: 'blur(6px)',
      }}
    >
      <Group gap="md" wrap="wrap" align="flex-start">
        <Stack gap={4} miw={180}>
          <Text size="xs" fw={600} c="dimmed">
            Capa base
          </Text>
          <SegmentedControl
            size="xs"
            aria-label="Seleccionar capa base"
            value={baseLayer}
            onChange={(value) => onBaseLayerChange(value as 'osm' | 'satellite')}
            data={[
              { value: 'osm', label: 'OSM' },
              { value: 'satellite', label: 'Satélite' },
            ]}
          />
        </Stack>
        {viewModePanel}
      </Group>
    </Paper>
  );
});
