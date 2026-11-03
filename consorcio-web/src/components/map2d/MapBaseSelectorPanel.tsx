import { Group, Paper, SegmentedControl, Stack, Text } from '@mantine/core';
import { memo, type ReactNode } from 'react';

interface MapBaseSelectorPanelProps {
  readonly baseLayer: 'osm' | 'satellite';
  readonly onBaseLayerChange: (value: 'osm' | 'satellite') => void;
  /**
   * Optional slot — typically a `<ViewModePanel>` rendered only when
   * `baseLayer === 'satellite'`. The parent decides when to show it.
   */
  readonly viewModePanel?: ReactNode;
  /** Drop the floating Paper. The layers panel already owns the chrome. */
  readonly plain?: boolean;
}

export const MapBaseSelectorPanel = memo(function MapBaseSelectorPanel({
  baseLayer,
  onBaseLayerChange,
  viewModePanel,
  plain = false,
}: MapBaseSelectorPanelProps) {
  const body = (
    <Stack gap={6}>
      <Stack gap={4}>
        <Text size="xs" fw={600} c="dimmed">
          Capa base
        </Text>
        <SegmentedControl
          size="xs"
          fullWidth
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
    </Stack>
  );

  if (plain) {
    return <div data-testid="map-base-selector-panel">{body}</div>;
  }

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
        {body}
      </Group>
    </Paper>
  );
});
