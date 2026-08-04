import { useEffect, useRef } from 'react';

/**
 * Key stamped on the history entry the hook pushes. Exported so tests assert
 * the contract instead of a magic string.
 */
export const DRAWER_HISTORY_MARKER = '__consorcioDrawer';

export interface UseDrawerHistoryCloseOptions {
  /** Whether the overlay (Drawer / Modal) is currently open. */
  opened: boolean;
  /** Closes the overlay. Called when the user pops the marker entry. */
  onClose: () => void;
  /**
   * Set to `false` where the overlay does not exist (desktop layouts). A
   * disabled hook NEVER touches the history stack.
   */
  enabled?: boolean;
}

function markerIsOnTop(): boolean {
  const state = window.history.state as Record<string, unknown> | null;
  return Boolean(state && state[DRAWER_HISTORY_MARKER] === true);
}

/**
 * AUD-005 — makes the hardware/browser Back button close an overlay instead of
 * leaving the page.
 *
 * On Android, Back is the universal "dismiss" gesture. With the mobile layers
 * Drawer open, Back used to navigate away from the map entirely: the user lost
 * the page to close a panel. The fix is the standard history-marker pattern:
 *
 * 1. Opening pushes a synthetic entry tagged with {@link DRAWER_HISTORY_MARKER}
 *    (same URL, so nothing visible changes).
 * 2. Back pops that entry → `popstate` → the overlay closes and the navigation
 *    is consumed. The user stays on the page.
 * 3. Closing by any OTHER means (tap outside, ✕, Escape, desktop breakpoint,
 *    unmount) rewinds the marker with `history.back()` so the stack does not
 *    accumulate phantom entries.
 *
 * Step 3 only fires when the marker is still the TOP of the stack. If a real
 * navigation landed on top of it while the overlay was open, rewinding would
 * undo the user's navigation — so the hook leaves the stack alone instead.
 */
export function useDrawerHistoryClose({
  opened,
  onClose,
  enabled = true,
}: UseDrawerHistoryCloseOptions): void {
  // `onClose` identity changes across renders; reading it from a ref keeps the
  // history effect keyed ONLY on `opened`/`enabled`, so a parent re-render can
  // never push a second marker.
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  });

  // True between "we pushed the marker" and "the marker is gone" (popped by
  // the user or rewound by us). Guards against double push and double back.
  const pushedRef = useRef(false);

  useEffect(() => {
    if (!enabled || !opened) return;
    if (typeof window === 'undefined') return;

    // Spread the current state so the router's own bookkeeping survives the
    // synthetic entry.
    const currentState = (window.history.state ?? {}) as Record<string, unknown>;
    window.history.pushState({ ...currentState, [DRAWER_HISTORY_MARKER]: true }, '');
    pushedRef.current = true;

    const handlePopState = () => {
      if (!pushedRef.current) return;
      // The browser ALREADY removed our entry — closing here must not call
      // `history.back()` again (that would eat a real entry).
      pushedRef.current = false;
      onCloseRef.current();
    };

    window.addEventListener('popstate', handlePopState);

    return () => {
      window.removeEventListener('popstate', handlePopState);
      if (!pushedRef.current) return;
      pushedRef.current = false;
      if (markerIsOnTop()) {
        window.history.back();
      }
    };
  }, [enabled, opened]);
}
