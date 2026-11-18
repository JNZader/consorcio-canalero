/**
 * SeleccionChips.tsx — the removable Pills of the current selection (S5).
 *
 * Renders BELOW the map/list choosers in the Elegir step so the selection is
 * always visible in both tabs. Each Pill carries Mantine's remove button (a
 * real `<button>`: keyboard operable for free), plus a "Quitar todas" action
 * once more than one zona is selected.
 */

import { Button, Group, Pill, Stack, Text } from '@mantine/core';

import type { ZonaRef } from './useSeleccionArea';

export interface SeleccionChipsProps {
  /** Selected zonas in catalog order (stable Pill order). */
  readonly zonas: readonly ZonaRef[];
  /** Drop one zona from the selection (reducer `quitar`). */
  readonly onRemove: (id: string) => void;
  /** Clear the whole selection (reducer `vaciar`). */
  readonly onClear: () => void;
}

export function SeleccionChips({ zonas, onRemove, onClear }: SeleccionChipsProps) {
  if (zonas.length === 0) {
    return (
      <Text size="xs" c="dimmed" fs="italic" data-testid="informe-area-chips-vacio">
        Todavía no elegiste subcuencas.
      </Text>
    );
  }
  return (
    <Stack gap={4} data-testid="informe-area-chips">
      <Group gap={4} justify="flex-start">
        {zonas.map((zona) => (
          <Pill
            key={zona.id}
            size="sm"
            withRemoveButton
            onRemove={() => onRemove(zona.id)}
            data-testid="informe-area-chip"
          >
            {zona.nombre}
          </Pill>
        ))}
      </Group>
      {zonas.length > 1 && (
        <Button
          size="compact-xs"
          variant="subtle"
          color="gray"
          onClick={onClear}
          data-testid="informe-area-chips-quitar-todas"
        >
          Quitar todas
        </Button>
      )}
    </Stack>
  );
}
