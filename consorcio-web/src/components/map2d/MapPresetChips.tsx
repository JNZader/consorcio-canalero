import { Button, Group, Text } from '@mantine/core';

import { useMapLayerSyncStore } from '../../stores/mapLayerSyncStore';
import { MAP_PRESETS } from './mapPresets';

/**
 * Thematic view chips (UX PDF R1). Applying a preset does not lock the
 * catalog — the next manual toggle marks the selection as Personalizado.
 */
export function MapPresetChips() {
  const applyPreset = useMapLayerSyncStore((state) => state.applyPreset);
  const activePresetId = useMapLayerSyncStore((state) => state.presetByView.map2d);

  return (
    <Group gap={6} wrap="wrap" data-testid="map-preset-chips">
      {MAP_PRESETS.map((preset) => (
        <Button
          key={preset.id}
          size="compact-xs"
          variant={activePresetId === preset.id ? 'filled' : 'light'}
          data-testid={`map-preset-${preset.id}`}
          title={preset.description}
          onClick={() => applyPreset('map2d', preset.id)}
        >
          {preset.label}
        </Button>
      ))}
      {activePresetId === 'custom' && (
        <Text size="xs" c="dimmed" data-testid="map-preset-custom">
          Personalizado
        </Text>
      )}
    </Group>
  );
}
