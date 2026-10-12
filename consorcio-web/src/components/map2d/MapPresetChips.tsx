import { Button, Group, Stack, Text } from '@mantine/core';

import { showInfo } from '../../lib/notifications';
import { useMapLayerSyncStore } from '../../stores/mapLayerSyncStore';
import { MAP_PRESETS, type MapPresetId } from './mapPresets';

interface MapPresetChipsProps {
  readonly onApplyRaster?: (presetId: MapPresetId) => void;
}

/**
 * Thematic view chips (UX PDF R1 / UX-26). Named as tasks, not family names.
 */
export function MapPresetChips({ onApplyRaster }: MapPresetChipsProps) {
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
        {MAP_PRESETS.map((preset) => {
          const pressed = activePresetId === preset.id;
          return (
            <Button
              key={preset.id}
              size="xs"
              variant={pressed ? 'filled' : 'light'}
              data-testid={`map-preset-${preset.id}`}
              title={preset.description}
              aria-pressed={pressed}
              onClick={() => {
                applyPreset('map2d', preset.id);
                onApplyRaster?.(preset.id);
                showInfo('Vista aplicada', 'Se reemplazó la selección de capas.');
              }}
            >
              {preset.label}
            </Button>
          );
        })}
        {canUndo && (
          <Button
            size="xs"
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
