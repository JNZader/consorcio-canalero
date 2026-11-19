/**
 * SeleccionChips.tsx — the removable Pills of the current selection (S5, PR 3).
 *
 * Renders BELOW the map/list/draw/file choosers in the Elegir step so the
 * selection is always visible in every tab. Each Pill carries Mantine's
 * remove button (a real `<button>`: keyboard operable for free), plus a
 * "Quitar todas" action once more than one element is selected.
 *
 * PR 3: the MIXED selection shows BOTH halves — zonas pills (catalog names)
 * and geometry pills ("Dibujo 2", "lote.kml · Polígono 1") with their own
 * removal, so a drawn or imported polygon leaves the selection exactly like
 * a subcuenca does.
 */

import { Button, Group, Pill, Stack, Text } from '@mantine/core';

import { fmtHa } from '../fichaShared';
import type { SeleccionGeometria, ZonaRef } from './useSeleccionArea';

export interface SeleccionChipsProps {
  /** Selected zonas in catalog order (stable Pill order). */
  readonly zonas: readonly ZonaRef[];
  /** Selected drawn/imported geometries in selection order (PR 3). */
  readonly geometrias?: readonly SeleccionGeometria[];
  /** Drop one zona from the selection (reducer `quitar`). */
  readonly onRemove: (id: string) => void;
  /** Drop one geometry from the selection (PR 3). */
  readonly onRemoveGeometria?: (id: string) => void;
  /** Clear the whole selection (reducer `vaciar` + the geometry list). */
  readonly onClear: () => void;
}

export function SeleccionChips({
  zonas,
  geometrias = [],
  onRemove,
  onRemoveGeometria,
  onClear,
}: SeleccionChipsProps) {
  if (zonas.length === 0 && geometrias.length === 0) {
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
        {geometrias.map((geometria) => (
          <Pill
            key={geometria.id}
            size="sm"
            withRemoveButton
            onRemove={() => onRemoveGeometria?.(geometria.id)}
            data-testid="informe-area-chip-geometria"
          >
            {geometria.etiqueta} · {fmtHa(geometria.ha)}
          </Pill>
        ))}
      </Group>
      {zonas.length + geometrias.length > 1 && (
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
