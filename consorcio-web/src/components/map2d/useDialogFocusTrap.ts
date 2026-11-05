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

/**
 * Trampa de foco del panel de capas en móvil (`aria-modal`).
 * Tab cicla adentro, Escape cierra (salvo en un campo de texto), un foco
 * que se escapa vuelve al diálogo, y al cerrar el foco regresa al disparador.
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
      if (event.key === 'Escape') {
        if (isFromTextEntry(event.target)) return;
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
      const back = trigger?.isConnected ? trigger : triggerRef.current;
      back?.focus({ preventScroll: true });
    };
  }, [active, dialogRef, triggerRef]);
}
