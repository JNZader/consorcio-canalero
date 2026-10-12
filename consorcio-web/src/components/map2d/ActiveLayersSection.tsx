import { ActionIcon, Button, Group, Slider, Stack, Text } from '@mantine/core';
import type { ReactNode } from 'react';

import { IconEye, IconEyeOff, IconX } from '../ui/icons';

export interface ActiveLayerRow {
  id: string;
  label: string;
  legend?: ReactNode;
}

interface ActiveLayersSectionProps {
  readonly rows: readonly ActiveLayerRow[];
  readonly onRemove: (id: string) => void;
  readonly onClearAll: () => void;
  readonly onRestore: () => void;
  /** UX-08: opacity multiplier 0..1. Absent = 1. */
  readonly opacityByLayer?: Record<string, number>;
  readonly onLayerOpacityChange?: (layerId: string, multiplier: number) => void;
}

export function ActiveLayersSection({
  rows,
  onRemove,
  onClearAll,
  onRestore,
  opacityByLayer = {},
  onLayerOpacityChange,
}: ActiveLayersSectionProps) {
  return (
    <Stack gap={4} data-testid="map-active-layers">
      <Group justify="space-between" wrap="nowrap">
        <Text size="xs" fw={600}>
          En el mapa ({rows.length})
        </Text>
        <Group gap={4} wrap="nowrap">
          <Button size="xs" variant="subtle" data-testid="map-active-restore" onClick={onRestore}>
            Volver a lo predeterminado
          </Button>
          <Button
            size="xs"
            variant="subtle"
            color="red"
            data-testid="map-active-clear"
            disabled={rows.length === 0}
            onClick={onClearAll}
          >
            Apagar todo
          </Button>
        </Group>
      </Group>
      {rows.length === 0 ? (
        <Text size="xs" c="dimmed">
          Nada prendido. Usá un preset o el catálogo.
        </Text>
      ) : (
        <Stack gap={2}>
          {rows.map((row) => {
            const opacity = opacityByLayer[row.id] ?? 1;
            return (
              <Stack key={row.id} gap={2}>
                <Group justify="space-between" wrap="nowrap" gap={6}>
                  <Text size="xs" lineClamp={1} style={{ flex: 1 }}>
                    {row.label}
                  </Text>
                  {onLayerOpacityChange ? (
                    <ActionIcon
                      size="md"
                      variant="subtle"
                      color="gray"
                      aria-label={opacity === 0 ? `Mostrar ${row.label}` : `Atenuar ${row.label}`}
                      data-testid={`map-active-eye-${row.id}`}
                      onClick={() => onLayerOpacityChange(row.id, opacity === 0 ? 1 : 0)}
                    >
                      {opacity === 0 ? <IconEyeOff size={12} /> : <IconEye size={12} />}
                    </ActionIcon>
                  ) : null}
                  <ActionIcon
                    size="md"
                    variant="subtle"
                    color="gray"
                    aria-label={`Quitar ${row.label}`}
                    data-testid={`map-active-remove-${row.id}`}
                    onClick={() => onRemove(row.id)}
                  >
                    <IconX size={12} />
                  </ActionIcon>
                </Group>
                {onLayerOpacityChange ? (
                  <Slider
                    size="xs"
                    min={0}
                    max={1}
                    step={0.05}
                    value={opacity}
                    thumbLabel={`Opacidad ${row.label}`}
                    data-testid={`map-active-opacity-${row.id}`}
                    onChange={(value) => onLayerOpacityChange(row.id, value)}
                  />
                ) : null}
                {row.legend ? (
                  <Stack gap={2} pl="xs">
                    {row.legend}
                  </Stack>
                ) : null}
              </Stack>
            );
          })}
        </Stack>
      )}
    </Stack>
  );
}
