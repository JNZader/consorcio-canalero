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
 *     bottom edge of the map canvas. Full width, internally scrollable, with a
 *     handle bar that cycles through three height caps.
 *
 * The handle is a TAP toggle, not a pointer-drag gesture: it needs no pointer
 * capture, no velocity tracking and no scroll-vs-drag arbitration, and it is
 * fully reachable by keyboard and screen readers.
 *
 * SHEET STAGES (T3a, fix 3). The sheet used to OPEN at its 45% cap, i.e. a new
 * selection immediately ate almost half the canvas. It now opens at `peek`
 * (~25%: the pinned header plus the summary line) and a handle tap CYCLES
 *
 *     peek (25%) → medio (45%) → alto (85%) → peek
 *
 * One affordance, one direction, always reachable — a two-control model
 * (separate grow/shrink) doubles the chrome in the tightest strip on screen for
 * no gain, and a "grow then bounce back" model hides the way down behind the
 * top of the cycle. Every stage is a `max-height` CAP, never a fixed height, so
 * a short panel still sizes to its content. `resetKey` returns the sheet to
 * `peek` whenever the caller's selection changes.
 *
 * MINIMIZE-TO-PILL (T3a, fix 2). Both shapes accept `minimized` +
 * `onToggleMinimize` + `pillLabel`. Minimized, the shell renders ONLY a pill
 * anchored where the panel was — a chip at the right edge on desktop, a slim bar
 * at the bottom edge in sheet mode — carrying a meaningful summary of what is
 * selected. The state is owned by the caller (`MapUiPanels`) because the map
 * drives it too: dragging the map auto-minimizes both panels, and restoring is
 * always an explicit tap on the pill.
 *
 * Close affordance: in sheet mode the shell owns it. The panels render their own
 * `Title + CloseButton` row inside `children`, i.e. inside the SCROLLABLE body —
 * on a tall ficha that button scrolls out of reach. In sheet mode the panels
 * therefore omit their inline close button and pass `onClose` + `closeLabel`
 * here, so the control sits in the pinned header strip next to the handle.
 * Exactly one close affordance is rendered in either shape.
 */

import { ActionIcon, CloseButton, Paper, Text, UnstyledButton } from '@mantine/core';
import { IconChevronDown } from '@tabler/icons-react';
import { type ReactNode, useState } from 'react';

import styles from '../../styles/components/map.module.css';

/** Height caps of the bottom sheet, in cycle order. */
export const SHEET_STAGES = ['peek', 'medio', 'alto'] as const;
export type SheetStage = (typeof SHEET_STAGES)[number];

/** Next stage in the peek → medio → alto → peek cycle. */
export function nextSheetStage(stage: SheetStage): SheetStage {
  const index = SHEET_STAGES.indexOf(stage);
  return SHEET_STAGES[(index + 1) % SHEET_STAGES.length];
}

const STAGE_ACTION_LABEL: Record<SheetStage, string> = {
  peek: 'Ampliar',
  medio: 'Ampliar',
  alto: 'Contraer',
};

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
  /**
   * Minimized state (T3a, fix 2). Owned by the caller so the map can drive it
   * (auto-minimize on drag) and so a NEW selection can restore it.
   */
  readonly minimized?: boolean;
  /** Toggles `minimized`. When absent no minimize affordance is rendered. */
  readonly onToggleMinimize?: () => void;
  /**
   * Summary shown on the pill while minimized, e.g. "Ficha · 116.8 ha". Must be
   * meaningful — a pill reading only "Ficha" tells the user nothing about which
   * selection it will restore.
   */
  readonly pillLabel?: string;
  /** Class applied to the pill in floating mode (anchors it where the card was). */
  readonly pillClassName?: string;
  /**
   * Opaque selection marker. Whenever it CHANGES the sheet returns to `peek`, so
   * a fresh selection always opens small (T3a, fix 3).
   */
  readonly resetKey?: unknown;
  readonly children: ReactNode;
}

