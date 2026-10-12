import { Button, Group, Stack, Text } from '@mantine/core';

import { showInfo } from '../../lib/notifications';
import { useMapLayerSyncStore } from '../../stores/mapLayerSyncStore';
import { MAP_PRESETS } from './mapPresets';

/**
 * Thematic view chips (UX PDF R1 / UX-26). Named as tasks, not family names.
 */
export function MapPresetChips() {
  const applyPreset = useMapLayerSyncStore((state) => state.applyPreset);
  const undoCatalogPreset = useMapLayerSyncStore((state) => state.undoCatalogPreset);
  const activePresetId = useMapLayerSyncStore((state) => state.presetByView.map2d);
  const canUndo = useMapLayerSyncStore((state) => state.catalogUndoByView.map2d != null);

  return (
    <Stack gap={4} data-testid="map-preset-chips">
      <Text size="xs" fw={600}>
        Vistas rápidas
      </Text>
      <Group gap={6} wrap="wrap">
        {MAP_PRESETS.map((preset) => (
          <Button
            key={preset.id}
            size="compact-xs"
            variant={activePresetId === preset.id ? 'filled' : 'light'}
            data-testid={`map-preset-${preset.id}`}
            title={preset.description}
            onClick={() => {
              applyPreset('map2d', preset.id);
              showInfo('Vista aplicada', 'Se reemplazó la selección de capas.');
            }}
          >
            {preset.label}
          </Button>
        ))}
        {canUndo && (
          <Button
            size="compact-xs"
            variant="subtle"
            data-testid="map-preset-undo"
            onClick={() => undoCatalogPreset('map2d')}
          >
            Deshacer
          </Button>
        )}
        {activePresetId === 'custom' && (
          <Text size="xs" c="dimmed" data-testid="map-preset-custom">
            Personalizado
          </Text>
        )}
      </Group>
    </Stack>
  );
}
