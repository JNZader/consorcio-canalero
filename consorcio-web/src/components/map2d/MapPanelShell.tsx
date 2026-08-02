/**
 * MapPanelShell.tsx
 *
 * Shared chrome for the two floating map panels (`InfoPanel`,
 * `FichaTerritorialPanel`).
 *
 * Two shapes, one component (map-fluidity T2, fix 1):
 *
 *   - desktop / wide (`sheet={false}`): the historical floating card. The
 *     caller owns the class (`.infoPanel` / `.fichaPanel`, plus the compact
 *     modifier when both panels share the right-hand column).
 *   - narrow (`sheet={true}`, viewport <= 62em): a BOTTOM SHEET anchored to the
 *     bottom edge of the map canvas. Full width, capped at 45% of the canvas so
 *     the top 55% of the map stays visible, internally scrollable, with a handle
 *     bar that toggles 45% ⇄ 85%.
 *
 * The handle is a TAP toggle, not a pointer-drag gesture: it needs no pointer
 * capture, no velocity tracking and no scroll-vs-drag arbitration, and it is
 * fully reachable by keyboard and screen readers.
 *
 * Close affordance: in sheet mode the shell owns it. The panels render their own
 * `Title + CloseButton` row inside `children`, i.e. inside the SCROLLABLE body —
 * on a tall ficha that button scrolls out of reach. In sheet mode the panels
 * therefore omit their inline close button and pass `onClose` + `closeLabel`
 * here, so the control sits in the pinned header strip next to the handle.
 * Exactly one close affordance is rendered in either shape.
 */

import { CloseButton, Paper } from '@mantine/core';
import { type ReactNode, useState } from 'react';

import styles from '../../styles/components/map.module.css';

interface MapPanelShellProps {
  /** Render as a bottom sheet instead of a floating card. */
  readonly sheet: boolean;
  /** Class applied in floating (non-sheet) mode. Ignored when `sheet`. */
  readonly floatingClassName: string;
  readonly testId: string;
  /** Accessible name for the expand/collapse handle, e.g. "ficha territorial". */
  readonly sheetLabel: string;
  /**
   * Dismiss handler. Only consumed in sheet mode — floating panels keep their
   * own close button inside the (unscrolled) card header.
   */
  readonly onClose?: () => void;
  /** Accessible name for the sheet close button, e.g. "Cerrar ficha territorial". */
  readonly closeLabel?: string;
  readonly children: ReactNode;
}

export function MapPanelShell({
  sheet,
  floatingClassName,
  testId,
  sheetLabel,
  onClose,
  closeLabel,
  children,
}: MapPanelShellProps) {
  const [expanded, setExpanded] = useState(false);

  if (!sheet) {
    return (
      <Paper shadow="md" p="md" radius="md" className={floatingClassName} data-testid={testId}>
        {children}
      </Paper>
    );
  }

  const className = expanded
    ? `${styles.panelSheet} ${styles.panelSheetExpanded}`
    : styles.panelSheet;

  return (
    <Paper
      shadow="md"
      p="md"
      radius="md"
      className={className}
      data-testid={testId}
      data-sheet="true"
      data-expanded={expanded ? 'true' : 'false'}
    >
      <div className={styles.panelSheetHeader}>
        <button
          type="button"
          className={styles.panelSheetHandle}
          onClick={() => setExpanded((value) => !value)}
          aria-expanded={expanded}
          aria-label={expanded ? `Contraer ${sheetLabel}` : `Expandir ${sheetLabel}`}
          data-testid={`${testId}-sheet-handle`}
        >
          <span className={styles.panelSheetGrabber} />
        </button>
        {onClose && closeLabel && (
          <CloseButton
            className={styles.panelSheetClose}
            onClick={onClose}
            size="sm"
            aria-label={closeLabel}
            data-testid={`${testId}-sheet-close`}
          />
        )}
      </div>
      <div className={styles.panelSheetBody}>{children}</div>
    </Paper>
  );
}
