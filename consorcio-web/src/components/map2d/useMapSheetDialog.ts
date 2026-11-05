import { type RefObject, useEffect, useId, useRef, useState, useSyncExternalStore } from 'react';

import { useDialogFocusTrap } from './useDialogFocusTrap';

/**
 * Sheets del mapa que pueden convivir (ficha, relevamiento, perfil, riesgos).
 * Solo la de mayor prioridad — y, a igualdad, la última en abrirse — queda
 * modal. El drawer de capas (`data-drawer-open` en el workspace) tapa el
 * lienzo con `inert`: mientras está abierto ninguna sheet de adentro atrapa
 * el foco.
 */
interface SheetEntry {
  id: string;
  priority: number;
}

const stack: SheetEntry[] = [];
const listeners = new Set<() => void>();
let topId = '';

function recomputeTop(): void {
  let bestId = '';
  let bestPriority = Number.NEGATIVE_INFINITY;
  let bestIndex = -1;
  for (let index = 0; index < stack.length; index += 1) {
    const entry = stack[index];
    if (!entry) continue;
    if (entry.priority > bestPriority || (entry.priority === bestPriority && index >= bestIndex)) {
      bestPriority = entry.priority;
      bestIndex = index;
      bestId = entry.id;
    }
  }
  topId = bestId;
}

function emit(): void {
  for (const listener of listeners) listener();
}

function publish(): void {
  const previous = topId;
  recomputeTop();
  if (previous !== topId) emit();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getTopId(): string {
  return topId;
}

function useTopMapSheet(id: string, open: boolean, priority: number): boolean {
  useEffect(() => {
    if (!open) return;
    stack.push({ id, priority });
    publish();
    return () => {
      const index = stack.findIndex((entry) => entry.id === id);
      if (index >= 0) stack.splice(index, 1);
      publish();
    };
  }, [open, id, priority]);

  const current = useSyncExternalStore(subscribe, getTopId, getTopId);
  return open && current === id;
}

function useMapDrawerCovers(ref: RefObject<HTMLElement | null>, open: boolean): boolean {
  const [covered, setCovered] = useState(false);
  useEffect(() => {
    if (!open) return;
    const root = ref.current?.closest('[data-testid="map-workspace-root"]');
    if (!root) return;
    const sync = () => {
      setCovered(root.getAttribute('data-drawer-open') === 'true');
    };
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(root, { attributes: true, attributeFilter: ['data-drawer-open'] });
    return () => observer.disconnect();
  }, [open, ref]);
  return open && covered;
}

/**
 * Misma trampa que el drawer de capas: foco adentro, Escape cierra, el foco
 * vuelve al disparador, `aria-modal` solo mientras esta sheet es la de adelante.
 */
export function useMapSheetDialog<T extends HTMLElement>(
  open: boolean,
  onEscape: () => void,
  priority: number,
  triggerRef?: RefObject<HTMLElement | null>,
  dialogRef?: RefObject<T | null>
): { ref: RefObject<T | null>; modal: boolean } {
  const id = useId();
  const ownRef = useRef<T>(null);
  const ref = dialogRef ?? ownRef;
  const fallbackTriggerRef = useRef<HTMLElement | null>(null);
  const covered = useMapDrawerCovers(ref, open);
  const registered = open && !covered;
  const top = useTopMapSheet(id, registered, priority);
  const modal = registered && top;
  useDialogFocusTrap(modal, ref, triggerRef ?? fallbackTriggerRef, onEscape);
  return { ref, modal };
}
