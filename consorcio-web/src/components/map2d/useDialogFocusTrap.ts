import { type RefObject, useEffect, useRef } from 'react';

const FOCUSABLE = [
  'button:not([disabled])',
  '[href]',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(', ');

function focusableIn(dialog: HTMLElement): HTMLElement[] {
  return [...dialog.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((element) => {
    if (element.closest('[hidden]')) return false;
    if (element.getAttribute('aria-hidden') === 'true') return false;
    return true;
  });
}

function isFromTextEntry(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable;
}

const OUTSIDE_OWNER =
  '[role="dialog"], .mantine-Modal-root, .mantine-Drawer-root, .mantine-Popover-dropdown, .mantine-Menu-dropdown, .mantine-Combobox-dropdown';

/**
 * No robar el foco si el diálogo está inert, o si el evento vive en otro
 * diálogo o en un popover portaleado (Select, menú) abierto desde acá.
 */
function isForeignDialog(dialog: HTMLElement, target: EventTarget | null): boolean {
  if (!dialog.isConnected || dialog.closest('[inert]')) return true;
  if (!(target instanceof Node)) return false;
  const element = target instanceof Element ? target : target.parentElement;
  if (!element || dialog.contains(element)) return false;
  return element.closest(OUTSIDE_OWNER) != null;
}

/**
 * Trampa de foco de un diálogo modal del mapa (drawer de capas y sheets).
 * Tab cicla adentro, Escape cierra (salvo en un campo de texto o en otro
 * diálogo), un foco que se escapa vuelve al diálogo, y al cerrar el foco
 * regresa al disparador si esta trampa todavía lo tenía.
 */
export function useDialogFocusTrap(
  active: boolean,
  dialogRef: RefObject<HTMLElement | null>,
  triggerRef: RefObject<HTMLElement | null>,
  onEscape: () => void
) {
  const onEscapeRef = useRef(onEscape);
  onEscapeRef.current = onEscape;
  useEffect(() => {
    if (!active) return;
    const dialog = dialogRef.current;
    if (!dialog) return;

    const previous =
      document.activeElement instanceof HTMLElement && document.activeElement !== document.body
        ? document.activeElement
        : null;
    const trigger = previous ?? triggerRef.current;

    const onKeyDown = (event: KeyboardEvent) => {
      if (isForeignDialog(dialog, event.target)) return;
      if (event.key === 'Escape') {
        if (event.defaultPrevented || isFromTextEntry(event.target)) return;
        onEscapeRef.current();
        return;
      }
      if (event.key !== 'Tab') return;
      const items = focusableIn(dialog);
      if (items.length === 0) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const current = document.activeElement;
      if (event.shiftKey) {
        if (current === first || current === dialog || !dialog.contains(current)) {
          event.preventDefault();
          last?.focus();
        }
        return;
      }
      if (current === last) {
        event.preventDefault();
        first?.focus();
      }
    };

    const onFocusIn = (event: FocusEvent) => {
      if (isForeignDialog(dialog, event.target)) return;
      if (!(event.target instanceof Node) || dialog.contains(event.target)) return;
      const items = focusableIn(dialog);
      (items[0] ?? dialog).focus();
    };

    document.addEventListener('keydown', onKeyDown);
    document.addEventListener('focusin', onFocusIn);
    dialog.focus({ preventScroll: true });

    return () => {
      document.removeEventListener('keydown', onKeyDown);
      document.removeEventListener('focusin', onFocusIn);
      const active = document.activeElement;
      const inside = active instanceof Node && (active === dialog || dialog.contains(active));
      const released = active == null || active === document.body;
      if (!inside && !released) return;
      const back = trigger?.isConnected ? trigger : triggerRef.current;
      if (back?.isConnected) back.focus({ preventScroll: true });
    };
  }, [active, dialogRef, triggerRef]);
}
