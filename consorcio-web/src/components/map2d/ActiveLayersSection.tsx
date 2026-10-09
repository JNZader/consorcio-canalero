import { ActionIcon, Button, Group, Stack, Text } from '@mantine/core';
import type { ReactNode } from 'react';

import { IconX } from '../ui/icons';

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
}

/**
 * Short list of layers currently on the map (UX PDF R2a).
 * Catalog search / accordion stay below as "Agregar capas".
 */
export function ActiveLayersSection({
  rows,
  onRemove,
  onClearAll,
  onRestore,
}: ActiveLayersSectionProps) {
  return (
    <Stack gap={4} data-testid="map-active-layers">
      <Group justify="space-between" wrap="nowrap">
        <Text size="xs" fw={600}>
          En el mapa ({rows.length})
        </Text>
        <Group gap={4} wrap="nowrap">
          <Button size="compact-xs" variant="subtle" data-testid="map-active-restore" onClick={onRestore}>
            Restablecer
          </Button>
          <Button
            size="compact-xs"
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
          {rows.map((row) => (
            <Stack key={row.id} gap={2}>
              <Group justify="space-between" wrap="nowrap" gap={6}>
                <Text size="xs" lineClamp={1} style={{ flex: 1 }}>
                  {row.label}
                </Text>
                <ActionIcon
                  size="sm"
                  variant="subtle"
                  color="gray"
                  aria-label={`Quitar ${row.label}`}
                  data-testid={`map-active-remove-${row.id}`}
                  onClick={() => onRemove(row.id)}
                >
                  <IconX size={12} />
                </ActionIcon>
              </Group>
              {row.legend ? <Stack gap={2} pl="xs">{row.legend}</Stack> : null}
            </Stack>
          ))}
        </Stack>
      )}
    </Stack>
  );
}
