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
 * - The dock offset, the button box AND the stack direction now live in
 *   `map.module.css` (`.mapCtrlDock` / `.measurementDock` / `.mapCtrlButton` /
 *   `.measurementGroup`): on a coarse pointer every control grows to the 44px
 *   WCAG target and reveals a text label — a media query cannot reach an inline
 *   style (map-fluidity T2, fix 2).
 * - COARSE POINTERS RE-LAY THIS TOOLBAR. Four 44px buttons stacked under the
 *   right-hand column would end at 436px on a 380px canvas with
 *   `overflow: hidden`, i.e. two buttons clipped off-canvas. On coarse pointers
 *   it becomes a horizontal row anchored bottom-left instead (see the fit-budget
 *   comment in `map.module.css`), which also lands it in the thumb zone.
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

import styles from '../../../styles/components/map.module.css';
import { IconPolygon, IconRoute, IconRuler, IconTrash, IconVectorTriangle } from '../../ui/icons';
import type { MeasurementMode } from './useMeasurement';

export interface MeasurementToolbarProps {
  readonly mode: MeasurementMode;
  readonly hasMeasurements: boolean;
  readonly onStartDistance: () => void;
  readonly onStartArea: () => void;
  readonly onClear: () => void;
  /**
   * Cancel the ACTIVE measurement without saving (map-fluidity T1). When
   * provided, the Medir trigger turns into a toggle-OFF while measuring instead
   * of re-opening its menu, which is what gives the mode a visible exit. Omit it
   * (3D viewer / legacy callers) and the old menu-always behaviour is kept.
   */
  readonly onCancel?: () => void;
  /**
   * Ficha territorial free-draw (A5). When `onToggleFichaDraw` is provided, a
   * "Dibujar polígono" toggle renders BESIDE the measurement buttons (design
   * §6.2 — same floating toolbar). `fichaDrawActive` drives its active cue. The
   * 3D viewer omits both and gets no draw button.
   */
  readonly fichaDrawActive?: boolean;
  readonly onToggleFichaDraw?: () => void;
  /**
   * Ficha territorial canal buffer (A6). When `onToggleFichaCanal` is provided, a
   * "Seleccionar canal" toggle renders beside the draw button (design §6.3 — same
   * floating toolbar). `fichaCanalActive` drives its active cue. The 3D viewer
   * omits it.
   */
  readonly fichaCanalActive?: boolean;
  readonly onToggleFichaCanal?: () => void;
}

export const MeasurementToolbar = memo(function MeasurementToolbar({
  mode,
  hasMeasurements,
  onStartDistance,
  onStartArea,
  onClear,
  onCancel,
  fichaDrawActive = false,
  onToggleFichaDraw,
  fichaCanalActive = false,
  onToggleFichaCanal,
}: MeasurementToolbarProps) {
  // `mode` is the single interaction machine (JDB-012); it reads `ficha-dibujo`
  // while drawing, but the "Medir" cue must only light for measurement modes.
  const isMeasuring = mode === 'measuring-distance' || mode === 'measuring-area';

  // Exit affordance (map-fluidity T1). Measuring mode used to be a one-way door:
  // the trash button was gated on `hasMeasurements`, so a user who started a
  // measurement and drew nothing had NO visible way out. The button now shows
  // for the whole of measuring mode and renames itself when there is nothing to
  // wipe — it cancels the mode instead.
  const showExitButton = hasMeasurements || isMeasuring;
  const exitLabel = hasMeasurements ? 'Limpiar mediciones' : 'Cancelar medición';
  const handleExit = hasMeasurements ? onClear : (onCancel ?? onClear);

  // While measuring, the trigger is a toggle-OFF rather than a menu re-opener.
  const isToggleOff = isMeasuring && !!onCancel;
  const measureTriggerButton = (
    <Tooltip label={isMeasuring ? 'Cancelar medición' : 'Medir'} position="left" withArrow>
      <UnstyledButton
        type="button"
        aria-label="Medir"
        aria-pressed={isMeasuring}
        // Spread conditionally: passing an explicit `onClick={undefined}` would
        // OVERRIDE the handler `Menu.Target` injects when it clones this node,
        // silently breaking the dropdown in the non-measuring case.
        {...(isToggleOff ? { onClick: onCancel } : {})}
        className={styles.mapCtrlButton}
        style={{
          background: isMeasuring ? '#fb923c' : 'transparent',
          color: isMeasuring ? '#fff' : '#333',
        }}
      >
        <IconRuler size={16} />
        {/* Coarse-pointer only (CSS): tooltips never fire on touch. */}
        <span className={styles.mapCtrlButtonLabel}>Medir</span>
      </UnstyledButton>
    </Tooltip>
  );

  return (
    <Box
      className={`maplibregl-ctrl maplibregl-ctrl-group ${styles.mapCtrlDock} ${styles.measurementDock}`}
    >
      <Group gap={0} wrap="nowrap" className={styles.measurementGroup}>
        {isToggleOff ? (
          // Toggle-OFF: no menu, the trigger itself ends the mode.
          measureTriggerButton
        ) : (
          <Menu shadow="md" width={200}>
            <Menu.Target>{measureTriggerButton}</Menu.Target>
            <Menu.Dropdown>
              <Menu.Item leftSection={<IconRuler size={14} />} onClick={onStartDistance}>
                Medir distancia
              </Menu.Item>
              <Menu.Item leftSection={<IconPolygon size={14} />} onClick={onStartArea}>
                Medir área
              </Menu.Item>
            </Menu.Dropdown>
          </Menu>
        )}

        {onToggleFichaDraw && (
          <Tooltip label="Dibujar polígono (ficha territorial)" position="left" withArrow>
            <UnstyledButton
              type="button"
              aria-label="Dibujar polígono"
              aria-pressed={fichaDrawActive}
              onClick={onToggleFichaDraw}
              className={styles.mapCtrlButton}
              style={{
                background: fichaDrawActive ? '#fb923c' : 'transparent',
                color: fichaDrawActive ? '#fff' : '#333',
              }}
            >
              <IconVectorTriangle size={16} />
              <span className={styles.mapCtrlButtonLabel}>Dibujar</span>
            </UnstyledButton>
          </Tooltip>
        )}

        {onToggleFichaCanal && (
          <Tooltip label="Seleccionar canal (ficha territorial)" position="left" withArrow>
            <UnstyledButton
              type="button"
              aria-label="Seleccionar canal"
              aria-pressed={fichaCanalActive}
              onClick={onToggleFichaCanal}
              className={styles.mapCtrlButton}
              style={{
                background: fichaCanalActive ? '#06b6d4' : 'transparent',
                color: fichaCanalActive ? '#fff' : '#333',
              }}
            >
              <IconRoute size={16} />
              <span className={styles.mapCtrlButtonLabel}>Canal</span>
            </UnstyledButton>
          </Tooltip>
        )}

        {showExitButton && (
          <Tooltip label={exitLabel} position="left" withArrow>
            <UnstyledButton
              type="button"
              aria-label={exitLabel}
              onClick={handleExit}
              className={styles.mapCtrlButton}
              style={{ color: '#dc2626' }}
            >
              <IconTrash size={16} />
              {/* The exit button shares the coarse-pointer label treatment: a
                  44px trash glyph with no text reads as ambiguous on touch. */}
              <span className={styles.mapCtrlButtonLabel}>
                {hasMeasurements ? 'Limpiar' : 'Cancelar'}
              </span>
            </UnstyledButton>
          </Tooltip>
        )}
      </Group>
    </Box>
  );
});
