/**
 * MeasurementToolbar — progressive-disclosure floating control.
 *
 * Two-button max, one dropdown menu: collapses the old 3-icon row
 * (Distance / Area / Clear) into a single "Medir" trigger that opens
 * a menu with the two measurement modes, plus a conditional "Limpiar"
 * ActionIcon that only appears when there is something to clear.
 *
 * Pure presentational component. State lives in the `useMeasurement`
 * hook that the parent owns. The toolbar only visualises `mode` (trigger
 * active/idle) + `hasMeasurements` (Limpiar rendered/hidden) and wires
 * three callbacks.
 *
 * Pattern reference:
 * - The `MapActionsPanel` "Exportar" trigger (commit 215316d) is the
 *   canonical Mantine `Menu.Target` + `Tooltip` + `ActionIcon` shape.
 *   We mirror it here for consistency across the map's floating
 *   controls.
 *
 * Placement:
 * - Absolute, `top: 150, right: 10` — sits right-aligned, directly below
 *   the MapLibre `top-right` control stack (NavigationControl ~110px +
 *   FullscreenControl ~30px + margin). See `useMapInitialization.ts` for
 *   the controls that define the stack. Horizontal layout (`Group`) so
 *   the row doesn't clash visually with the fullscreen button.
 * - `zIndex: 16` matches `MapActionsPanel`'s layer so we're above the
 *   map canvas but below modals/menus.
 *
 * Accessibility:
 * - The Medir trigger carries an explicit `aria-label="Medir"`
 *   (required by Mantine `ActionIcon` — the tooltip text alone does
 *   not reach SR users).
 * - Active-mode cue: `variant="filled"` (with orange color matching
 *   the `#fd7e14` draw style from Batch B) is applied whenever
 *   `mode !== 'idle'`, so both sighted and SR users have a clear
 *   indication that a measurement is live.
 * - The Limpiar ActionIcon is conditionally rendered rather than
 *   disabled: when there is nothing to clear, showing a greyed-out
 *   button is noise — hiding it reduces chrome and mirrors how the
 *   "Exportar PDF" menu entry is gated inside `MapActionsPanel`.
 */

import { ActionIcon, Group, Menu, Paper, Tooltip } from '@mantine/core';
import { memo } from 'react';

import { IconPolygon, IconRuler, IconTrash } from '../../ui/icons';
import type { MeasurementMode } from './useMeasurement';

export interface MeasurementToolbarProps {
  readonly mode: MeasurementMode;
  readonly hasMeasurements: boolean;
  readonly onStartDistance: () => void;
  readonly onStartArea: () => void;
  readonly onClear: () => void;
}

export const MeasurementToolbar = memo(function MeasurementToolbar({
  mode,
  hasMeasurements,
  onStartDistance,
  onStartArea,
  onClear,
}: MeasurementToolbarProps) {
  const isMeasuring = mode !== 'idle';

  return (
    <Paper
      shadow="md"
      p={4}
      radius="md"
      style={{
        position: 'absolute',
        top: 150,
        right: 10,
        zIndex: 16,
        background: 'light-dark(rgba(255,255,255,0.94), rgba(36,36,36,0.94))',
        backdropFilter: 'blur(6px)',
      }}
    >
      <Group gap={4} wrap="nowrap">
        <Menu shadow="md" width={200}>
          <Menu.Target>
            <Tooltip label="Medir" position="bottom" withArrow>
              <ActionIcon
                aria-label="Medir"
                size="lg"
                variant={isMeasuring ? 'filled' : 'subtle'}
                color="orange"
              >
                <IconRuler size={18} />
              </ActionIcon>
            </Tooltip>
          </Menu.Target>
          <Menu.Dropdown>
            <Menu.Item leftSection={<IconRuler size={14} />} onClick={onStartDistance}>
              Medir distancia
            </Menu.Item>
            <Menu.Item leftSection={<IconPolygon size={14} />} onClick={onStartArea}>
              Medir área
            </Menu.Item>
          </Menu.Dropdown>
        </Menu>

        {hasMeasurements && (
          <Tooltip label="Limpiar mediciones" position="bottom" withArrow>
            <ActionIcon
              aria-label="Limpiar mediciones"
              size="lg"
              variant="subtle"
              color="red"
              onClick={onClear}
            >
              <IconTrash size={18} />
            </ActionIcon>
          </Tooltip>
        )}
      </Group>
    </Paper>
  );
});