export function MapPanelShell({
  sheet,
  floatingClassName,
  testId,
  sheetLabel,
  onClose,
  closeLabel,
  minimized = false,
  onToggleMinimize,
  pillLabel,
  pillClassName,
  resetKey,
  children,
}: MapPanelShellProps) {
  const [stage, setStage] = useState<SheetStage>('peek');

  // A new selection reuses the same mounted shell, so the stage has to be reset
  // explicitly — otherwise clicking a second parcel would open at whatever cap
  // the previous one was left at. Adjusted DURING render (React's documented
  // "resetting state when a prop changes" pattern) rather than in an effect, so
  // the sheet never paints one frame at the previous selection's height.
  // `resetKey` is a pure TRIGGER: only its identity matters, never its value.
  const [lastResetKey, setLastResetKey] = useState(resetKey);
  if (lastResetKey !== resetKey) {
    setLastResetKey(resetKey);
    setStage('peek');
  }

  const canMinimize = !!onToggleMinimize;

  // Restaurar desde la pildora: la pildora en sheet es `position: fixed` (B2-2.2),
  // asi que sigue tocable con la pagina scrolleada — pero el panel que restaura
  // esta anclado al CANVAS, y si el usuario scrolleo mientras estaba minimizada,
  // el panel reaparece fuera de vista y la restauracion se lee como "no pasó
  // nada". Traer el canvas a cuadro cierra el circulo. `block: 'nearest'` no
  // mueve nada si ya se ve.
  const handleRestore = () => {
    onToggleMinimize?.();
    if (!sheet) return;
    document
      .querySelector('[data-testid="map-workspace-canvas"]')
      ?.scrollIntoView({ block: 'nearest' });
  };

  if (minimized && canMinimize) {
    return (
      <UnstyledButton
        className={sheet ? styles.panelSheetPill : `${styles.panelPill} ${pillClassName ?? ''}`}
        onClick={handleRestore}
        data-testid={`${testId}-pill`}
        data-sheet={sheet ? 'true' : undefined}
        aria-label={`Restaurar ${sheetLabel}`}
      >
        <Text size="xs" fw={600} truncate>
          {pillLabel ?? sheetLabel}
        </Text>
      </UnstyledButton>
    );
  }

  const minimizeButton = canMinimize ? (
    <ActionIcon
      variant="subtle"
      color="gray"
      className={styles.panelActionIcon}
      onClick={onToggleMinimize}
      aria-label={`Minimizar ${sheetLabel}`}
      data-testid={`${testId}-minimize`}
    >
      <IconChevronDown size={16} />
    </ActionIcon>
  ) : null;

  if (!sheet) {
    return (
      <Paper shadow="md" p="md" radius="md" className={floatingClassName} data-testid={testId}>
        {minimizeButton && <div className={styles.panelCardMinimize}>{minimizeButton}</div>}
        {children}
      </Paper>
    );
  }

  // `medio` maps to NO modifier class on purpose: it is the base `.panelSheet`
  // shape (the 45% cap the sheet has always had), so the middle stage needs no
  // override — only `peek` (25%) and `alto` (85%) add one. Adding a
  // `.panelSheetMedio` that re-declares 45% would just duplicate the base rule
  // and give it a second place to drift.
  const stageClass =
    stage === 'peek'
      ? styles.panelSheetPeek
      : stage === 'alto'
        ? styles.panelSheetExpanded
        : undefined;
  const className = stageClass ? `${styles.panelSheet} ${stageClass}` : styles.panelSheet;

  return (
    <Paper
      shadow="md"
      p="md"
      radius="md"
      className={className}
      data-testid={testId}
      data-sheet="true"
      /* PUBLIC CONTRACT with map.module.css — do not rename or drop. The
         measurement dock lifts itself clear of a PARTIAL sheet via
         `.mapCanvasWrapper:has(.panelSheet[data-stage='peek'|'medio'])`. It
         cannot key off the modifier classes because `medio` deliberately has
         none (see the comment above). Guarded by
         `tests/unit/mapDockSheetClearance.test.ts`. */
      data-stage={stage}
      data-expanded={stage === 'alto' ? 'true' : 'false'}
    >
      <div className={styles.panelSheetHeader}>
        <button
          type="button"
          className={styles.panelSheetHandle}
          onClick={() => setStage((value) => nextSheetStage(value))}
          aria-expanded={stage !== 'peek'}
          aria-label={`${STAGE_ACTION_LABEL[stage]} ${sheetLabel}`}
          data-testid={`${testId}-sheet-handle`}
        >
          <span className={styles.panelSheetGrabber} />
        </button>
        <div className={styles.panelSheetActions}>
          {minimizeButton}
          {onClose && closeLabel && (
            <CloseButton
              onClick={onClose}
              className={styles.panelCloseButton}
              aria-label={closeLabel}
              data-testid={`${testId}-sheet-close`}
            />
          )}
        </div>
      </div>
      <div className={styles.panelSheetBody}>{children}</div>
    </Paper>
  );
}
