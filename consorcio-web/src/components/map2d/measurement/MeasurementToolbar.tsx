/**
 * MeasurementToolbar — floating 3-button control (distance / area / clear).
 *
 * Pure presentational component. State lives in the `useMeasurement` hook
 * that the parent owns. The toolbar only visualises `mode` (which button
 * is active) + `hasMeasurements` (Clear enabled/disabled) and wires 3
 * callbacks.
 *
 * Placement:
 * - Absolute, `top: 150, right: 10` — sits right-aligned, directly below
 *   the MapLibre `top-right` control stack (NavigationControl ~110px +
 *   FullscreenControl ~30px + margin). See `useMapInitialization.ts` for
 *   the controls that define the stack. Horizontal layout (3 buttons in a
 *   `Group`) so the row doesn't clash visually with the fullscreen button.
 * - `zIndex: 16` matches `MapActionsPanel`'s layer so we're above the
 *   map canvas but below modals/menus.
 *
 * Accessibility:
 * - Each button has an explicit `aria-label` (required by Mantine
 *   `ActionIcon` — the tooltip text alone does not reach SR users).
 * - Distance/Area buttons expose `aria-pressed` so SR users hear whether
 *   the measurement mode is active.
 * - Clear button uses the standard `disabled` attribute, which already
 *   exposes `aria-disabled` via Mantine.
 */

import { ActionIcon, Group, Paper, Tooltip } from '@mantine/core';
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
  const isMeasuringDistance = mode === 'measuring-distance';
  const isMeasuringArea = mode === 'measuring-area';

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
        <Tooltip label="Medir distancia" position="bottom" withArrow>
          <ActionIcon
            aria-label="Medir distancia"
            aria-pressed={isMeasuringDistance}
            size="lg"
            variant={isMeasuringDistance ? 'filled' : 'subtle'}
            color="orange"
            onClick={onStartDistance}
          >
            <IconRuler size={18} />
          </ActionIcon>
        </Tooltip>

        <Tooltip label="Medir área" position="bottom" withArrow>
          <ActionIcon
            aria-label="Medir área"
            aria-pressed={isMeasuringArea}
            size="lg"
            variant={isMeasuringArea ? 'filled' : 'subtle'}
            color="orange"
            onClick={onStartArea}
          >
            <IconPolygon size={18} />
          </ActionIcon>
        </Tooltip>

        <Tooltip label="Limpiar mediciones" position="bottom" withArrow>
          <ActionIcon
            aria-label="Limpiar mediciones"
            size="lg"
            variant="subtle"
            color="red"
            disabled={!hasMeasurements}
            onClick={onClear}
          >
            <IconTrash size={18} />
          </ActionIcon>
        </Tooltip>
      </Group>
    </Paper>
  );
});
