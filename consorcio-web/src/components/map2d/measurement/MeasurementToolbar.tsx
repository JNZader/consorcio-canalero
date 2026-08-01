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
 * - Absolute, `top: 220, right: 10` — sits right-aligned, directly below
 *   the MapLibre `top-right` control stack (NavigationControl ~110px +
 *   FullscreenControl ~30px) AND the `MapActionsPanel` Export icon at
 *   `top: 175` (added 2026-04-28 when the standalone "Marcar punto" /
 *   "Ver zonificación" panel was retired). Horizontal layout (`Group`)
 *   so the row doesn't clash visually with the fullscreen button.
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

import { Box, Group, Menu, Tooltip, UnstyledButton } from '@mantine/core';
import { memo } from 'react';

import { IconPolygon, IconRuler, IconTrash, IconVectorTriangle } from '../../ui/icons';
import type { MeasurementMode } from './useMeasurement';

export interface MeasurementToolbarProps {
  readonly mode: MeasurementMode;
  readonly hasMeasurements: boolean;
  readonly onStartDistance: () => void;
  readonly onStartArea: () => void;
  readonly onClear: () => void;
  /**
   * Ficha territorial free-draw (A5). When `onToggleFichaDraw` is provided, a
   * "Dibujar polígono" toggle renders BESIDE the measurement buttons (design
   * §6.2 — same floating toolbar). `fichaDrawActive` drives its active cue. The
   * 3D viewer omits both and gets no draw button.
   */
  readonly fichaDrawActive?: boolean;
  readonly onToggleFichaDraw?: () => void;
}

export const MeasurementToolbar = memo(function MeasurementToolbar({
  mode,
  hasMeasurements,
  onStartDistance,
  onStartArea,
  onClear,
  fichaDrawActive = false,
  onToggleFichaDraw,
}: MeasurementToolbarProps) {
  // `mode` is the single interaction machine (JDB-012); it reads `ficha-dibujo`
  // while drawing, but the "Medir" cue must only light for measurement modes.
  const isMeasuring = mode === 'measuring-distance' || mode === 'measuring-area';

  return (
    <Box
      className="maplibregl-ctrl maplibregl-ctrl-group"
      style={{
        position: 'absolute',
        top: 180,
        right: 10,
        zIndex: 16,
        margin: 0,
      }}
    >
      <Group gap={0} wrap="nowrap" style={{ flexDirection: 'column' }}>
        <Menu shadow="md" width={200}>
          <Menu.Target>
            <Tooltip label="Medir" position="left" withArrow>
              <UnstyledButton
                type="button"
                aria-label="Medir"
                style={{
                  width: 29,
                  height: 29,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  cursor: 'pointer',
                  background: isMeasuring ? '#fb923c' : 'transparent',
                  color: isMeasuring ? '#fff' : '#333',
                }}
              >
                <IconRuler size={16} />
              </UnstyledButton>
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

        {onToggleFichaDraw && (
          <Tooltip label="Dibujar polígono (ficha territorial)" position="left" withArrow>
            <UnstyledButton
              type="button"
              aria-label="Dibujar polígono"
              aria-pressed={fichaDrawActive}
              onClick={onToggleFichaDraw}
              style={{
                width: 29,
                height: 29,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
                background: fichaDrawActive ? '#fb923c' : 'transparent',
                color: fichaDrawActive ? '#fff' : '#333',
              }}
            >
              <IconVectorTriangle size={16} />
            </UnstyledButton>
          </Tooltip>
        )}

        {hasMeasurements && (
          <Tooltip label="Limpiar mediciones" position="left" withArrow>
            <UnstyledButton
              type="button"
              aria-label="Limpiar mediciones"
              onClick={onClear}
              style={{
                width: 29,
                height: 29,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
                color: '#dc2626',
              }}
            >
              <IconTrash size={16} />
            </UnstyledButton>
          </Tooltip>
        )}
      </Group>
    </Box>
  );
});
